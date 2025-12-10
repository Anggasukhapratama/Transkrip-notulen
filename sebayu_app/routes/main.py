from flask import render_template, send_from_directory
# Impor relatif dari package routes
from . import main_bp
# Impor relatif dari package sebayu_app
from ..database import get_db, current_program
from ..config import UPLOAD_DIR

@main_bp.route("/")
def index():
    with get_db() as db:
        trs = db.execute("SELECT id, program, filename, created_at FROM transcripts ORDER BY id DESC LIMIT 8").fetchall()
        reqs = db.execute("SELECT username, platform, message, status, created_at FROM requests ORDER BY id DESC LIMIT 8").fetchall()
    cp = current_program()
    return render_template("index.html", transcripts=trs, reqs=reqs, cp=cp)

@main_bp.route("/transcripts")
def transcripts():
    with get_db() as db:
        rows = db.execute("SELECT id, program, filename, created_at FROM transcripts ORDER BY id DESC").fetchall()
    return render_template("transcripts.html", rows=rows)

@main_bp.route("/requests")
def requests_view():
    with get_db() as db:
        rows = db.execute("SELECT username, platform, message, status, created_at FROM requests ORDER BY id DESC").fetchall()
    return render_template("requests.html", rows=rows)

# Perhatikan UPLOAD_DIR di config.py sudah diubah ke parent folder
@main_bp.route("/uploads/<path:fname>")
def serve_upload(fname: str):
    return send_from_directory(UPLOAD_DIR, fname)