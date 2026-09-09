"""
Cek semua video berstatus 'Aktif' di Google Sheets, verifikasi apakah
file-nya masih ada di B2. Kalau sudah tidak ada -- baik karena dihapus
lewat bot maupun dihapus manual langsung di B2 -- status di Sheets
otomatis diupdate jadi 'Tidak Aktif'.
"""
import b2_client
import sheets_client


def run_check() -> dict:
    """
    Jalankan pengecekan sekali. Return ringkasan hasil:
    {"checked": ..., "deactivated": ..., "deactivated_names": [...], "skipped": ...}

    "skipped" itu video yang GAGAL dicek (network/timeout/dll) -- statusnya
    dibiarin apa adanya, gak ditandain 'Tidak Aktif' cuma gara-gara gangguan
    sesaat pas ngecek.
    """
    active_rows = sheets_client.get_active_rows()
    checked = 0
    deactivated = 0
    deactivated_names = []
    skipped = 0

    for row in active_rows:
        # "(root)" itu cuma teks tampilan doang di Sheets buat video yang
        # di-upload ke folder root -- pas mau dicek ke B2, harus di-translate
        # balik jadi string kosong, biar path-nya bener (gak ada prefix aneh).
        folder_path = row["folder_path"]
        if folder_path == "(root)":
            folder_path = ""

        remote_path = f"{folder_path}{row['file_name']}"

        try:
            exists = b2_client.file_exists(remote_path)
        except Exception:
            # Gagal ngecek (bukan berarti file gak ada) -- skip, jangan ubah status.
            skipped += 1
            continue

        checked += 1
        if not exists:
            sheets_client.set_status(row["row_index"], "Tidak Aktif")
            deactivated += 1
            deactivated_names.append(row["file_name"])

    return {
        "checked": checked,
        "deactivated": deactivated,
        "deactivated_names": deactivated_names,
        "skipped": skipped,
    }
