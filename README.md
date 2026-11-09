---
title: Notulen Rapat Otomatis
emoji: 🎙️
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# 🎙️ Sistem Transkrip Audio & Penyusunan Notulen Rapat Otomatis

Aplikasi web berbasis Flask & `faster-whisper` (mendukung **CPU int8** maupun **GPU CUDA**) untuk menyalin rekaman rapat menjadi teks, merangkum poin penting, dan menyusun dokumen **Notulen Rapat Resmi (`.docx` & Cetak A4)** lengkap dengan **Tanda Tangan Digital**.

---

## ✨ Fitur Utama

1. **Transkripsi Cepat (CPU & GPU)**
   - Menggunakan mesin `faster-whisper` dengan kuantisasi `int8` di CPU dan dukungan penuh GPU CUDA.
   - Dilengkapi *Voice Activity Detection (VAD)* untuk melewati bagian hening dan mempercepat proses.
   - Pemantauan progres transkripsi secara *real-time* (Server-Sent Events).
2. **Penyusunan Notulen Rapat Resmi**
   - Klasifikasi otomatis isi rapat ke bagian **Pokok Pembahasan, Arahan Pimpinan, Isu/Kendala, Keputusan Rapat**, dan **Tabel Tindak Lanjut (PIC & Batas Waktu)**.
   - Pratinjau halaman web berformat kertas A4 yang identik dengan hasil unduhan Microsoft Word (`.docx`).
3. **Tanda Tangan Digital**
   - Gambar tanda tangan langsung di layar (mouse/layar sentuh/stylus) atau unggah foto tanda tangan di kertas putih.
   - Latar putih dihapus otomatis menjadi transparan dan langsung terpasang pada dokumen notulen & file `.docx`.

---

## 🚀 Cara Menjalankan di Komputer Lokal (Windows)

1. Pastikan **Python 3.10+** dan **FFmpeg** sudah terpasang di `PATH` (`ffmpeg -version`).
2. Buat virtual environment & instal dependensi:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
3. *(Opsional)* Jika memiliki GPU NVIDIA modern (seri GTX 16xx / RTX), aktifkan akselerasi CUDA dengan:
   ```powershell
   .\.venv\Scripts\pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*
   ```
4. Jalankan server:
   ```powershell
   .\.venv\Scripts\python app.py
   ```
5. Buka browser di **http://127.0.0.1:5000**.

---

## ☁️ Cara Deploy Gratis ke Cloud (Hugging Face Spaces / Railway)

Karena aplikasi ini menjalankan model AI `faster-whisper` dan `ffmpeg` secara langsung di server, gunakan platform berbasis kontainer (Docker) seperti **Hugging Face Spaces** (Gratis 2 vCPU + 16 GB RAM) atau **Railway**:

### A. Deploy ke Hugging Face Spaces (Gratis 16 GB RAM)
1. Buat akun di [huggingface.co](https://huggingface.co) lalu klik **New Space**.
2. Isi nama Space, pilih **SDK: Docker** (Blank), dan pilih perangkat **CPU basic (Free · 2 vCPU · 16 GB)**.
3. Hubungkan atau push repositori ini ke Space Anda:
   ```bash
   git remote add space https://huggingface.co/spaces/USERNAME_ANDA/NAMA_SPACE_ANDA
   git push space main
   ```
4. Hugging Face akan otomatis membaca `Dockerfile` di repositori ini dan menjalankan aplikasi.

### B. Deploy ke Railway
1. Buka [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
2. Pilih repositori `Anggasukhapratama/Transkrip-notulen`.
3. Railway otomatis mendeteksi `Dockerfile` / `Procfile` dan langsung men-deploy aplikasi Anda.
