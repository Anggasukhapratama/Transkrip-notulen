from flask import render_template, abort, redirect, url_for, flash, request
# Impor relatif dari package routes
from . import editor_bp
# Impor relatif dari package sebayu_app
from ..database import get_db

# ====== Editor Transkrip untuk Cetak (opsional) ======
@editor_bp.get("/transcripts/<int:tid>/edit")
def transcript_edit(tid: int):
    with get_db() as db:
        row = db.execute(
            "SELECT id, program, filename, created_at, transcript, COALESCE(transcript_html,'') transcript_html "
            "FROM transcripts WHERE id=?",
            (tid,),
        ).fetchone()
    if not row: abort(404)

    html = row["transcript_html"]
    if not html:
        paras = []
        for line in row["transcript"].splitlines():
            line = line.strip()
            paras.append(f"<p>{line or '&nbsp;'}</p>")
        html = "\n".join(paras)
    return render_template("transcript_edit.html", tr=row, html=html)

@editor_bp.post("/transcripts/<int:tid>/edit")
def transcript_edit_save(tid: int):
    html = (request.form.get("html") or "").strip()
    if not html:
        flash("Konten kosong, tidak disimpan.")
        return redirect(url_for("editor_bp.transcript_edit", tid=tid))
    with get_db() as db:
        db.execute("UPDATE transcripts SET transcript_html=? WHERE id=?", (html, tid))
        db.commit() # Commit perubahan
    flash("Perubahan disimpan.")
    return redirect(url_for("transcription.transcript_detail", tid=tid))