from flask import Blueprint

# Buat objek Blueprint
main_bp = Blueprint("main", __name__)
transcription_bp = Blueprint("transcription", __name__)
minutes_bp = Blueprint("minutes_bp", __name__) # Ubah nama variabel blueprint
editor_bp = Blueprint("editor_bp", __name__)   # Ubah nama variabel blueprint

# Import rute-rute agar terdaftar pada Blueprint
from . import main, transcription, minutes, editor