# sebayu_app/utils.py
import requests
from pathlib import Path

from .config import ALLOWED_AUDIO, log, PROGRESS
from .database import get_db, now_str, current_program, get_today_schedule_text
from .textclean import clean_text_id  # Cleaner terintegrasi
from .stt import transcribe_file, engine_info  # noqa: F401  (CPU/GPU)
from .notulen import (  # noqa: F401  (diekspor untuk route)
    local_summarize_bullets, build_minutes_data, build_docx_from_minutes,
)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_AUDIO


# ====================== CHAT BOT JADWAL / REQUEST ======================

def get_now_playing() -> str:
    try:
        resp = requests.get("https://admin.sebayu.my.id/api/nowplaying/sebayu", timeout=6)
        data = resp.json()
        song = data["now_playing"]["song"]
        artist = song.get("artist", "")
        title = song.get("title", "")
        live = data["now_playing"].get("live")
        listeners = data.get("listeners", {}).get("current", 0)
        if live and live.get("is_live", False):
            return f"🎙️ Sedang live oleh {live.get('streamer_name', 'penyiar')} – memutar {title} {artist}".strip()
        return f"🎶 Sekarang memutar: {title} {artist} | 👥 {listeners} pendengar".strip()
    except Exception as e:
        return f"[Gagal ambil status: {e}]"


def set_progress(job_id: str, pct: int, msg: str, *, done: bool = False, error: str | None = None, tid: int | None = None):
    PROGRESS[job_id] = {"pct": int(pct), "msg": msg, "done": done, "error": error, "tid": tid}
    log.info(f"[{job_id}] {pct}% {msg}")


def run_transcribe_job(job_id: str, save_path: Path, program: str, mode: str, manual_choice: str,
                       device: str, quality: str, do_summary: bool):
    try:
        set_progress(job_id, 10, "Mulai proses")
        full_text = transcribe_file(
            save_path, mode=mode, manual_choice=manual_choice, device=device, quality=quality,
            progress=lambda p, m: set_progress(job_id, p, m),
        )
        if not full_text.strip():
            raise RuntimeError("Tidak ada ucapan terdeteksi pada audio.")

        summary_text = None
        if do_summary:
            set_progress(job_id, 92, "Merangkum (lokal)…")
            try:
                summary_text = local_summarize_bullets(full_text)
            except Exception as e:
                summary_text = f"[Gagal merangkum: {e}]"

        set_progress(job_id, 96, "Membersihkan teks")
        try:
            cleaned = clean_text_id(full_text)
        except Exception as e:
            log.warning(f"Gagal membersihkan teks: {e}")
            cleaned = None

        set_progress(job_id, 98, "Menyimpan ke database")
        with get_db() as db:
            cur = db.execute(
                "INSERT INTO transcripts(program, filename, transcript, created_at, summary, cleaned_transcript) "
                "VALUES(?,?,?,?,?,?)",
                (program, save_path.name, full_text, now_str(), summary_text, cleaned),
            )
            tid = cur.lastrowid
            db.commit()

        set_progress(job_id, 100, "Selesai", done=True, tid=tid)
    except Exception as e:
        log.exception("Transcribe job error")
        set_progress(job_id, 100, f"Gagal: {e}", done=True, error=str(e))


def handle_chat_message(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "Halo! Ketik 'jadwal', 'siaran', 'lagu sekarang', atau 'request Judul - Artis'."
    lower = t.lower()
    if lower in {"help", "bantuan", "/start"}:
        return (
            "Perintah yang tersedia:\n"
            "• jadwal — Lihat jadwal siaran hari ini\n"
            "• siaran — Info program terjadwal sekarang\n"
            "• lagu sekarang / status — Info lagu real-time dari Azuracast\n"
            "• request Judul - Artis — Kirim request lagu\n"
            "• help — Bantuan"
        )
    if "jadwal" in lower:
        return get_today_schedule_text()
    if "siaran" in lower:
        cp = current_program()
        if cp:
            prog, host = cp
            host_s = f" oleh {host}" if host else ""
            return f"📻 Program terjadwal sekarang: {prog}{host_s}"
        return "Tidak ada program terjadwal saat ini."
    if "lagu" in lower or "status" in lower:
        return get_now_playing()
    if lower.startswith("request ") or lower.startswith("req "):
        return "Oke, aku catat. (Akan tersimpan saat kamu kirim.)"
    return "Maaf, aku belum paham. Ketik 'help' untuk bantuan."

