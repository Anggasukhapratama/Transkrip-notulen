# my_flask_app/sebayu_app/database.py
import sqlite3
from .config import DB_PATH, log
from datetime import datetime

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS transcripts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  program TEXT NOT NULL,
  filename TEXT NOT NULL,
  transcript TEXT NOT NULL,
  created_at TEXT NOT NULL,
  summary TEXT,
  transcript_html TEXT,
  minutes_meta TEXT,
  cleaned_transcript TEXT           -- ← kolom baru untuk teks bersih (boleh null)
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  platform TEXT NOT NULL,
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'baru',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedule (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  day_of_week INTEGER NOT NULL, -- 0=Senin ... 6=Minggu
  start_time TEXT NOT NULL,     -- HH:MM
  end_time TEXT NOT NULL,       -- HH:MM
  program TEXT NOT NULL,
  host TEXT
);
"""

def init_db():
    with get_db() as db:
        db.executescript(SCHEMA_SQL)
        # kolom tambahan (aman bila sudah ada)
        for alter in [
            "ALTER TABLE transcripts ADD COLUMN summary TEXT",
            "ALTER TABLE transcripts ADD COLUMN transcript_html TEXT",
            "ALTER TABLE transcripts ADD COLUMN minutes_meta TEXT",
            "ALTER TABLE transcripts ADD COLUMN cleaned_transcript TEXT",  # ← penting
        ]:
            try:
                db.execute(alter)
            except Exception:
                pass

        # seed jadwal jika kosong
        c = db.execute("SELECT COUNT(*) AS c FROM schedule").fetchone()["c"]
        if c == 0:
            seed = [
                (0, "06:00", "08:00", "Berita Pagi", "Dina"),
                (0, "08:00", "10:00", "Musik Santai", "Rama"),
                (1, "18:00", "20:00", "Relaks Malam", "Naya"),
                (5, "09:00", "11:00", "Sabtu Ceria", "Guest DJ"),
            ]
            db.executemany(
                "INSERT INTO schedule(day_of_week,start_time,end_time,program,host) VALUES(?,?,?,?,?)",
                seed,
            )
        db.commit()

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def current_program(dt: datetime = None) -> tuple[str, str] | None:
    dt = dt or datetime.now()
    dow = dt.weekday()
    hhmm = dt.strftime("%H:%M")
    with get_db() as db:
        rows = db.execute(
            "SELECT program, host, start_time, end_time FROM schedule WHERE day_of_week=?",
            (dow,),
        ).fetchall()
    for r in rows:
        if r["start_time"] <= hhmm < r["end_time"]:
            return (r["program"], r["host"] or "")
    return None

def get_today_schedule_text() -> str:
    dow = datetime.now().weekday()
    hari = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"][dow]
    with get_db() as db:
        rows = db.execute(
            "SELECT start_time, end_time, program, COALESCE(host,'') host FROM schedule WHERE day_of_week=? ORDER BY start_time",
            (dow,),
        ).fetchall()
    if not rows: return f"{hari}: belum ada jadwal."
    lines = [f"Jadwal {hari}:"]
    for r in rows:
        host = f" (host: {r['host']})" if r["host"] else ""
        lines.append(f"{r['start_time']}-{r['end_time']}: {r['program']}{host}")
    return "\n".join(lines)
