"""
Konfigurasi project - load semua env variable dari file .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Telegram ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# --- Backblaze B2 ---
B2_KEY_ID = os.getenv("B2_KEY_ID", "")
B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY", "")
B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME", "")
CUSTOM_DOMAIN = os.getenv("CUSTOM_DOMAIN", "").strip()

# --- Google Sheets ---
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

# Dipakai kalau deploy ke Railway/hosting lain yang gak punya file fisik --
# isi seluruh konten JSON service account langsung sebagai env variable.
# Kalau ini diisi, dia diprioritaskan daripada GOOGLE_SERVICE_ACCOUNT_FILE.
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# --- Bot access control ---
_allowed_raw = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [
    int(uid.strip()) for uid in _allowed_raw.split(",") if uid.strip().isdigit()
]

# --- Pengecekan link berkala ---
# Tiap berapa jam bot otomatis cek semua link 'Aktif' dan update status
# kalau file-nya udah gak ada di B2. Default 6 jam.
CHECK_INTERVAL_HOURS = float(os.getenv("CHECK_INTERVAL_HOURS", "6"))

# --- Validasi dasar biar error-nya jelas dari awal, bukan pas runtime ---
def validate():
    missing = []
    if not API_ID:
        missing.append("API_ID")
    if not API_HASH:
        missing.append("API_HASH")
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not B2_KEY_ID:
        missing.append("B2_KEY_ID")
    if not B2_APPLICATION_KEY:
        missing.append("B2_APPLICATION_KEY")
    if not B2_BUCKET_NAME:
        missing.append("B2_BUCKET_NAME")
    if not SPREADSHEET_ID:
        missing.append("SPREADSHEET_ID")

    # Salah satu dari dua ini wajib ada: file lokal ATAU env variable JSON
    if not GOOGLE_SERVICE_ACCOUNT_JSON and not os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        missing.append(
            "GOOGLE_SERVICE_ACCOUNT_JSON atau GOOGLE_SERVICE_ACCOUNT_FILE "
            f"(file '{GOOGLE_SERVICE_ACCOUNT_FILE}' tidak ditemukan dan env JSON kosong)"
        )

    if missing:
        raise SystemExit(
            "\n❌ Konfigurasi belum lengkap di file .env:\n"
            + "\n".join(f"   - {m}" for m in missing)
            + "\n\nCek kembali file .env kamu.\n"
        )
