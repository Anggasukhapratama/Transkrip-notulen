import os
from flask import Flask
from datetime import datetime
from pathlib import Path

def create_app():
    # Import konfigurasi dari modul lokal di dalam package
    # Sekarang kita butuh PROJECT_ROOT dari config.py juga untuk template/static folders
    from .config import INSTANCE_DIR, UPLOAD_DIR, log, PROJECT_ROOT

    # Tidak perlu menghitung template_folder_path dan static_folder_path lagi di sini
    # karena kita sudah punya PROJECT_ROOT di config.py
    app = Flask(
        __name__,
        instance_path=str(INSTANCE_DIR),          # Gunakan INSTANCE_DIR dari config
        template_folder=str(PROJECT_ROOT / "templates"), # Path template di root proyek
        static_folder=str(PROJECT_ROOT / "static")       # Path static di root proyek
    )
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)

    # Expose now() untuk template Jinja
    app.jinja_env.globals['now'] = datetime.now

    # Import blueprints dari modul routes di dalam package
    from .routes import (
        main_bp,
        transcription_bp,
        minutes_bp,
        editor_bp,
    )

    # Daftarkan Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(transcription_bp)
    app.register_blueprint(minutes_bp)
    app.register_blueprint(editor_bp)


    # Inisialisasi database saat aplikasi dibuat
    from .database import init_db
    with app.app_context():
        init_db()

    log.info("Flask app instance created and blueprints registered.")
    return app