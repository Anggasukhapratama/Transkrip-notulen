# sebayu_app/routes/minutes.py
import base64
import json
import time
from datetime import datetime
from io import BytesIO
from urllib.parse import urlsplit

from flask import render_template, abort, redirect, url_for, flash, request, send_file, jsonify
from werkzeug.utils import secure_filename

from . import minutes_bp
from ..database import get_db
from ..config import DEFAULT_META, UPLOAD_DIR, ALLOWED_IMG, log
from ..notulen import build_minutes_data, build_docx_from_minutes

TR_SQL = (
    "SELECT id, program, filename, "
    "COALESCE(NULLIF(cleaned_transcript,''), transcript) AS transcript, "
    "created_at, COALESCE(summary,'') summary, COALESCE(minutes_meta,'') minutes_meta "
    "FROM transcripts WHERE id=?"
)


def _get_tr(tid: int):
    with get_db() as db:
        row = db.execute(TR_SQL, (tid,)).fetchone()
    if not row:
        abort(404)
    return row


def _load_meta(raw: str) -> dict:
    meta = DEFAULT_META.copy()
    if raw:
        try:
            meta.update(json.loads(raw))
        except Exception:
            pass
    return meta


def _save_meta(tid: int, meta: dict) -> None:
    with get_db() as db:
        db.execute("UPDATE transcripts SET minutes_meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), tid))
        db.commit()


@minutes_bp.get("/transcripts/<int:tid>/minutes")
def transcript_minutes(tid: int):
    row = _get_tr(tid)
    meta = _load_meta(row["minutes_meta"])
    data = build_minutes_data(dict(row), meta)
    return render_template("minutes.html", tr=row, data=data, meta=meta)


@minutes_bp.get("/transcripts/<int:tid>/minutes/edit")
def minutes_edit(tid: int):
    row = _get_tr(tid)
    meta = _load_meta(row["minutes_meta"])
    logo_qs = request.args.get("logo")
    if logo_qs and logo_qs.startswith("/uploads/"):
        meta["logo"] = logo_qs
    return render_template("minutes_edit.html", tid=tid, tr=row, meta=meta)


@minutes_bp.post("/transcripts/<int:tid>/minutes/edit")
def minutes_edit_save(tid: int):
    row = _get_tr(tid)
    meta = _load_meta(row["minutes_meta"])        # pertahankan field lain (mis. tanda tangan digital)
    fields = [
        "instansi", "alamat", "judul", "nomor", "hari", "tanggal", "waktu",
        "tempat", "acara", "peserta", "pimpinan", "notulis", "penutup", "logo", "kop_html",
        "ttd_kota", "ttd_tanggal", "ttd_jabatan", "ttd_nama", "ttd_pangkat", "ttd_nip",
    ]
    for k in fields:
        if k in request.form:
            meta[k] = (request.form.get(k) or "").strip()

    for key in ["kw_keputusan", "kw_tindak_lanjut", "kw_isu", "kw_arahan", "kw_catatan"]:
        raw = (request.form.get(key) or "").strip()
        if not raw:
            meta[key] = []
            continue
        try:
            val = json.loads(raw)
            if not isinstance(val, list):
                raise ValueError("Not a list")
            meta[key] = [str(x).strip() for x in val if str(x).strip()]
        except (json.JSONDecodeError, ValueError):
            meta[key] = [x.strip() for x in raw.split(",") if x.strip()]

    _save_meta(tid, meta)
    flash("Pengaturan notulen disimpan.")
    return redirect(url_for("minutes_bp.transcript_minutes", tid=tid))


@minutes_bp.post("/minutes/logo")
def upload_logo():
    f = request.files.get("logo")
    parts = urlsplit(request.form.get("redirect") or "")
    redirect_to = parts.path or url_for("main.index")      # hanya path lokal (cegah open redirect)
    if not f or f.filename == "":
        flash("Pilih file logo terlebih dahulu.")
        return redirect(redirect_to)
    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMG:
        flash("Format logo harus gambar (png/jpg/jpeg/gif/webp).")
        return redirect(redirect_to)
    fname = secure_filename(f"logo_{int(time.time())}.{ext}")
    f.save(UPLOAD_DIR / fname)
    flash("Logo terunggah.")
    return redirect(f"{redirect_to}?logo=/uploads/{fname}")


# ====================== TANDA TANGAN DIGITAL ======================

def _process_signature(raw: bytes) -> bytes:
    """Bersihkan latar putih -> transparan, potong tepi kosong, kecilkan ukuran."""
    from PIL import Image, ImageChops
    im = Image.open(BytesIO(raw)).convert("RGBA")
    r, g, b, a = im.split()
    lum = im.convert("L")
    # piksel terang (kertas putih) -> transparan secara halus
    keep = lum.point(lambda v: 255 if v < 200 else max(0, int((255 - v) * 255 / 55)))
    alpha = ImageChops.multiply(a, keep)
    im.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v > 12 else 0).getbbox()
    if not bbox:
        raise ValueError("Tanda tangan kosong.")
    pad = 8
    bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad))
    im = im.crop(bbox)
    if im.width > 700:
        im = im.resize((700, max(1, int(im.height * 700 / im.width))), Image.LANCZOS)
    out = BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


