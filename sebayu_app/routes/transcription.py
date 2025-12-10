# sebayu_app/routes/transcription.py
import threading
import uuid
from flask import request, redirect, url_for, flash, render_template, abort, Response, jsonify
import json
from werkzeug.utils import secure_filename

from . import transcription_bp
from ..config import UPLOAD_DIR, ALLOWED_AUDIO, PROGRESS
from ..database import get_db
from ..utils import allowed_file, run_transcribe_job
from ..textclean import clean_text_id  # <--- DITAMBAHKAN

@transcription_bp.route("/transcribe", methods=["POST"])
def transcribe():
    if not request.files.get("audio"):
        flash("Pilih file audio terlebih dahulu."); return redirect(url_for("main.index"))
    program = (request.form.get("program") or "Tanpa Nama").strip()
    mode = request.form.get("mode") or "auto"
    manual_choice = request.form.get("model_choice") or "small"
    do_chunk = True if request.form.get("chunk") == "on" else False
    do_summary = True if request.form.get("summary") == "on" else False

    f = request.files["audio"]
    if f.filename == "":
        flash("Nama file kosong."); return redirect(url_for("main.index"))
    if not allowed_file(f.filename):
        flash("Format file tidak didukung."); return redirect(url_for("main.index"))

    fname = secure_filename(f.filename)
    save_path = UPLOAD_DIR / fname
    f.save(save_path)

    job_id = str(uuid.uuid4())
    PROGRESS[job_id] = {"pct": 5, "msg": "Unggahan diterima", "done": False, "error": None, "tid": None}
    t = threading.Thread(
        target=run_transcribe_job,
        args=(job_id, save_path, program, mode, manual_choice, do_chunk, do_summary),
        daemon=True
    ); t.start()
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
    if not row: abort(404)
    return render_template("transcript_detail.html", tr=row)

# --- Halaman Progres + SSE ---
@transcription_bp.get("/progress/<job_id>")
def progress_page(job_id: str):
    if job_id not in PROGRESS:
        PROGRESS[job_id] = {"pct":0,"msg":"Menyiapkan…","done":False,"error":None,"tid":None}
    return render_template("progress.html", job_id=job_id)

@transcription_bp.get("/events/<job_id>")
def events(job_id: str):
    def stream():
        while True:
            state = PROGRESS.get(job_id) or {"pct":0,"msg":"Menunggu…","done":False}
            yield f"data: {json.dumps(state)}\n\n"
            import time; time.sleep(1)
    return Response(stream(), mimetype="text/event-stream")

# --- Tambahan: tombol bersihkan manual ---
@transcription_bp.post("/transcripts/<int:tid>/clean")
def transcript_clean(tid: int):
    with get_db() as db:
        row = db.execute("SELECT transcript FROM transcripts WHERE id=?", (tid,)).fetchone()
        if not row:
            abort(404)
        cleaned = clean_text_id(row["transcript"]) if row["transcript"] else ""
        db.execute("UPDATE transcripts SET cleaned_transcript=? WHERE id=?", (cleaned, tid))
        db.commit()
    flash("Transkrip dibersihkan.")
    return redirect(url_for("transcription.transcript_detail", tid=tid))

@transcription_bp.post("/transcripts/<int:tid>/delete")
def transcript_delete(tid: int):
    with get_db() as db:
        row = db.execute(
            "SELECT filename FROM transcripts WHERE id=?", (tid,)
        ).fetchone()
        if not row:
            abort(404)

        # hapus file audio asli dari folder uploads (kalau masih ada)
        try:
            fpath = UPLOAD_DIR / row["filename"]
            if fpath.exists():
                fpath.unlink()
        except Exception as e:
            log.warning(f"Gagal hapus file audio: {e}")

        # hapus row dari database
        db.execute("DELETE FROM transcripts WHERE id=?", (tid,))
        db.commit()

    flash("Transkrip berhasil dihapus.")
    return redirect(url_for("main.index"))
