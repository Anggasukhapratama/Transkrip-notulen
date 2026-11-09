from flask import render_template, send_from_directory, jsonify
from . import main_bp
from ..database import get_db, current_program
from ..config import UPLOAD_DIR
from ..stt import engine_info


@main_bp.route("/")
def index():
    with get_db() as db:
        trs = db.execute("SELECT id, program, filename, created_at FROM transcripts ORDER BY id DESC LIMIT 8").fetchall()
        total = db.execute("SELECT COUNT(*) AS c FROM transcripts").fetchone()["c"]
    return render_template("index.html", transcripts=trs, total=total, cp=current_program(), engine=engine_info())


@main_bp.route("/api/engine")
def api_engine():
    return jsonify(engine_info())


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


@main_bp.route("/uploads/<path:fname>")
def serve_upload(fname: str):
    return send_from_directory(UPLOAD_DIR, fname)