@minutes_bp.post("/transcripts/<int:tid>/minutes/signature")
def minutes_signature_save(tid: int):
    row = _get_tr(tid)
    try:
        if request.files.get("file") and request.files["file"].filename:
            raw = request.files["file"].read()
        else:
            data_url = request.form.get("data") or ""
            if "," not in data_url:
                raise ValueError("Data tanda tangan tidak valid.")
            raw = base64.b64decode(data_url.split(",", 1)[1])
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("Ukuran gambar maksimal 5 MB.")
        png = _process_signature(raw)
    except Exception as e:
        log.warning(f"Tanda tangan ditolak: {e}")
        return jsonify(ok=False, error=str(e)), 400

    fname = f"ttd_{tid}_{int(time.time())}.png"
    (UPLOAD_DIR / fname).write_bytes(png)

    meta = _load_meta(row["minutes_meta"])
    meta["ttd_image"] = f"/uploads/{fname}"
    meta["ttd_signed_at"] = datetime.now().strftime("%d-%m-%Y %H:%M")
    _save_meta(tid, meta)
    return jsonify(ok=True, url=meta["ttd_image"])


@minutes_bp.post("/transcripts/<int:tid>/minutes/signature/delete")
def minutes_signature_delete(tid: int):
    row = _get_tr(tid)
    meta = _load_meta(row["minutes_meta"])
    old = meta.get("ttd_image") or ""
    if old.startswith("/uploads/"):
        try:
            (UPLOAD_DIR / old.split("/uploads/", 1)[1]).unlink(missing_ok=True)
        except Exception:
            pass
    meta["ttd_image"] = ""
    meta["ttd_signed_at"] = ""
    _save_meta(tid, meta)
    flash("Tanda tangan digital dihapus.")
    return redirect(url_for("minutes_bp.minutes_edit", tid=tid) + "#ttd")


@minutes_bp.get("/transcripts/<int:tid>/minutes.docx")
def minutes_docx(tid: int):
    row = _get_tr(tid)
    meta = _load_meta(row["minutes_meta"])
    data = build_minutes_data(dict(row), meta)
    try:
        bio = build_docx_from_minutes(data)
    except Exception as e:
        log.exception("Gagal membuat DOCX")
        abort(500, description=str(e))

    safe_prog = "".join(c for c in (row["program"] or "Notulen") if c not in '\\/:*?"<>|')
    date_part = (row["created_at"] or "")[:10]
    return send_file(
        bio, as_attachment=True, download_name=f"Notulen - {safe_prog} - {date_part}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
