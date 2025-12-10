import os
# Import fungsi create_app dari package sebayu_app
from sebayu_app import create_app
# Import log dari config agar bisa digunakan di sini juga
from sebayu_app.config import log

# Panggil fungsi create_app untuk mendapatkan instance aplikasi Flask
app = create_app()

if __name__ == "__main__":
    # Contoh: PYTHONUNBUFFERED=1 LOG_LEVEL=INFO python -u app.py
    log.info("Starting Flask app from root app.py...")
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))