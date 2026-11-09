# sebayu_app/stt.py
"""
Mesin transkripsi (Speech-to-Text) yang mendukung CPU dan GPU (CUDA).

Prioritas backend:
  1. faster-whisper (CTranslate2)  -> jauh lebih cepat di CPU (int8) maupun GPU
  2. openai-whisper (PyTorch)      -> fallback bila faster-whisper belum terpasang

Fitur percepatan:
  - Model di-cache di memori (tidak di-load ulang tiap job)
  - VAD filter: bagian hening dilewati
  - Greedy decoding (beam=1) pada mode "cepat"
  - CPU memakai kuantisasi int8 + semua thread CPU
  - GPU otomatis dipakai bila tersedia; jika gagal otomatis turun ke CPU
"""
import os
import sys
import site
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from .config import log

ProgressFn = Optional[Callable[[int, str], None]]

_MODEL_LOCK = threading.Lock()
_MODELS: dict = {}
_GPU_BROKEN = {"flag": False, "reason": ""}
_GPU_INFO = {"name": "", "vram_mb": 0, "ready": False}

MODEL_ALIASES = {"large": "large-v3"}
VALID_MODELS = {"tiny", "base", "small", "medium", "large-v3"}

DOMAIN_PROMPT = "Notulen rapat. Agenda, pembahasan, keputusan, dan tindak lanjut."


# ---------------------------------------------------------------- utilitas GPU
def _register_nvidia_dll_dirs() -> None:
    """Jika cuBLAS/cuDNN dipasang via pip (paket nvidia-*), daftarkan folder DLL-nya."""
    if os.name != "nt":
        return
    roots = []
    try:
        roots += site.getsitepackages()
    except Exception:
        pass
    roots.append(str(Path(sys.prefix) / "Lib" / "site-packages"))
    for root in roots:
        nv = Path(root) / "nvidia"
        if not nv.is_dir():
            continue
        for b in nv.glob("*/bin"):
            try:
                os.add_dll_directory(str(b))
                os.environ["PATH"] = str(b) + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass


_register_nvidia_dll_dirs()


def _probe_gpu_info() -> None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=20,
        ).decode(errors="ignore").strip().splitlines()[0]
        name, mem = [x.strip() for x in out.split(",")[:2]]
        _GPU_INFO.update(name=name, vram_mb=int(float(mem)))
    except Exception:
        pass
    _GPU_INFO["ready"] = True


threading.Thread(target=_probe_gpu_info, daemon=True).start()


def have_faster_whisper() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def cuda_available() -> bool:
    if _GPU_BROKEN["flag"]:
        return False
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return True
    except Exception:
        pass
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def engine_info() -> dict:
    cuda = cuda_available()
    return {
        "backend": "faster-whisper" if have_faster_whisper() else "openai-whisper",
        "cuda": cuda,
        "gpu_name": _GPU_INFO["name"],
        "vram_mb": _GPU_INFO["vram_mb"],
        "gpu_detected": bool(_GPU_INFO["name"]),
        "gpu_broken_reason": _GPU_BROKEN["reason"],
        "cpu_threads": os.cpu_count() or 1,
    }


# ---------------------------------------------------------------- pemilihan model
def ffprobe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            stderr=subprocess.DEVNULL, timeout=30,
        ).decode().strip()
        return float(out)
    except Exception:
        return 0.0


def choose_model(duration_sec: float, mode: str, manual_choice: str, device: str) -> str:
    """Otomatis: sesuaikan dengan perangkat supaya cepat tapi tetap akurat."""
    manual_choice = MODEL_ALIASES.get(manual_choice, manual_choice)
    if mode == "manual" and manual_choice in VALID_MODELS:
        return manual_choice
    if device == "cuda":
        # medium butuh ~5GB VRAM (fp16) ; GPU kecil (<=4GB) pakai small
        return "medium" if _GPU_INFO["vram_mb"] >= 6000 else "small"
    # CPU: rekaman sangat panjang -> base agar tidak berjam-jam
    return "base" if duration_sec > 2700 else "small"


# ---------------------------------------------------------------- faster-whisper
def _compute_candidates(device: str, pref: str) -> list:
    if pref and pref != "auto":
        return [pref]
    if device == "cpu":
        return ["int8"]
    supported = set()
    try:
        import ctranslate2
        supported = set(ctranslate2.get_supported_compute_types("cuda"))
    except Exception:
        pass
    order = ["float16", "int8_float16", "int8", "float32"]
    cands = [c for c in order if not supported or c in supported]
    return cands or ["float32"]


def _load_faster(size: str, device: str, compute_pref: str):
    from faster_whisper import WhisperModel
    last_err = None
    for compute in _compute_candidates(device, compute_pref):
        key = ("fw", size, device, compute)
        if key in _MODELS:
            return _MODELS[key], compute
        try:
            kwargs = {"device": device, "compute_type": compute}
            if device == "cpu":
                kwargs["cpu_threads"] = os.cpu_count() or 4
            log.info(f"[stt] load faster-whisper model={size} device={device} compute={compute}")
            model = WhisperModel(size, **kwargs)
            _MODELS[key] = model
            return model, compute
        except Exception as e:  # compute type tidak didukung / DLL hilang / OOM
            last_err = e
            log.warning(f"[stt] gagal load ({device}/{compute}): {e}")
    raise RuntimeError(f"Tidak bisa memuat model {size} di {device}: {last_err}")


