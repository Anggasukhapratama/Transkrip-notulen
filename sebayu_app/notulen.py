# sebayu_app/notulen.py
"""
Penyusun notulen rapat (tanpa AI eksternal):
  - klasifikasi kalimat transkrip -> pembahasan / keputusan / tindak lanjut / isu / arahan
  - satu sumber data (build_minutes_data) dipakai oleh tampilan web DAN file DOCX
  - DOCX berformat surat resmi: kop + logo, tabel informasi, penomoran rapi,
    tabel tindak lanjut, blok tanda tangan (mendukung tanda tangan digital berupa gambar)
"""
import re
import requests
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from urllib.parse import urlparse

from .config import UPLOAD_DIR, HAVE_DOCX, log, DEFAULT_META

HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
            "Agustus", "September", "Oktober", "November", "Desember"]


def _parse_dt(created_at: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime((created_at or "")[:19], fmt)
        except Exception:
            continue
    return None


def tanggal_id(dt: Optional[datetime]) -> str:
    return f"{dt.day} {BULAN_ID[dt.month - 1]} {dt.year}" if dt else ""


def hari_id(dt: Optional[datetime]) -> str:
    return HARI_ID[dt.weekday()] if dt else ""


# ====================== RINGKASAN LOKAL ======================

def local_summarize_bullets(text: str, max_sentences: int = 18) -> str:
    sents = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    keywords = [
        "keputusan", "tindak lanjut", "action", "deadline", "anggaran", "solusi", "usulan",
        "disepakati", "menyetujui", "ditetapkan", "menetapkan", "menugaskan", "PIC", "owner",
        "target", "paling lambat", "KUA", "PPAS", "TAPD", "RKPD"
    ]
    scored = []
    for s in sents:
        s2 = s.strip()
        if not s2:
            continue
        score = len(s2)
        low = s2.lower()
        score += sum(28 for k in keywords if k in low)
        scored.append((score, s2))
    scored.sort(reverse=True, key=lambda x: x[0])
    bullets = [f"- {s}" for _, s in scored[:max_sentences]]
    if not bullets:
        return "- (tidak cukup konten untuk diringkas)"
    return "\n".join(bullets)


# ====== Klasifikasi Lokal Notulen (tanpa AI eksternal) ======

RE_DATE = re.compile(
    r"\b(\d{1,2}[/\-.]\d{1,2}([/\-.]\d{2,4})?|"
    r"\d{1,2}\s+(jan|feb|mar|apr|mei|jun|jul|agu|sep|okt|nov|des)[a-z]*\s+\d{2,4}|"
    r"paling lambat|selambat-lambatnya|sebelum tanggal|minggu ke-\d+|akhir bulan|awal bulan)\b",
    re.I
)
RE_OWNER = re.compile(
    r"\b(PIC|owner|penanggung jawab|ditugaskan kepada|menugaskan|oleh)\b[: ]+([A-Z][a-zA-Z_. ]+)",
    re.I
)
RE_DECISION_VERB = re.compile(
    r"\b(diputuskan|memutuskan|menetapkan|ditetapkan|disepakati|menyepakati|"
    r"menyetujui|disetujui|menolak|dengan catatan)\b", re.I)
RE_ACTION_VERB = re.compile(
    r"\b(dilakukan|ditindaklanjuti|dikerjakan|menindaklanjuti|menyelesaikan|"
    r"melakukan|follow[- ]?up|menugaskan|ditugaskan|koordinasi|menyusun|mengirim|"
    r"mengajukan|merevisi|memperbaiki|menyampaikan)\b", re.I)

BASE_KEYSETS = {
    "keputusan": [
        r"\bkeputusan\b", r"\bdiputuskan\b", r"\bmemutuskan\b", r"\bmenetapkan\b", r"\bditetapkan\b",
        r"\bdisepakati\b|\bkesepakatan\b", r"\bmenyetujui\b|\bdisetujui\b", r"\bmenolak\b", r"\bdengan catatan\b",
        r"\bhasil rapat\b", r"\bputusan rapat\b", r"\bkonklusi\b", r"\bkonklusinya\b", r"\bketetapan\b",
        r"\bpengesahan\b", r"\bdiputus\b|\bmenyepakati\b|\bmufakat\b|\bmusyawarah\b",
        r"\bPeraturan\b|\bPerda\b|\bPerwal\b|\bPerbup\b|\bSK\b|\bSurat Keputusan\b|\bKeppres\b|\bPerpres\b",
        r"\bditerbitkan\b|\bditetapkan melalui\b|\bdikuatkan\b|\bdisahkan\b|\bsah\b",
        r"\bdipersetujui\b", r"\bdibolehkan\b", r"\bdilarang\b", r"\bditolak\b", r"\bditunda\b", r"\bdipending\b",
        r"\bdisetujui bersama\b", r"\bdengan syarat\b", r"\bdengan ketentuan\b", r"\bbersyarat\b",
        r"\bmenyetujui anggaran\b", r"\bpenetapan pagu\b", r"\bpenetapan KUA\b", r"\bpengesahan APBD\b",
        r"\bpengesahan KUA\b", r"\bpengesahan PPAS\b", r"\bpengesahan RAPBD\b", r"\bpengesahan RKPD\b",
        r"\bmutasi\b|\bpromosi\b|\bpemberhentian\b|\bpenunjukan\b|\bdiangkat\b|\bpengangkatan\b|\bpergantian\b",
        r"\bkeputusan pimpinan\b|\bkeputusan ketua\b|\bkeputusan dewan\b|\bhasil pleno\b",
        r"\bdinyatakan\b|\bditegaskan\b|\bdipastikan\b|\bdipilih\b|\bmemilih\b",
        r"\bdisetujui rapat\b|\bhasil sidang\b|\bketok palu\b"
    ],
    "tindak_lanjut": [
        r"\btindak lanjut\b", r"\bditindaklanjuti\b", r"\bmenindaklanjuti\b", r"\baksi\b|\baction\b",
        r"\bfollow[- ]?up\b", r"\bkelanjutan\b", r"\bprogress\b|\bprogres\b",
        r"\bdeadline\b|\bdue\b|\bjatuh tempo\b|\bbatas waktu\b|\bpaling lambat\b|\bselambat\b|\btarget\b|\bSLA\b|\bKPI\b",
        r"\bPIC\b|\bowner\b|\bpenanggung jawab\b|\bpenanggungjawab\b",
        r"\bditugaskan\b|\bmenugaskan\b|\bmenunjuk\b|\bdidelegasikan\b|\bdelegasi\b",
        r"\btanggung jawab\b|\bkoordinator\b|\bpenanggung jawab kegiatan\b",
        r"\bkoordinasi\b|\bberkoordinasi\b|\bkoor(d)?\b",
        r"\bkomunikasi\b|\bmenghubungi\b|\bkontak\b|\bkonfirmasi\b|\bmengonfirmasi\b",
        r"\breminder\b|\bdiingatkan\b|\bperingatan\b|\bnotifikasi\b|\bfollow[- ]?up via\b",
        r"\bmenyusun surat\b|\bmembuat surat\b|\bkonsep surat\b|\bsurat tugas\b|\bsurat undangan\b|\bnota dinas\b|\bNODIN\b",
        r"\bdisposisi\b|\bparaf\b|\bpara(f)? berjenjang\b|\btembusan\b",
        r"\bmengirim surat\b|\bmengirimkan surat\b|\bmenyampaikan surat\b|\bunggah surat\b",
        r"\bBAST\b|\bberita acara\b|\bSPT\b|\bSK\b|\bMoU\b|\bPKS\b",
        r"\bmenjadwalkan rapat\b|\bdijadwalkan rapat\b|\bpenjadwalan\b|\batur jadwal\b",
        r"\bRapat lanjutan\b|\bFGD\b|\bbriefing\b|\bkoordinasi lintas OPD\b",
        r"\bsosialisasi\b|\bdiseminasi\b|\bpembinaan\b|\bpenguatan\b|\bpendampingan\b",
        r"\bmenyusun\b|\bmenyempurnakan\b|\bmelengkapi\b|\bmemperbarui\b|\bmemutakhirkan\b",
        r"\bmerevisi\b|\brevisi\b|\bperbaikan\b|\bperubahan\b|\bupdate dokumen\b",
        r"\bfinalisasi\b|\bfinal\b|\bpengesahan internal\b",
        r"\bmengarsipkan\b|\bdiarsipkan\b|\bunggah\b|\bmengunggah\b|\bupload\b|\bdiunggah\b",
        r"\bverifikasi\b|\bdipverifikasi\b|\bvalidasi\b|\bdipvalidasi\b|\bcek kelengkapan\b|\bcek dokumen\b",
        r"\bmenyusun laporan\b|\bmenyampaikan laporan\b|\blaporan kemajuan\b|\blaporan realisasi\b|\bLPJ\b|\bSPJ\b",
        r"\bmonitoring\b|\bmonitor\b|\bMonev\b|\bevaluasi\b|\breview\b|\bpenilaian\b",
        r"\bRKPD\b|\bKUA\b|\bPPAS\b|\bRKA\b|\bDPA\b|\bPOK\b",
        r"\binput (ke )?SIPD\b|\bSIPD\b|\bSIRUP\b|\bSiRUP\b",
        r"\bpenyelarasan\b|\bsinkronisasi\b|\bpenyesuaian pagu\b|\bpenajaman program\b",
        r"\bpengadaan\b|\bPBJ\b|\bULP\b|\bLPSE\b|\be-?catalog\b|\be-katalog\b",
        r"\bSPK\b|\bkontrak\b|\bBAST\b|\bBAHN\b|\bvendor\b|\bpenyedia\b|\btagihan\b|\binvoice\b|\bpembayaran\b",
        r"\btiket\b|\bhelpdesk\b|\bissue tracking\b|\bperbaiki bug\b|\bbugfix\b|\bdeploy\b|\brelease\b|\brollout\b",
        r"\bkonfigurasi\b|\bkonfigur(asi)?\b|\bsetup\b|\binstalasi\b|\bimplementasi\b|\bgo[- ]live\b",
        r"\bdokumentasi teknis\b|\breadme\b|\bSOP\b|\bpanduan\b",
        r"\bsurvei\b|\bsurvey\b|\bverifikasi lapangan\b|\bpengukuran\b|\bpemetaan\b",
        r"\bkunjungan\b|\bvisit\b|\bpeninjauan\b|\binspeksi\b|\bcek lokasi\b",
        r"\bpenyusunan rancangan\b|\brancangan peraturan\b|\bperwal\b|\bperbup\b|\bperda\b",
        r"\bkonsultasi hukum\b|\bklarifikasi regulasi\b",
        r"\bmenyiapkan materi\b|\bbahan paparan\b|\bslide\b|\bdeck\b|\bpress release\b|\bsiaran pers\b",
        r"\bpublikasi\b|\bunggah ke website\b|\bmedia sosial\b|\bkonten informasi\b",
        r"\bH\+?\d+\b|\bMinggu depan\b|\bpekan depan\b|\bbulan depan\b|\bakhir (pekan|bulan)\b|\bawal (pekan|bulan)\b",
        r"\bdiminta untuk\b|\bdiharapkan untuk\b|\bagar\b|\bharap\b|\bsegera\b|\bsesegera mungkin\b|\bASAP\b",
        r"\bdiperintahkan\b|\bditekankan\b|\bdianjurkan\b",
        r"\bserahkan\b|\bdiserahkan\b|\bkirimkan\b|\bdikirimkan\b|\bunggah berkas\b|\bupload berkas\b|\bsubmit\b|\bdisubmit\b",
        r"\bmenyertakan lampiran\b|\blampiran lengkap\b|\bkelengkapan berkas\b",
        r"\bmenyusun jadwal\b|\btime line\b|\btimeline\b|\brencana kerja\b|\bRencana Tindak Lanjut\b|\bRTL\b"
    ],
    "isu": [
        r"\bisu\b|\bmasalah\b|\bkendala\b|\brisiko\b|\bblokir\b|\bproblem\b|\bcatatan risiko\b"
    ],
    "arahan": [
        r"\barahan\b|\binstruksi\b|\bdiarahkan\b|\bdiminta\b|\bgaris besar\b|\bperhatian\b"
    ],
    "catatan": [
        r"\bcatatan\b|\binformasi\b|\bupdate\b|\bkonteks\b|\bpengantar\b"
    ]
}


def _compile_keysets(custom: Dict[str, List[str]] | None) -> Dict[str, List[re.Pattern]]:
    merged: Dict[str, List[str]] = {k: list(v) for k, v in BASE_KEYSETS.items()}
    if custom:
        for k, arr in custom.items():
            if not arr:
                continue
            merged.setdefault(k, [])
            merged[k].extend(arr)
    return {k: [re.compile(p, re.I) for p in v] for k, v in merged.items()}


def _split_candidates(text: str) -> list[str]:
    parts = re.split(r"(?:\n{2,}|(?<=[.!?])\s+)", text)
    return [p.strip("•- \t\r") for p in parts if p and p.strip()]


def _infer_owner(line: str) -> str | None:
    m = RE_OWNER.search(line)
    if m:
        return m.group(2).strip()
    m2 = re.search(r"\b([A-Z][a-zA-Z_. ]{1,40})\b[^.]{0,30}\b(akan|agar|diminta|ditugaskan)\b", line)
    return m2.group(1).strip() if m2 else None


def _infer_due(line: str) -> str | None:
    m = RE_DATE.search(line)
    return m.group(0) if m else None



# ====================== EKSTRAKSI NOTULEN (urut sesuai isi rapat) ======================

_RE_OWNER_STRICT = re.compile(
    r"\b(?:PIC|penanggung\s*jawab|ditugaskan\s+kepada|diserahkan\s+kepada|dikoordinasikan\s+oleh)\b"
    r"\s*[:\-]?\s*((?-i:[A-Z][\w.]*(?:\s+[A-Z][\w.]*){0,3}))",
    re.I,
)
_RE_LEAD_JUNK = re.compile(r"^(?:dan|jadi|nah|ya|oke|baik|ok|terus|lalu|kemudian|nanti|tapi|tetapi|dan juga)\b[\s,]*", re.I)

THRESHOLDS = {"keputusan": 2.0, "tindak_lanjut": 2.4, "isu": 1.0, "arahan": 1.0}
LIMITS = {"keputusan": 15, "tindak_lanjut": 15, "isu": 10, "arahan": 10}


_RE_DUE = re.compile(
    r"(?:(?:paling lambat|selambat-lambatnya|sebelum(?: tanggal)?)\s+(?:tanggal\s+)?)?"
    r"(?:\d{1,2}\s+(?:jan|feb|mar|apr|mei|jun|jul|agu|sep|okt|nov|des)[a-z]*\s+\d{2,4}"
    r"|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})"
    r"|(?:paling lambat|selambat-lambatnya)\s+(?:akhir|awal)\s+(?:bulan|pekan|minggu)"
    r"|\b(?:akhir|awal)\s+(?:bulan|pekan|minggu)(?:\s+ini|\s+depan)?"
    r"|\b(?:minggu|pekan|bulan)\s+depan\b",
    re.I,
)
_RE_ARAHAN_VERB = re.compile(r"\b(mengarahkan|menginstruksikan|menekankan|mengimbau|menghimbau|pimpinan (?:meminta|berpesan))\b", re.I)


def _infer_due(line: str) -> str | None:
    m = _RE_DUE.search(line)
    return m.group(0).strip() if m else None


def _owner(line: str) -> Optional[str]:
    m = _RE_OWNER_STRICT.search(line)
    return m.group(1).strip() if m else None


def _norm_key(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()[:90]


def polish_sentence(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip(" \t-•*")
    for _ in range(3):
        s2 = _RE_LEAD_JUNK.sub("", s).strip()
        if s2 == s:
            break
        s = s2
    if not s:
        return ""
    s = s[0].upper() + s[1:]
    if s[-1] not in ".!?":
        s += "."
    return s


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    out = []
    for p in parts:
        p = p.strip()
        if len(p.split()) < 5 or len(p) > 450:
            continue
        out.append(p)
    return out


def _scores(line: str, COMPILED: Dict[str, List[re.Pattern]]) -> Dict[str, float]:
    sc = {k: 0.0 for k in COMPILED}
    for k, regs in COMPILED.items():
        for rgx in regs:
            if rgx.search(line):
                sc[k] += 1.0
    if _RE_ARAHAN_VERB.search(line):
        sc["arahan"] += 3.0
    if RE_DECISION_VERB.search(line):
        sc["keputusan"] += 1.6
    if RE_ACTION_VERB.search(line):
        sc["tindak_lanjut"] += 1.1
    if _infer_due(line):
        sc["tindak_lanjut"] += 0.8
    if _owner(line):
        sc["tindak_lanjut"] += 0.8
    return sc


def _importance(line: str) -> float:
    low = line.lower()
    kw = ("anggaran", "program", "kegiatan", "usulan", "rencana", "target", "evaluasi",
          "pembahasan", "laporan", "peraturan", "kebijakan", "pagu", "dokumen")
    return min(len(line), 220) + sum(30 for k in kw if k in low)


def extract_sections(transcript: str, custom_keywords: Dict[str, List[str]] | None = None) -> dict:
    """Kembalikan bagian notulen dengan urutan kemunculan di rapat (bukan acak)."""
    COMPILED = _compile_keysets(custom_keywords)
    sents = _sentences(transcript)

    seen = set()
    uniq: List[str] = []
    for s in sents:
        k = _norm_key(s)
        if k and k not in seen:
            seen.add(k)
            uniq.append(s)

    buckets: Dict[str, List[tuple]] = {k: [] for k in LIMITS}
    used = set()
    for idx, s in enumerate(uniq):
        sc = _scores(s, COMPILED)
        best, margin = None, 0.0
        for label, thr in THRESHOLDS.items():
            if sc.get(label, 0) >= thr and sc[label] - thr >= margin:
                best, margin = label, sc[label] - thr
        if best and len(buckets[best]) < LIMITS[best]:
            buckets[best].append((idx, s))
            used.add(idx)

    rest = [(i, s) for i, s in enumerate(uniq) if i not in used]
    k = min(12, max(4, len(rest) // 12))
    top = sorted(rest, key=lambda x: _importance(x[1]), reverse=True)[:k]
    top.sort(key=lambda x: x[0])

    tindak = []
    for _, s in buckets["tindak_lanjut"]:
        tindak.append({"text": polish_sentence(s), "pic": _owner(s) or "", "due": _infer_due(s) or ""})

    def fin(label):
        return [polish_sentence(s) for _, s in buckets[label]]

    return {
        "pembahasan": [polish_sentence(s) for _, s in top],
        "keputusan": fin("keputusan"),
        "tindak_lanjut": tindak,
        "arahan": fin("arahan"),
        "isu": fin("isu"),
    }


# ====================== DATA NOTULEN (dipakai web + DOCX) ======================

def _lines(val) -> List[str]:
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return [x.strip() for x in str(val or "").splitlines() if x.strip()]


def resolve_image(val: str):
    """Kembalikan Path file lokal (dari /uploads/...) atau BytesIO (dari URL http), atau None."""
    val = (val or "").strip()
    if not val:
        return None
    try:
        if val.startswith("/uploads/"):
            p = UPLOAD_DIR / val.split("/uploads/", 1)[1]
            return p if p.exists() else None
        if urlparse(val).scheme in ("http", "https"):
            r = requests.get(val, timeout=10)
            r.raise_for_status()
            return BytesIO(r.content)
    except Exception as e:
        log.warning(f"Gagal memuat gambar {val}: {e}")
    return None


def build_minutes_data(tr: dict, meta: dict | None) -> dict:
    tr = dict(tr)
    m = dict(DEFAULT_META)
    m.update(meta or {})
    dt = _parse_dt(tr.get("created_at", ""))
    program = tr.get("program") or "Rapat"

    custom = {
        "keputusan": m.get("kw_keputusan", []),
        "tindak_lanjut": m.get("kw_tindak_lanjut", []),
        "isu": m.get("kw_isu", []),
        "arahan": m.get("kw_arahan", []),
    }
    custom = {k: v for k, v in custom.items() if v}
    sec = extract_sections(tr.get("transcript", ""), custom)

    tgl = m.get("tanggal") or tanggal_id(dt)
    hari = m.get("hari") or hari_id(dt)
    dash = "-"
    info = [
        ("Hari / Tanggal", f"{hari}, {tgl}".strip(", ") or dash),
        ("Waktu", m.get("waktu") or dash),
        ("Tempat", m.get("tempat") or dash),
        ("Acara", m.get("acara") or f"Rapat {program}"),
        ("Pimpinan Rapat", m.get("pimpinan") or dash),
        ("Notulis", m.get("notulis") or dash),
    ]
    ttd_tgl = m.get("ttd_tanggal") or tgl
    return {
        "header": {
            "instansi_lines": _lines(m.get("instansi")),
            "alamat": m.get("alamat", ""),
            "logo": m.get("logo", ""),
            "kop_html": m.get("kop_html", ""),
        },
        "judul": (m.get("judul") or "Notulen Rapat").upper(),
        "nomor": m.get("nomor", ""),
        "info": info,
        "peserta": _lines(m.get("peserta")),
        **sec,
        "penutup": m.get("penutup") or "Demikian notulen rapat ini dibuat untuk dapat dipergunakan sebagaimana mestinya.",
        "ttd": {
            "kota": m.get("ttd_kota", ""),
            "tanggal": ttd_tgl,
            "jabatan": m.get("ttd_jabatan", ""),
            "nama": m.get("ttd_nama", ""),
            "pangkat": m.get("ttd_pangkat", ""),
            "nip": m.get("ttd_nip", ""),
            "image": m.get("ttd_image", ""),
            "signed_at": m.get("ttd_signed_at", ""),
        },
    }


# ====================== DOCX (format surat resmi) ======================

def build_docx_from_minutes(data: dict) -> BytesIO:
    if not HAVE_DOCX:
        raise RuntimeError("python-docx belum terpasang. Jalankan: pip install python-docx")
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH as AL
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    FONT = "Times New Roman"
    doc = Document()

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin, sec.right_margin = Cm(2.5), Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(2.0)

    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(12)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.paragraph_format.space_after = Pt(0)
    st.paragraph_format.space_before = Pt(0)
    st.paragraph_format.line_spacing = 1.15

    # ---------- helpers ----------
    def para(container, text="", *, bold=False, italic=False, underline=False, size=None,
             align=None, after=0, before=0, keep_next=False):
        p = container.add_paragraph()
        if text:
            r = p.add_run(text)
            r.bold, r.italic, r.underline = bold, italic, underline
            if size:
                r.font.size = Pt(size)
        if align is not None:
            p.alignment = align
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.space_before = Pt(before)
        p.paragraph_format.keep_with_next = keep_next
        return p

    def first_para(cell):
        """Pakai paragraf kosong bawaan sel agar tidak ada baris ekstra."""
        return cell.paragraphs[0]

    def fill(p, text, *, bold=False, italic=False, underline=False, size=None, align=None, after=0):
        r = p.add_run(text)
        r.bold, r.italic, r.underline = bold, italic, underline
        if size:
            r.font.size = Pt(size)
        if align is not None:
            p.alignment = align
        p.paragraph_format.space_after = Pt(after)
        return p

    def shade(cell, fill_hex):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), fill_hex)
        tcPr.append(shd)

    def widths(table, ws):
        table.autofit = False
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, w in enumerate(ws):
            table.columns[i].width = w
        for row in table.rows:
            for i, w in enumerate(ws):
                row.cells[i].width = w

    def cant_split(row):
        trPr = row._tr.get_or_add_trPr()
        trPr.append(OxmlElement("w:cantSplit"))

    def repeat_header(row):
        trPr = row._tr.get_or_add_trPr()
        el = OxmlElement("w:tblHeader"); el.set(qn("w:val"), "true")
        trPr.append(el)

    def double_rule(p):
        pPr = p._p.get_or_add_pPr()
        bd = OxmlElement("w:pBdr")
        b = OxmlElement("w:bottom")
        b.set(qn("w:val"), "double"); b.set(qn("w:sz"), "6"); b.set(qn("w:space"), "1"); b.set(qn("w:color"), "000000")
        bd.append(b); pPr.append(bd)

    def heading(text):
        return para(doc, text, bold=True, before=10, after=4, keep_next=True)

    def numbered(items):
        for i, t in enumerate(items, 1):
            p = doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent, pf.first_line_indent = Cm(0.9), Cm(-0.9)
            pf.tab_stops.add_tab_stop(Cm(0.9))
            pf.space_after = Pt(4)
            p.alignment = AL.JUSTIFY
            p.add_run(f"{i}.\t{t}")

    def add_image(cell_or_par, src, *, max_w_cm, max_h_cm):
        w_cm, h_cm = max_w_cm, max_h_cm
        try:
            from PIL import Image
            if isinstance(src, Path):
                im = Image.open(src)
            else:
                src.seek(0); im = Image.open(src)
            iw, ih = im.size
            scale = min(max_w_cm / iw, max_h_cm / ih)
            w_cm, h_cm = iw * scale, ih * scale
            if not isinstance(src, Path):
                src.seek(0)
        except Exception:
            pass
        run = cell_or_par.add_run()
        run.add_picture(str(src) if isinstance(src, Path) else src, width=Cm(w_cm), height=Cm(h_cm))

    # ---------- KOP SURAT ----------
    hd = data["header"]
    logo = resolve_image(hd["logo"])
    kop = doc.add_table(rows=1, cols=3)
    widths(kop, [Cm(2.6), Cm(11.3), Cm(2.6)])
    c_logo, c_txt, _ = kop.rows[0].cells
    if logo is not None:
        p = first_para(c_logo)
        add_image(p, logo, max_w_cm=2.3, max_h_cm=2.3)
    lines = hd["instansi_lines"] or [""]
    p = first_para(c_txt)
    for i, ln in enumerate(lines):
        if i:
            p = c_txt.add_paragraph()
        fill(p, ln.upper(), bold=True, size=14 if i == len(lines) - 1 else 12, align=AL.CENTER)
    if hd["alamat"]:
        fill(c_txt.add_paragraph(), hd["alamat"], size=9.5, align=AL.CENTER)
    rule = para(doc, "", after=8)
    rule.paragraph_format.space_before = Pt(2)
    double_rule(rule)

    # ---------- JUDUL ----------
    para(doc, data["judul"], bold=True, underline=True, size=13, align=AL.CENTER, after=2)
    if data["nomor"]:
        para(doc, f"Nomor: {data['nomor']}", align=AL.CENTER, after=2)
    para(doc, "", after=4)

    # ---------- INFORMASI ----------
    t = doc.add_table(rows=0, cols=3)
    for label, val in data["info"]:
        cells = t.add_row().cells
        fill(first_para(cells[0]), label)
        fill(first_para(cells[1]), ":")
        fill(first_para(cells[2]), val)
        for c in cells:
            c.paragraphs[0].paragraph_format.space_after = Pt(3)
    widths(t, [Cm(4.2), Cm(0.6), Cm(11.7)])

    # ---------- BAGIAN-BAGIAN ----------
    letters = iter("ABCDEFGH")

    def section(title, items):
        if not items:
            return
        heading(f"{next(letters)}. {title}")
        numbered(items)

    if data["peserta"]:
        section("PESERTA RAPAT", data["peserta"])
    section("POKOK PEMBAHASAN", data["pembahasan"])
    section("ARAHAN PIMPINAN", data["arahan"])
    section("ISU / KENDALA", data["isu"])
    section("KEPUTUSAN RAPAT", data["keputusan"])

    if data["tindak_lanjut"]:
        heading(f"{next(letters)}. TINDAK LANJUT")
        tl = doc.add_table(rows=1, cols=4)
        tl.style = "Table Grid"
        hdr = tl.rows[0]
        repeat_header(hdr)
        for c, txt in zip(hdr.cells, ["No", "Tindak Lanjut", "PIC", "Batas Waktu"]):
            fill(first_para(c), txt, bold=True, align=AL.CENTER, size=11)
            shade(c, "D9E2F3")
        for i, it in enumerate(data["tindak_lanjut"], 1):
            row = tl.add_row()
            cant_split(row)
            vals = [str(i), it["text"], it["pic"] or "-", it["due"] or "-"]
            for j, (c, v) in enumerate(zip(row.cells, vals)):
                fill(first_para(c), v, size=11,
                     align=AL.CENTER if j in (0, 2, 3) else AL.JUSTIFY)
                c.paragraphs[0].paragraph_format.space_after = Pt(2)
        widths(tl, [Cm(1.1), Cm(9.4), Cm(3.0), Cm(3.0)])

    # ---------- PENUTUP ----------
    para(doc, data["penutup"], align=AL.JUSTIFY, before=12, after=6, keep_next=True)

    # ---------- TANDA TANGAN ----------
    tt = data["ttd"]
    sig = doc.add_table(rows=1, cols=2)
    widths(sig, [Cm(9.0), Cm(7.5)])
    cant_split(sig.rows[0])
    right = sig.rows[0].cells[1]
    place = ", ".join(x for x in [tt["kota"], tt["tanggal"]] if x)
    fill(first_para(right), place, align=AL.CENTER)
    if tt["jabatan"]:
        fill(right.add_paragraph(), tt["jabatan"], align=AL.CENTER)
    img = resolve_image(tt["image"])
    if img is not None:
        p = right.add_paragraph()
        p.alignment = AL.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        add_image(p, img, max_w_cm=5.5, max_h_cm=2.6)
    else:
        for _ in range(4):
            right.add_paragraph()
    fill(right.add_paragraph(), tt["nama"] or "(                                        )",
         bold=bool(tt["nama"]), underline=bool(tt["nama"]), align=AL.CENTER)
    if tt["pangkat"]:
        fill(right.add_paragraph(), tt["pangkat"], align=AL.CENTER)
    if tt["nip"]:
        fill(right.add_paragraph(), f"NIP. {tt['nip']}", align=AL.CENTER)
    if img is not None and tt.get("signed_at"):
        fill(right.add_paragraph(), f"Ditandatangani secara digital, {tt['signed_at']}",
             italic=True, size=8, align=AL.CENTER)

    # ---------- FOOTER: nomor halaman ----------
    fp = sec.footer.paragraphs[0]
    fp.alignment = AL.CENTER
    r = fp.add_run("Halaman ")
    r.font.size = Pt(9)
    run = fp.add_run()
    run.font.size = Pt(9)
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = text
        run._r.append(el)

    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio
