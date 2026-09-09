"""
Wrapper untuk semua operasi ke Backblaze B2:
- List folder & subfolder (pakai prefix + delimiter)
- Upload file
- Generate link
- Hapus file
"""
import config
from b2sdk.v2 import InMemoryAccountInfo, B2Api
from b2sdk.v2.exception import FileNotPresent

_b2_api = None
_bucket = None


def get_bucket(force_refresh: bool = False):
    """
    Lazy-init koneksi ke B2, dipanggil sekali aja terus di-reuse.
    Token otentikasi B2 cuma valid ~24 jam -- kalau force_refresh=True,
    paksa re-autentikasi ulang (dipakai pas ketauan token udah kadaluarsa).
    """
    global _b2_api, _bucket
    if _bucket is None or force_refresh:
        info = InMemoryAccountInfo()
        _b2_api = B2Api(info)
        _b2_api.authorize_account("production", config.B2_KEY_ID, config.B2_APPLICATION_KEY)
        _bucket = _b2_api.get_bucket_by_name(config.B2_BUCKET_NAME)
    return _bucket


def list_folder(prefix: str = ""):
    """
    List isi folder di level tertentu.
    prefix kosong = root bucket.
    prefix "video-1/Komedi/" = isi dalam folder itu.

    Return: dict {"folders": [...], "files": [...]}
    Folder dan file dipisah biar gampang di-render jadi tombol.
    """
    bucket = get_bucket()
    folders = set()
    files = []

    # delimiter="/" bikin B2 cuma balikin 1 level folder di bawah prefix,
    # bukan semua isi rekursif
    for file_version, folder_name in bucket.ls(folder_to_list=prefix, latest_only=True, recursive=False):
        if folder_name:
            # ini folder -> ambil nama folder-nya aja (tanpa prefix parent)
            folder_name_clean = folder_name[len(prefix):].rstrip("/")
            if folder_name_clean:
                folders.add(folder_name_clean)
        else:
            # ini file beneran
            file_name = file_version.file_name
            display_name = file_name[len(prefix):]
            if display_name:  # skip kalau nama filenya kosong (folder marker)
                files.append({
                    "name": display_name,
                    "full_path": file_name,
                    "size": file_version.size,
                })

    return {"folders": sorted(folders), "files": files}


def create_folder_marker(prefix: str):
    """
    B2 gak punya konsep folder asli, folder cuma 'muncul' kalau ada file di dalamnya.
    Trik umum: upload file kosong bernama '.keep' di dalam folder biar folder itu kebentuk.
    """
    bucket = get_bucket()
    path = prefix.rstrip("/") + "/.keep"
    bucket.upload_bytes(b"", path)
    return path


def upload_file(local_path: str, remote_path: str, progress_callback=None):
    """
    Upload file lokal ke B2 di path tertentu (termasuk folder-nya).
    remote_path contoh: 'video-1/Komedi/Komedi Indonesia/lucu-banget.mp4'
    """
    bucket = get_bucket()
    uploaded_file = bucket.upload_local_file(
        local_file=local_path,
        file_name=remote_path,
        progress_listener=progress_callback,
    )
    return uploaded_file


def get_download_url(remote_path: str) -> str:
    """
    Generate link download.
    Kalau CUSTOM_DOMAIN diisi di .env, pakai itu (link lebih rapi + egress gratis via Cloudflare).
    Kalau enggak, pakai link native B2.
    """
    if config.CUSTOM_DOMAIN:
        return f"https://{config.CUSTOM_DOMAIN}/{remote_path}"

    bucket = get_bucket()
    return bucket.get_download_url(remote_path)


def delete_file(remote_path: str):
    """Hapus file dari bucket berdasarkan path lengkapnya."""
    bucket = get_bucket()
    file_version = bucket.get_file_info_by_name(remote_path)
    bucket.delete_file_version(file_version.id_, remote_path)


def file_exists(remote_path: str) -> bool:
    """
    Cek apakah file masih ada di bucket.
    Dipakai buat pengecekan berkala -- kalau file udah dihapus (baik lewat bot
    atau manual langsung di B2), fungsi ini balikin False.

    PENTING: cuma balikin False kalau BENERAN dapet konfirmasi file gak ada
    (FileNotPresent). Error lain (network glitch, timeout, dll) di-raise ulang
    biar gak salah nandain video yang sebenernya masih ada jadi 'Tidak Aktif'.

    Kalau errornya karena token otentikasi B2 udah kadaluarsa (biasanya abis
    ~24 jam), otomatis re-autentikasi sekali dan coba ulang sebelum nyerah.
    """
    bucket = get_bucket()
    try:
        bucket.get_file_info_by_name(remote_path)
        return True
    except FileNotPresent:
        return False
    except Exception:
        # Kemungkinan token expired atau koneksi ke B2 kepake sesi lama --
        # paksa re-auth sekali, lalu coba lagi sebelum bener-bener nyerah.
        bucket = get_bucket(force_refresh=True)
        try:
            bucket.get_file_info_by_name(remote_path)
            return True
        except FileNotPresent:
            return False
