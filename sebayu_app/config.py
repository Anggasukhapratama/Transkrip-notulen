# my_flask_app/sebayu_app/config.py
import os
from pathlib import Path
from datetime import datetime
import logging
import sys

# --- Config dasar ---
_APP_PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _APP_PACKAGE_DIR.parent

INSTANCE_DIR = PROJECT_ROOT / "instance"
UPLOAD_DIR = PROJECT_ROOT / "uploads"
DB_PATH = INSTANCE_DIR / "sebayu.db"

ALLOWED_AUDIO = {"wav", "mp3", "m4a", "aac", "flac", "ogg"}
ALLOWED_IMG = {"png", "jpg", "jpeg", "gif", "webp"}

INSTANCE_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

WHISPER_DEVICE  = os.environ.get("WHISPER_DEVICE", "auto")       # auto|cuda|cpu
WHISPER_COMPUTE = os.environ.get("WHISPER_COMPUTE", "float16")   # float16|int8_float16|int8

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

try:
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    HAVE_DOCX = True
except Exception:
    HAVE_DOCX = False

# ==== Default meta header (editable) ====
DEFAULT_META = {
    "instansi": "PEMERINTAH KOTA TEGAL\nSEKRETARIAT DPRD",
    "alamat": "Jl. Pemuda No. 4 Tegal • Telp/Faks (0283) 321506 Kode Pos 52111",
    "judul": "Notulen Rapat",
    "nomor": "",
    "hari": "",
    "tanggal": "",
    "waktu": "",
    "tempat": "",
    "pimpinan": "",
    "notulis": "",
    "logo": "",
    "kop_html": "",
    # === BARU: Field untuk tanda tangan yang lebih detail ===
    "ttd_jabatan": "SEKRETARIS DPRD KOTA TEGAL",
    "ttd_nama": "",
    "ttd_pangkat": "", # Tambah field untuk Pangkat/Golongan
    "ttd_nip": "",     # Tambah field untuk NIP
    # === Kata kunci custom (opsional) ===
    "kw_keputusan": [],
    "kw_tindak_lanjut": [],
    "kw_isu": [],
    "kw_arahan": [],
    "kw_catatan": []
}

PROGRESS = {}