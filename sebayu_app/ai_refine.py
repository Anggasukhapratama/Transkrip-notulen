# sebayu_app/ai_refine.py
"""
Modul Koreksi AI untuk:
  1. Memperbaiki typo/kesalahan dengar hasil transkrip Whisper menjadi Bahasa Indonesia yang rapi & baku.
  2. Menyusun & merapikan isi Notulen Rapat (Pokok Pembahasan, Arahan, Isu/Kendala, Keputusan, Tindak Lanjut + PIC & Tenggat)
     menggunakan AI secara otomatis.

Mendukung:
  - GROQ_API_KEY (jika diset di environment, memakai llama-3.3-70b-versatile)
  - OPENAI_API_KEY (jika diset di environment, memakai gpt-4o-mini)
  - Built-in Free AI (otomatis aktif tanpa API key melalui endpoint OpenAI-compatible Pollinations)
"""
import json
import os
import re
import requests
from typing import Optional

from .config import log
from .textclean import clean_text_id


def _call_llm(messages: list[dict], timeout: int = 45) -> str:
    """Panggil LLM (Groq -> OpenAI -> Free Built-in AI)."""
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    endpoints = []
    if groq_key:
        for groq_model in ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"):
            endpoints.append((
                "https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": f"Bearer {groq_key}"},
                groq_model,
            ))
    if openai_key:
        endpoints.append((
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {openai_key}"},
            "gpt-4o-mini",
        ))
    # Default gratis tanpa API key
    endpoints.append((
        "https://text.pollinations.ai/openai",
        {},
        "openai",
    ))

    last_err = None
    for url, headers, model in endpoints:
        try:
            resp = requests.post(
                url,
                headers=headers,
                json={"model": model, "messages": messages, "temperature": 0.2},
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            content = content.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
            if content.strip():
                return content.strip()
        except Exception as e:
            last_err = e
            log.warning(f"[ai_refine] endpoint {url} gagal: {e}")
    raise RuntimeError(f"Gagal menghubungi layanan AI: {last_err}")


def _extract_json_obj(raw: str) -> dict:
    """Ambil objek JSON dari respons teks LLM."""
    raw = (raw or "").strip()
    # Hilangkan blok markdown ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.S)
    if m:
        raw = m.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]
    return json.loads(raw)


