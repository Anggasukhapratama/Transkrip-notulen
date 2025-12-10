# my_flask_app/sebayu_app/routes/minutes.py
import json
import time
from flask import render_template, abort, redirect, url_for, flash, request, send_file
from werkzeug.utils import secure_filename

from . import minutes_bp
from ..database import get_db
from ..config import DEFAULT_META, UPLOAD_DIR, ALLOWED_IMG, log
from ..utils import build_minutes_gpt, build_docx_from_minutes


@minutes_bp.get("/transcripts/<int:tid>/minutes")
def transcript_minutes(tid: int):
    with get_db() as db:
        row = db.execute(
            "SELECT id, program, filename, "
            "COALESCE(cleaned_transcript, transcript) AS transcript, "
            "created_at, COALESCE(summary,'') summary, COALESCE(minutes_meta,'') minutes_meta "
            "FROM transcripts WHERE id=?",
            (tid,),
        ).fetchone()
    if not row:
        abort(404)

    meta = DEFAULT_META.copy()
    raw_meta = row["minutes_meta"]
    if raw_meta:
        try:
            meta.update(json.loads(raw_meta))
        except Exception:
            pass

    minutes = build_minutes_gpt(row["transcript"], row["summary"], row["program"], row["created_at"], meta=meta)

    # Tidak ada lagi override hasil koreksi AI: murni klasifikasi lokal
    return render_template("minutes.html", tr=row, minutes=minutes, meta=meta)


@minutes_bp.get("/transcripts/<int:tid>/minutes/edit")
def minutes_edit(tid: int):
    with get_db() as db:
        row = db.execute(
            "SELECT id, program, created_at, COALESCE(minutes_meta,'') minutes_meta FROM transcripts WHERE id=?",
            (tid,),
        ).fetchone()
    if not row:
        abort(404)
    meta = DEFAULT_META.copy()
    if row["minutes_meta"]:
        try:
            meta.update(json.loads(row["minutes_meta"]))
        except Exception:
            pass

    logo_qs = request.args.get("logo")
    if logo_qs:
        meta["logo"] = logo_qs

    return render_template("minutes_edit.html", tid=tid, meta=meta)


@minutes_bp.post("/transcripts/<int:tid>/minutes/edit")
def minutes_edit_save(tid: int):
    fields = [
        "instansi", "alamat", "judul", "nomor", "hari", "tanggal", "waktu",
        "tempat", "pimpinan", "notulis", "logo", "kop_html",
        "ttd_jabatan", "ttd_nama", "ttd_pangkat", "ttd_nip"
    ]
    meta = {k: (request.form.get(k) or "").strip() for k in fields}
    try:
        for key in ["kw_keputusan", "kw_tindak_lanjut", "kw_isu", "kw_arahan", "kw_catatan"]:
            raw = (request.form.get(key) or "").strip()
            if raw:
                try:
                    meta[key] = json.loads(raw)
                    if not isinstance(meta[key], list):
                        raise ValueError("Not a list")
                except (json.JSONDecodeError, ValueError):
                    meta[key] = [x.strip() for x in raw.split(",") if x.strip()]
    except Exception as e:
        log.warning(f"Kata kunci custom invalid: {e}")

    with get_db() as db:
        db.execute("UPDATE transcripts SET minutes_meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), tid))
        db.commit()
    flash("Header notulen disimpan.")
    return redirect(url_for("minutes_bp.transcript_minutes", tid=tid))


@minutes_bp.post("/minutes/logo")
def upload_logo():
    f = request.files.get("logo")
    redirect_to = request.form.get("redirect") or url_for("main.index")
    if not f or f.filename == "":
        flash("Pilih file logo terlebih dahulu.")
        return redirect(redirect_to)
    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMG:
        flash("Format logo harus gambar (png/jpg/jpeg/gif/webp).")
        return redirect(redirect_to)
    fname = secure_filename(f"logo_{int(time.time())}.{ext}")
    path = UPLOAD_DIR / fname
    f.save(path)
    flash("Logo terunggah.")
    return redirect(f"{redirect_to}?logo=/uploads/{fname}")


@minutes_bp.get("/transcripts/<int:tid>/minutes.docx")
def minutes_docx(tid: int):
    with get_db() as db:
        row = db.execute(
            "SELECT id, program, filename, "
            "COALESCE(cleaned_transcript, transcript) AS transcript, "
            "created_at, COALESCE(summary,'') summary, COALESCE(minutes_meta,'') minutes_meta "
            "FROM transcripts WHERE id=?",
            (tid,),
        ).fetchone()
    if not row:
        abort(404)
    meta = DEFAULT_META.copy()
    if row["minutes_meta"]:
        try:
            meta.update(json.loads(row["minutes_meta"]))
        except Exception:
            pass
    minutes = build_minutes_gpt(row["transcript"], row["summary"], row["program"], row["created_at"], meta=meta)
    try:
        bio = build_docx_from_minutes(minutes, meta, dict(row))
    except Exception as e:
        abort(500, description=str(e))

    safe_prog = (row["program"] or "Notulen").replace("/", "-")
    date_part = (row["created_at"] or "")[:10]
    fname = f"Notulen - {safe_prog} - {date_part}.docx"
    return send_file(
        bio, as_attachment=True, download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
