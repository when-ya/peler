"""
Wrapper untuk semua operasi ke Google Sheets:
- Catat metadata video baru
- List video (buat menu "Daftar Video")
- Cari video
- Update status (misal pas dihapus)
"""
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import config

_client = None
_sheet = None

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Urutan kolom di sheet -- HARUS sama persis sama header di spreadsheet
HEADERS = ["Timestamp", "Uploader", "Folder Path", "Nama File", "Size", "Link", "Status"]


def get_sheet():
    """Lazy-init koneksi ke Google Sheets, di-reuse setelah pertama kali connect."""
    global _client, _sheet
    if _sheet is None:
        if config.GOOGLE_SERVICE_ACCOUNT_JSON:
            # Deploy di Railway/hosting: JSON diambil langsung dari env variable
            service_account_info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
            creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        else:
            # Lokal: baca dari file fisik
            creds = Credentials.from_service_account_file(
                config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        _client = gspread.authorize(creds)
        _sheet = _client.open_by_key(config.SPREADSHEET_ID).sheet1
    return _sheet


def format_size(size_bytes: int) -> str:
    """Convert bytes ke format MB/GB yang gampang dibaca."""
    size_mb = size_bytes / (1024 * 1024)
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB"
    return f"{size_mb:.2f} MB"


def log_upload(uploader: str, folder_path: str, file_name: str, size_bytes: int, link: str):
    """Tambah row baru setiap kali ada upload sukses."""
    sheet = get_sheet()
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        uploader,
        folder_path,
        file_name,
        format_size(size_bytes),
        link,
        "Aktif",
    ]
    sheet.append_row(row)


def get_all_videos():
    """Ambil semua record video (buat menu 'Daftar Video')."""
    sheet = get_sheet()
    records = sheet.get_all_records()
    return records


def search_videos(keyword: str):
    """Cari video berdasarkan nama file (case-insensitive, partial match)."""
    records = get_all_videos()
    keyword_lower = keyword.lower()
    return [r for r in records if keyword_lower in str(r.get("Nama File", "")).lower()]


def get_latest_video():
    """Ambil record video paling terakhir diupload."""
    records = get_all_videos()
    return records[-1] if records else None


def mark_deleted(file_name: str, link: str):
    """
    Update status row jadi 'Dihapus' berdasarkan match nama file + link
    (biar gak ketuker kalau ada nama file yang sama tapi beda folder).
    """
    sheet = get_sheet()
    all_values = sheet.get_all_values()
    for idx, row in enumerate(all_values[1:], start=2):  # skip header, row mulai dari 2
        if len(row) >= 6 and row[3] == file_name and row[5] == link:
            sheet.update_cell(idx, 7, "Dihapus")
            return True
    return False


def get_active_rows():
    """
    Ambil semua row berstatus 'Aktif' beserta nomor row-nya di spreadsheet.
    Dipakai buat pengecekan berkala -- untuk masing-masing row, dicek apakah
    file-nya masih ada di B2 atau tidak.
    """
    sheet = get_sheet()
    all_values = sheet.get_all_values()
    rows = []
    for idx, row in enumerate(all_values[1:], start=2):  # skip header
        if len(row) >= 7 and row[6] == "Aktif":
            rows.append({
                "row_index": idx,
                "folder_path": row[2],
                "file_name": row[3],
                "link": row[5],
            })
    return rows


def set_status(row_index: int, status: str):
    """Update kolom Status (kolom G) di row tertentu."""
    sheet = get_sheet()
    sheet.update_cell(row_index, 7, status)
