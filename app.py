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
    log.info("Starting Flask app from root app.py...")
    app.run(debug=debug, use_reloader=False, threaded=True, port=int(os.environ.get("PORT", 5000)))