def _paragraphs(segments_iter, duration: float, progress: ProgressFn, base: int, span: int):
    """Gabungkan segmen jadi paragraf (jeda panjang = paragraf baru) sambil melapor progres."""
    paras, cur, prev_end = [], [], 0.0
    for seg in segments_iter:
        txt = (seg.text or "").strip()
        if not txt:
            continue
        gap = seg.start - prev_end
        if cur and (gap > 1.8 or sum(len(x) for x in cur) > 600):
            paras.append(" ".join(cur))
            cur = []
        cur.append(txt)
        prev_end = seg.end
        if progress and duration > 0:
            frac = min(1.0, seg.end / duration)
            progress(base + int(span * frac), f"Transkripsi {int(frac*100)}% ({int(seg.end//60):02d}:{int(seg.end%60):02d} / {int(duration//60):02d}:{int(duration%60):02d})")
    if cur:
        paras.append(" ".join(cur))
    return "\n".join(paras).strip()


def _run_faster(audio: Path, size: str, device: str, quality: str, progress: ProgressFn) -> str:
    from .config import WHISPER_COMPUTE
    with _MODEL_LOCK:
        model, compute = _load_faster(size, device, WHISPER_COMPUTE)
    if progress:
        progress(30, f"Model {size} siap ({device.upper()}, {compute})")

    beam = 5 if quality == "accurate" else 1
    segments, info = model.transcribe(
        str(audio),
        language="id",
        beam_size=beam,
        best_of=1,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 600},
        condition_on_previous_text=False,
        initial_prompt=DOMAIN_PROMPT,
    )
    duration = float(getattr(info, "duration", 0.0) or 0.0)
    return _paragraphs(segments, duration, progress, 32, 56)


# ---------------------------------------------------------------- openai-whisper (fallback)
def _run_openai(audio: Path, size: str, device: str, quality: str, progress: ProgressFn) -> str:
    import whisper  # type: ignore
    key = ("ow", size, device)
    with _MODEL_LOCK:
        if key not in _MODELS:
            log.info(f"[stt] load openai-whisper model={size} device={device}")
            _MODELS[key] = whisper.load_model(size, device=device)
        model = _MODELS[key]
    if progress:
        progress(35, f"Model {size} siap ({device.upper()}) – memproses audio…")
    result = model.transcribe(
        str(audio), language="id", initial_prompt=DOMAIN_PROMPT, verbose=None,
        fp16=(device == "cuda"), condition_on_previous_text=False,
        beam_size=5 if quality == "accurate" else None,
        best_of=None if quality != "accurate" else 5,
        temperature=0.0,
    )
    segs = result.get("segments") or []
    if not segs:
        return (result.get("text") or "").strip()
    paras, cur, prev_end = [], [], 0.0
    for s in segs:
        t = (s.get("text") or "").strip()
        if not t:
            continue
        if cur and (s["start"] - prev_end > 1.8 or sum(len(x) for x in cur) > 600):
            paras.append(" ".join(cur)); cur = []
        cur.append(t); prev_end = s["end"]
    if cur:
        paras.append(" ".join(cur))
    return "\n".join(paras).strip()


# ---------------------------------------------------------------- API utama
def _device_plan(pref: str) -> list:
    pref = (pref or "auto").lower()
    if pref == "cpu":
        return ["cpu"]
    if pref in ("cuda", "gpu"):
        return ["cuda", "cpu"]
    return ["cuda", "cpu"] if cuda_available() else ["cpu"]


def transcribe_file(
    audio: Path,
    *,
    mode: str = "auto",
    manual_choice: str = "small",
    device: str = "auto",
    quality: str = "fast",
    progress: ProgressFn = None,
) -> str:
    duration = ffprobe_duration(audio)
    if progress:
        progress(15, f"Durasi ~{duration/60:.1f} menit" if duration else "Menyiapkan audio…")

    use_fw = have_faster_whisper()
    runner = _run_faster if use_fw else _run_openai
    errors = []
    for dev in _device_plan(device):
        size = choose_model(duration, mode, manual_choice, dev)
        if progress:
            progress(20, f"Memuat model {size} di {dev.upper()}…")
        try:
            text = runner(audio, size, dev, quality, progress)
            if progress:
                progress(90, f"Selesai ({dev.upper()}, model {size})")
            return text
        except Exception as e:
            log.exception(f"[stt] gagal di {dev}")
            errors.append(f"{dev}: {e}")
            if dev == "cuda":
                _GPU_BROKEN.update(flag=True, reason=str(e)[:200])
                if progress:
                    progress(22, "GPU gagal, beralih ke CPU…")
    raise RuntimeError("Transkripsi gagal. " + " | ".join(errors))
