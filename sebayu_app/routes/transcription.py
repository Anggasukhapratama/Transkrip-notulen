# sebayu_app/routes/transcription.py
import json
import threading
import time
import uuid
from flask import request, redirect, url_for, flash, render_template, abort, Response
from werkzeug.utils import secure_filename

from . import transcription_bp
from ..config import UPLOAD_DIR, PROGRESS, log
from ..database import get_db
from ..utils import allowed_file, run_transcribe_job
from ..textclean import clean_text_id


@transcription_bp.route("/transcribe", methods=["POST"])
def transcribe():
    f = request.files.get("audio")
    if not f or f.filename == "":
        flash("Pilih file audio terlebih dahulu.")
        return redirect(url_for("main.index"))
    if not allowed_file(f.filename):
        flash("Format file tidak didukung.")
        return redirect(url_for("main.index"))

    program = (request.form.get("program") or "Tanpa Nama").strip()
    mode = request.form.get("mode") or "auto"
    manual_choice = request.form.get("model_choice") or "small"
    device = request.form.get("device") or "auto"          # auto | cpu | cuda
    quality = request.form.get("quality") or "fast"        # fast | accurate
    do_summary = request.form.get("summary") == "on"

    fname = f"{int(time.time())}_{secure_filename(f.filename)}"
    save_path = UPLOAD_DIR / fname
    f.save(save_path)

    job_id = str(uuid.uuid4())
    PROGRESS[job_id] = {"pct": 5, "msg": "Unggahan diterima", "done": False, "error": None, "tid": None}
    threading.Thread(
        target=run_transcribe_job,
        args=(job_id, save_path, program, mode, manual_choice, device, quality, do_summary),
        daemon=True,
    ).start()
    return redirect(url_for("transcription.progress_page", job_id=job_id))


@transcription_bp.route("/transcripts/<int:tid>")
def transcript_detail(tid: int):
    with get_db() as db:
        row = db.execute(
            "SELECT id, program, filename, transcript, created_at, "
            "COALESCE(summary,'') summary, COALESCE(cleaned_transcript,'') cleaned_transcript "
            "FROM transcripts WHERE id= ?",
            (tid,),
        ).fetchone()
    if not row:
        abort(404)
    return render_template("transcript_detail.html", tr=row)


# --- Halaman Progres + SSE ---
@transcription_bp.get("/progress/<job_id>")
def progress_page(job_id: str):
    if job_id not in PROGRESS:
        PROGRESS[job_id] = {"pct": 0, "msg": "Menyiapkan…", "done": False, "error": None, "tid": None}
    return render_template("progress.html", job_id=job_id)


@transcription_bp.get("/events/<job_id>")
def events(job_id: str):
    def stream():
        while True:
            state = PROGRESS.get(job_id) or {"pct": 0, "msg": "Menunggu…", "done": False}
            yield f"data: {json.dumps(state)}\n\n"
            if state.get("done"):
                break
            time.sleep(1)
    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


@transcription_bp.post("/transcripts/<int:tid>/clean")
def transcript_clean(tid: int):
    from ..ai_refine import clean_transcript_with_ai, refine_minutes_with_ai
    from ..config import DEFAULT_META
    with get_db() as db:
        row = db.execute("SELECT program, transcript, COALESCE(minutes_meta,'') minutes_meta FROM transcripts WHERE id=?", (tid,)).fetchone()
        if not row:
            abort(404)
        cleaned = clean_transcript_with_ai(row["transcript"]) if row["transcript"] else ""
        ai_min = refine_minutes_with_ai(cleaned or row["transcript"], row["program"])
        meta = DEFAULT_META.copy()
        if row["minutes_meta"]:
            try:
                meta.update(json.loads(row["minutes_meta"]))
            except Exception:
                pass
        if ai_min:
            meta["_ai_minutes"] = ai_min
            summary = ai_min.get("ringkasan") or None
            db.execute(
                "UPDATE transcripts SET cleaned_transcript=?, summary=COALESCE(?, summary), minutes_meta=? WHERE id=?",
                (cleaned, summary, json.dumps(meta, ensure_ascii=False), tid),
            )
        else:
            db.execute("UPDATE transcripts SET cleaned_transcript=? WHERE id=?", (cleaned, tid))
        db.commit()
    flash("Transkrip & poin notulen berhasil diperbaiki dengan AI.")
    return redirect(url_for("transcription.transcript_detail", tid=tid))


@transcription_bp.post("/transcripts/<int:tid>/delete")
def transcript_delete(tid: int):
    with get_db() as db:
        row = db.execute("SELECT filename FROM transcripts WHERE id=?", (tid,)).fetchone()
        if not row:
            abort(404)
        try:
            fpath = UPLOAD_DIR / row["filename"]
            if fpath.exists():
                fpath.unlink()
        except Exception as e:
            log.warning(f"Gagal hapus file audio: {e}")
        db.execute("DELETE FROM transcripts WHERE id=?", (tid,))
        db.commit()
    flash("Transkrip berhasil dihapus.")
    return redirect(url_for("main.index"))
