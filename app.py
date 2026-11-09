import os
# Import fungsi create_app dari package sebayu_app
from sebayu_app import create_app
# Import log dari config agar bisa digunakan di sini juga
from sebayu_app.config import log

# Panggil fungsi create_app untuk mendapatkan instance aplikasi Flask
app = create_app()

if __name__ == "__main__":
    # Reloader dimatikan: restart otomatis akan membunuh proses transkripsi yang sedang berjalan.
    # Aktifkan dengan FLASK_DEBUG=1 bila sedang mengembangkan.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    host = os.environ.get("HOST", "0.0.0.0")
    default_port = 7860 if (os.environ.get("SPACE_ID") or os.environ.get("GRADIO_SERVER_PORT")) else 5000
    port = int(os.environ.get("PORT") or os.environ.get("GRADIO_SERVER_PORT") or default_port)
    log.info(f"Starting Flask app on {host}:{port} ...")
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