def clean_transcript_with_ai(raw_transcript: str) -> str:
    """
    Perbaiki kesalahan kata/typo hasil Speech-to-Text (Whisper) menjadi
    paragraf Bahasa Indonesia yang rapi dan mudah dibaca.
    """
    text = (raw_transcript or "").strip()
    if not text:
        return ""

    # Bersihkan filler dasar terlebih dahulu
    base_cleaned = clean_text_id(text, aggressive=False)
    # Potong per bagian bila sangat panjang (maks ~6000 karakter per panggilan)
    chunk = base_cleaned[:7000]

    prompt = (
        "Kamu adalah editor transkrip rapat profesional Bahasa Indonesia.\n"
        "Tugasmu adalah memperbaiki kata-kata yang salah dengar/typo akibat Speech-to-Text (misalnya 'kordanesai' -> 'koordinasi', "
        "'memyodiskan' -> 'memutuskan', 'di karanji sepulah person' -> 'dikurangi sepuluh persen'), memperbaiki tanda baca, "
        "dan menghapus kata gumaman (eh, anu, gitu) TANPA mengubah makna atau menghilangkan informasi rapat.\n"
        "Keluarkan HANYA teks transkrip yang sudah rapi dalam paragraf Bahasa Indonesia, tanpa komentar tambahan."
    )
    try:
        res = _call_llm(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": chunk},
            ],
            timeout=45,
        )
        if res and len(res.strip()) >= max(10, len(chunk) // 5):
            return res.strip()
    except Exception as e:
        log.warning(f"[ai_refine] clean_transcript_with_ai fallback ke lokal: {e}")

    return clean_text_id(text, aggressive=True)


def refine_minutes_with_ai(transcript: str, program: str = "") -> Optional[dict]:
    """
    Susun dan rapikan poin-poin Notulen Rapat dari transkrip menggunakan AI.
    Mengembalikan dict dengan key:
      - ringkasan: str (bullet points)
      - pembahasan: list[str]
      - arahan: list[str]
      - isu: list[str]
      - keputusan: list[str]
      - tindak_lanjut: list[dict(text, pic, due)]
    """
    text = (transcript or "").strip()
    if not text or len(text.split()) < 4:
        return None

    snippet = text[:8000]
    sys_prompt = (
        "Kamu adalah Notulis Rapat Resmi Pemerintah/Instansi Indonesia.\n"
        "Berdasarkan teks transkrip rapat yang diberikan (yang mungkin mengandung salah ketik/dengar dari mesin transkrip suara), "
        "koreksi kata-kata yang typo berdasarkan konteksnya, lalu susun menjadi Notulen Rapat Resmi dengan bahasa Indonesia baku, jelas, dan formal.\n"
        "Keluarkan HANYA JSON valid (tanpa markdown/penjelasan) dengan struktur persis berikut:\n"
        "{\n"
        '  "ringkasan": "- Poin ringkasan 1\\n- Poin ringkasan 2",\n'
        '  "pembahasan": ["Kalimat baku pokok pembahasan 1.", "Kalimat baku pokok pembahasan 2."],\n'
        '  "arahan": ["Kalimat baku arahan pimpinan (kosongkan [] jika tidak ada)."],\n'
        '  "isu": ["Kalimat baku isu/kendala yang dibahas (kosongkan [] jika tidak ada)."],\n'
        '  "keputusan": ["Kalimat baku keputusan rapat yang disepakati/diputuskan."],\n'
        '  "tindak_lanjut": [\n'
        '    {"text": "Uraian tugas/tindak lanjut secara baku.", "pic": "Nama/Bagian Penanggung Jawab atau -", "due": "Batas waktu atau -"}\n'
        "  ]\n"
        "}"
    )
    user_msg = f"Nama Rapat/Acara: {program or 'Rapat Koordinasi'}\n\nTranskrip Rapat:\n{snippet}"

    try:
        raw = _call_llm(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_msg},
            ],
            timeout=50,
        )
        obj = _extract_json_obj(raw)

        def _str_list(val) -> list[str]:
            if isinstance(val, str) and val.strip():
                return [val.strip()]
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
            return []

        tl_raw = obj.get("tindak_lanjut") or []
        tl_clean = []
        if isinstance(tl_raw, list):
            for item in tl_raw:
                if isinstance(item, dict) and str(item.get("text") or "").strip():
                    tl_clean.append({
                        "text": str(item.get("text")).strip(),
                        "pic": str(item.get("pic") or "-").strip() or "-",
                        "due": str(item.get("due") or "-").strip() or "-",
                    })
                elif isinstance(item, str) and item.strip():
                    tl_clean.append({"text": item.strip(), "pic": "-", "due": "-"})

        ringkasan = obj.get("ringkasan") or ""
        if isinstance(ringkasan, list):
            ringkasan = "\n".join(f"- {str(x).lstrip('-• ')}" for x in ringkasan if str(x).strip())

        result = {
            "ringkasan": str(ringkasan).strip(),
            "pembahasan": _str_list(obj.get("pembahasan")),
            "arahan": _str_list(obj.get("arahan")),
            "isu": _str_list(obj.get("isu")),
            "keputusan": _str_list(obj.get("keputusan")),
            "tindak_lanjut": tl_clean,
        }
        # Pastikan minimal ada 1 bagian terisi
        if any(result[k] for k in ("pembahasan", "arahan", "isu", "keputusan", "tindak_lanjut")):
            return result
    except Exception as e:
        log.warning(f"[ai_refine] refine_minutes_with_ai gagal: {e}")
    return None
