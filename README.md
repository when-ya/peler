# Telegram Video Storage Bot

Bot Telegram buat upload video (sampai 2GB) ke Backblaze B2 dengan navigasi folder,
dan otomatis catat link + metadata ke Google Sheets.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Isi file `.env`

Copy `.env.example` jadi `.env`:

```bash
cp .env.example .env
```

Lalu isi semua **placeholder** (`ISI_..._DISINI`) di file `.env` dengan credentials asli kamu:
- `API_ID` & `API_HASH` — dari https://my.telegram.org
- `BOT_TOKEN` — dari @BotFather
- `B2_KEY_ID` & `B2_APPLICATION_KEY` — dari Backblaze B2 App Keys
- `ALLOWED_USER_IDS` — Telegram user ID kamu (cek lewat @userinfobot), pisahkan koma kalau lebih dari satu. **Kosongkan kalau mau bot bisa diakses siapa aja.**

`SPREADSHEET_ID` dan `B2_BUCKET_NAME` udah keisi otomatis sesuai yang udah disetup sebelumnya — cek ulang aja apakah sudah benar.

### 3. Taruh Service Account JSON

Taruh file JSON Service Account (`vdscld@propane-primacy-502823-m8.iam.gserviceaccount.com`)
di folder project ini, kasih nama `service_account.json` — atau ganti nama file
di `.env` pada bagian `GOOGLE_SERVICE_ACCOUNT_FILE` sesuai nama file kamu.

### 4. Jalanin bot

```bash
python bot.py
```

Pertama kali jalan, Pyrogram akan generate session file di folder `sessions/` —
biarkan aja, itu buat menjaga koneksi biar gak perlu re-auth terus.

## Struktur Project

```
telegram-video-bot/
├── bot.py                  # Entry point + semua handler & menu
├── b2_client.py             # Fungsi upload/list/delete ke Backblaze B2
├── sheets_client.py         # Fungsi baca/tulis ke Google Sheets
├── config.py                 # Loader environment variable
├── requirements.txt
├── .env.example              # Template -- copy jadi .env dan isi
├── service_account.json      # (kamu taruh sendiri, JANGAN di-commit ke git)
└── sessions/                  # Auto-generated oleh Pyrogram
```

## Menu Bot

- **📤 Upload Video** — browsing folder lewat inline keyboard, pilih tujuan, lalu kirim video
- **📁 Daftar Video** — list semua video yang tercatat di Sheets (dengan pagination)
- **🔗 Link Terakhir** — ambil video paling baru diupload
- **🔍 Cari Video** — cari berdasarkan nama file
- **🆕 Buat Folder Baru** — muncul otomatis pas lagi browsing folder
- **/checklinks** — cek manual semua link, update status kalau ada yang sudah tidak aktif

## Pengecekan Link Otomatis

Bot otomatis cek semua video berstatus "Aktif" tiap **`CHECK_INTERVAL_HOURS`** jam sekali
(default 6 jam, bisa diubah di `.env`). Kalau file-nya udah tidak ada di B2 — baik karena
dihapus manual langsung di B2 console, maupun cara lain — statusnya otomatis diubah jadi
**"Tidak Aktif"** di Google Sheets.

Kalau mau cek langsung tanpa nunggu jadwal, ketik `/checklinks` ke bot kapan aja.

## Deploy ke Railway

1. **Push ke GitHub** — `.env` dan `service_account.json` otomatis gak ke-push (sudah ada di `.gitignore`)
2. Di Railway: **New Project → Deploy from GitHub Repo** → pilih repo ini
3. Buka tab **Variables**, isi satu-satu (samain dengan isi `.env` lokal kamu):
   - `API_ID`, `API_HASH`, `BOT_TOKEN`
   - `B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`
   - `SPREADSHEET_ID`
   - `ALLOWED_USER_IDS` (opsional)
4. **Khusus Service Account**: karena file JSON gak ikut ke-push, buka file JSON-nya,
   copy seluruh isinya (dari `{` sampai `}`), paste sebagai satu variable baru:
   - Key: `GOOGLE_SERVICE_ACCOUNT_JSON`
   - Value: seluruh isi file JSON (satu baris panjang, gapapa)
5. Railway otomatis baca `Procfile` dan jalanin sebagai **worker** (bukan web service,
   karena bot Telegram gak buka port HTTP)
6. Cek **Deployments → Logs**, harus muncul `🤖 Bot jalan...` tanpa error

> Kode di `sheets_client.py` sudah otomatis handle dua skenario: baca dari file JSON lokal
> (`GOOGLE_SERVICE_ACCOUNT_FILE`) kalau ada di komputer kamu, atau baca dari isi env variable
> (`GOOGLE_SERVICE_ACCOUNT_JSON`) kalau di-deploy ke Railway. Gak perlu ubah kode apa pun.

## Catatan Penting

- **Jangan commit `.env` atau `service_account.json` ke Git** — kalau pakai Git,
  tambahin keduanya ke `.gitignore`.
- Kalau bot di-restart, "state" navigasi user (lagi di folder mana) akan reset —
  ini normal, user tinggal `/start` ulang.
- Limit ukuran file ditentukan Telegram (bukan bot ini) — akun biasa bisa upload
  sampai 2GB per file lewat Pyrogram.
