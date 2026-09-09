"""
Bot Telegram untuk upload video ke Backblaze B2 dengan navigasi folder,
dan auto-catat link + metadata ke Google Sheets.

Cara jalanin:
    python bot.py
"""
import os
import asyncio
import tempfile

from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
)

import config
import b2_client
import sheets_client
import link_checker

config.validate()

# Pastikan folder session ada -- di hosting kayak Railway, folder kosong
# gak ikut ke-push lewat Git, jadi perlu dibuat manual saat startup.
os.makedirs("sessions", exist_ok=True)

app = Client(
    "video_bot_session",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    workdir="sessions",
)

# ============================================
# STATE MANAGEMENT (in-memory, per user)
# ============================================
# Nyimpen lagi di folder mana user browsing, dan lagi mode apa
# (mode "navigate" = cuma liat-liat, mode "upload_target" = habis ini kirim video)
#
# Kalau bot restart, state ini hilang -- gak masalah, user tinggal /start lagi.
user_state = {}


def get_state(user_id: int) -> dict:
    if user_id not in user_state:
        user_state[user_id] = {"path": "", "mode": "navigate"}
    return user_state[user_id]


def is_allowed(user_id: int) -> bool:
    """Kalau ALLOWED_USER_IDS kosong di .env, semua orang boleh akses (mode bebas)."""
    if not config.ALLOWED_USER_IDS:
        return True
    return user_id in config.ALLOWED_USER_IDS


# ============================================
# HELPER: bikin keyboard navigasi folder
# ============================================
def build_folder_keyboard(prefix: str, mode: str):
    """
    Bikin inline keyboard isi daftar folder di path 'prefix'.
    mode dipakai buat nentuin callback_data prefix (browse: vs pick:)
    biar bot tau ini lagi mode liat-liat atau mode milih folder tujuan upload.
    """
    listing = b2_client.list_folder(prefix)
    buttons = []

    for folder in listing["folders"]:
        full_path = f"{prefix}{folder}/"
        buttons.append([
            InlineKeyboardButton(f"📁 {folder}", callback_data=f"{mode}:{full_path}")
        ])

    # tombol aksi tambahan
    action_row = []
    if mode == "pick":
        action_row.append(
            InlineKeyboardButton("✅ Upload ke sini", callback_data=f"confirm_upload:{prefix}")
        )
    action_row.append(
        InlineKeyboardButton("🆕 Buat Folder Baru", callback_data=f"newfolder:{prefix}")
    )
    buttons.append(action_row)

    if prefix:  # kalau bukan root, kasih tombol kembali
        parent = "/".join(prefix.rstrip("/").split("/")[:-1])
        parent = f"{parent}/" if parent else ""
        buttons.append([
            InlineKeyboardButton("⬅️ Kembali", callback_data=f"{mode}:{parent}")
        ])

    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])

    return InlineKeyboardMarkup(buttons)


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload Video", callback_data="pick:")],
        [InlineKeyboardButton("📁 Daftar Video", callback_data="list_videos:0")],
        [InlineKeyboardButton("🔗 Link Terakhir", callback_data="latest_link")],
        [InlineKeyboardButton("🔍 Cari Video", callback_data="search_prompt")],
    ])


async def safe_edit_text(message: Message, text: str, reply_markup=None):
    """
    Wrapper buat edit_text yang aman dari error MESSAGE_NOT_MODIFIED.
    Error ini muncul kalau bot coba edit pesan dengan isi yang PERSIS SAMA
    (misal user pencet tombol yang sama dua kali) -- Telegram nolak dan
    error ini gak berbahaya, jadi cukup diabaikan aja.
    """
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except MessageNotModified:
        pass


MAX_DOWNLOAD_RETRIES = 3


async def download_with_retry(message: Message, local_path: str, status_msg: Message):
    """
    Download file dari Telegram dengan retry otomatis.
    Koneksi ke server Telegram kadang timeout, terutama buat file besar --
    daripada langsung gagal total, coba ulang beberapa kali dulu.
    """
    last_error = None
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        try:
            await message.download(file_name=local_path)
            return  # sukses, keluar dari fungsi
        except Exception as e:
            last_error = e
            if attempt < MAX_DOWNLOAD_RETRIES:
                await status_msg.edit_text(
                    f"⚠️ Download gagal (percobaan {attempt}/{MAX_DOWNLOAD_RETRIES}), coba lagi..."
                )
                await asyncio.sleep(3)  # jeda sebentar sebelum retry

    # kalau semua percobaan gagal, lempar error terakhir biar ke-handle di video_handler
    raise last_error


# ============================================
# COMMAND: /start
# ============================================
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    if not is_allowed(message.from_user.id):
        await message.reply("⛔ Maaf, kamu tidak punya akses ke bot ini.")
        return

    user_state[message.from_user.id] = {"path": "", "mode": "navigate"}
    await message.reply(
        "👋 **Video Storage Bot**\n\nPilih menu di bawah:",
        reply_markup=main_menu_keyboard(),
    )


# ============================================
# CALLBACK: kembali ke menu utama
# ============================================
@app.on_callback_query(filters.regex("^main_menu$"))
async def main_menu_callback(client: Client, cq: CallbackQuery):
    await safe_edit_text(cq.message, 
        "👋 **Video Storage Bot**\n\nPilih menu di bawah:",
        reply_markup=main_menu_keyboard(),
    )


# ============================================
# CALLBACK: navigasi folder (mode browse & pick)
# ============================================
@app.on_callback_query(filters.regex("^(browse|pick):"))
async def folder_navigate_callback(client: Client, cq: CallbackQuery):
    mode, path = cq.data.split(":", 1)
    state = get_state(cq.from_user.id)
    state["path"] = path
    state["mode"] = mode

    label = "📤 Pilih folder tujuan upload:" if mode == "pick" else "📁 Browsing folder:"
    current = path if path else "(root)"

    await safe_edit_text(cq.message, 
        f"{label}\n`{current}`",
        reply_markup=build_folder_keyboard(path, mode),
    )
    await cq.answer()


# ============================================
# CALLBACK: konfirmasi folder tujuan upload
# ============================================
@app.on_callback_query(filters.regex("^confirm_upload:"))
async def confirm_upload_callback(client: Client, cq: CallbackQuery):
    _, path = cq.data.split(":", 1)
    state = get_state(cq.from_user.id)
    state["mode"] = "waiting_video"
    state["path"] = path

    await safe_edit_text(cq.message, 
        f"✅ Folder tujuan diset ke:\n`{path if path else '(root)'}`\n\n"
        "📎 Sekarang kirim video-nya ke chat ini."
    )
    await cq.answer()


# ============================================
# CALLBACK: buat folder baru
# ============================================
@app.on_callback_query(filters.regex("^newfolder:"))
async def newfolder_callback(client: Client, cq: CallbackQuery):
    _, path = cq.data.split(":", 1)
    state = get_state(cq.from_user.id)
    state["mode"] = "waiting_folder_name"
    state["path"] = path

    await safe_edit_text(cq.message, 
        f"🆕 Bikin folder baru di dalam:\n`{path if path else '(root)'}`\n\n"
        "Ketik nama folder yang mau dibuat."
    )
    await cq.answer()


# ============================================
# MESSAGE: nama folder baru (teks biasa, dicek state-nya)
# ============================================
@app.on_message(filters.text & filters.private & ~filters.regex(r"^/"))
async def text_handler(client: Client, message: Message):
    if not is_allowed(message.from_user.id):
        return

    state = get_state(message.from_user.id)

    if state["mode"] == "waiting_folder_name":
        folder_name = message.text.strip().strip("/")
        new_path = f"{state['path']}{folder_name}/"
        b2_client.create_folder_marker(new_path)
        state["mode"] = "pick"
        state["path"] = new_path
        await message.reply(
            f"✅ Folder `{folder_name}` berhasil dibuat.",
            reply_markup=build_folder_keyboard(new_path, "pick"),
        )
        return

    if state["mode"] == "waiting_search":
        state["mode"] = "navigate"
        results = sheets_client.search_videos(message.text.strip())
        await reply_search_results(message, results)
        return

    # default: kalau ngetik teks bebas tanpa konteks, arahin ke /start
    await message.reply("Ketik /start untuk buka menu.")


# ============================================
# MESSAGE: terima video (upload flow)
# ============================================
@app.on_message((filters.video | filters.document) & filters.private)
async def video_handler(client: Client, message: Message):
    if not is_allowed(message.from_user.id):
        return

    state = get_state(message.from_user.id)
    if state["mode"] != "waiting_video":
        await message.reply(
            "ℹ️ Mau upload ke folder mana dulu? Pencet 📤 Upload Video di /start."
        )
        return

    target_folder = state["path"]
    file_name = (
        message.video.file_name if message.video and message.video.file_name
        else message.document.file_name if message.document
        else f"video_{message.id}.mp4"
    )
    remote_path = f"{target_folder}{file_name}"

    status_msg = await message.reply("⬇️ Mendownload dari Telegram...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = os.path.join(tmp_dir, file_name)

        try:
            await download_with_retry(message, local_path, status_msg)
        except Exception as e:
            state["mode"] = "navigate"
            await status_msg.edit_text(
                "❌ **Download gagal** setelah beberapa kali percobaan.\n\n"
                f"Error: `{str(e)[:200]}`\n\n"
                "Ini biasanya karena koneksi ke server Telegram lagi gak stabil, "
                "terutama untuk file besar. Coba upload ulang, atau coba lagi beberapa saat lagi."
            )
            return

        await status_msg.edit_text("⬆️ Mengupload ke cloud storage...")
        try:
            b2_client.upload_file(local_path, remote_path)
            link = b2_client.get_download_url(remote_path)
            size_bytes = os.path.getsize(local_path)
        except Exception as e:
            state["mode"] = "navigate"
            await status_msg.edit_text(
                "❌ **Upload ke storage gagal.**\n\n"
                f"Error: `{str(e)[:200]}`\n\n"
                "Video sudah berhasil didownload dari Telegram, tapi gagal diupload "
                "ke cloud storage. Coba upload ulang."
            )
            return

        await status_msg.edit_text("📝 Mencatat ke Google Sheets...")
        uploader_name = message.from_user.first_name or str(message.from_user.id)
        try:
            sheets_client.log_upload(
                uploader=uploader_name,
                folder_path=target_folder if target_folder else "(root)",
                file_name=file_name,
                size_bytes=size_bytes,
                link=link,
            )
        except Exception as e:
            state["mode"] = "navigate"
            await status_msg.edit_text(
                "⚠️ **Video sudah terupload**, tapi gagal dicatat ke Google Sheets.\n\n"
                f"Error: `{str(e)[:200]}`\n\n"
                f"🔗 Link (simpan manual): {link}"
            )
            return

    state["mode"] = "navigate"

    await status_msg.edit_text(
        f"✅ **Upload selesai!**\n\n"
        f"📁 Folder: `{target_folder if target_folder else '(root)'}`\n"
        f"🎬 File: `{file_name}`\n"
        f"📦 Size: {sheets_client.format_size(size_bytes)}\n"
        f"🔗 Link: {link}"
    )


# ============================================
# CALLBACK: daftar video (dari Sheets, dengan pagination sederhana)
# ============================================
PAGE_SIZE = 10


@app.on_callback_query(filters.regex("^list_videos:"))
async def list_videos_callback(client: Client, cq: CallbackQuery):
    _, page_str = cq.data.split(":", 1)
    page = int(page_str)

    records = sheets_client.get_all_videos()
    active = [r for r in records if r.get("Status") == "Aktif"]

    if not active:
        await safe_edit_text(cq.message, 
            "📁 Belum ada video yang tercatat.",
            reply_markup=main_menu_keyboard(),
        )
        await cq.answer()
        return

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = active[start:end]

    text_lines = [f"📁 **Daftar Video** (halaman {page + 1})\n"]
    for r in page_items:
        text_lines.append(f"🎬 `{r['Nama File']}`\n📂 {r['Folder Path']}\n🔗 {r['Link']}\n")

    nav_buttons = []
    if start > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"list_videos:{page - 1}"))
    if end < len(active):
        nav_buttons.append(InlineKeyboardButton("➡️ Berikutnya", callback_data=f"list_videos:{page + 1}"))

    buttons = [nav_buttons] if nav_buttons else []
    buttons.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])

    await safe_edit_text(cq.message, "\n".join(text_lines), reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


# ============================================
# CALLBACK: link video terakhir
# ============================================
@app.on_callback_query(filters.regex("^latest_link$"))
async def latest_link_callback(client: Client, cq: CallbackQuery):
    latest = sheets_client.get_latest_video()
    if not latest:
        await cq.answer("Belum ada video yang diupload.", show_alert=True)
        return

    await safe_edit_text(cq.message, 
        f"🔗 **Video Terakhir**\n\n"
        f"🎬 `{latest['Nama File']}`\n"
        f"📂 {latest['Folder Path']}\n"
        f"🔗 {latest['Link']}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]),
    )
    await cq.answer()


# ============================================
# CALLBACK: mulai pencarian
# ============================================
@app.on_callback_query(filters.regex("^search_prompt$"))
async def search_prompt_callback(client: Client, cq: CallbackQuery):
    state = get_state(cq.from_user.id)
    state["mode"] = "waiting_search"
    await safe_edit_text(cq.message, "🔍 Ketik kata kunci nama video yang mau dicari:")
    await cq.answer()


async def reply_search_results(message: Message, results: list):
    if not results:
        await message.reply(
            "❌ Gak ada video yang cocok.",
            reply_markup=main_menu_keyboard(),
        )
        return

    text_lines = ["🔍 **Hasil Pencarian**\n"]
    for r in results[:10]:
        text_lines.append(f"🎬 `{r['Nama File']}`\n📂 {r['Folder Path']}\n🔗 {r['Link']}\n")

    await message.reply(
        "\n".join(text_lines),
        reply_markup=main_menu_keyboard(),
    )


# ============================================
# COMMAND: /checklinks -- cek manual kapan aja (gak perlu nunggu jadwal)
# ============================================
@app.on_message(filters.command("checklinks") & filters.private)
async def checklinks_handler(client: Client, message: Message):
    if not is_allowed(message.from_user.id):
        await message.reply("⛔ Maaf, kamu tidak punya akses ke bot ini.")
        return

    status_msg = await message.reply("🔍 Mengecek semua link video, mohon tunggu...")

    # gspread & b2sdk itu library sync (blocking), jalanin di thread terpisah
    # biar gak nge-freeze bot pas lagi ngecek banyak file
    result = await asyncio.to_thread(link_checker.run_check)

    if result["deactivated"] == 0:
        skip_note = f"\n\n⚠️ {result['skipped']} video gagal dicek (network/timeout), dicoba lagi nanti." if result["skipped"] else ""
        await status_msg.edit_text(
            f"✅ Selesai! {result['checked']} video dicek, semuanya masih aktif.{skip_note}"
        )
    else:
        names = "\n".join(f"  • `{n}`" for n in result["deactivated_names"])
        skip_note = f"\n\n⚠️ {result['skipped']} video gagal dicek (network/timeout), dicoba lagi nanti." if result["skipped"] else ""
        await status_msg.edit_text(
            f"✅ Selesai! {result['checked']} video dicek.\n\n"
            f"⚠️ {result['deactivated']} video ditandai **Tidak Aktif** (file sudah tidak ada di storage):\n"
            f"{names}{skip_note}"
        )


# ============================================
# BACKGROUND TASK: cek link secara berkala otomatis
# ============================================
async def periodic_link_check():
    """
    Jalan terus di background selama bot hidup. Tiap beberapa jam sekali,
    otomatis cek semua video 'Aktif' dan update status kalau file-nya
    udah gak ada di B2 (baik dihapus lewat bot atau manual di B2 console).
    """
    interval_seconds = config.CHECK_INTERVAL_HOURS * 3600

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            result = await asyncio.to_thread(link_checker.run_check)
            if result["deactivated"] > 0:
                print(
                    f"🔍 [Auto-check] {result['checked']} video dicek, "
                    f"{result['deactivated']} ditandai Tidak Aktif: {result['deactivated_names']}"
                )
        except Exception as e:
            print(f"⚠️ [Auto-check] Gagal jalanin pengecekan: {e}")


# ============================================
# RUN
# ============================================
# PENTING: pola di bawah ini SENGAJA dibikin semirip mungkin sama app.run()
# bawaan Pyrogram (start -> idle -> stop), yang udah kebukti stabil.
# JANGAN tambahin retry-loop manual yang manggil app.start() berkali-kali
# dalam satu proses yang sama -- itu yang kemarin bikin bot gagal nerima
# update sama sekali walau keliatan "berhasil" login di log.
# ============================================
# RUN
# ============================================
# PENTING: app.loop.create_task() dipanggil SEBELUM app.run(), pakai loop
# yang SAMA yang udah dipegang Pyrogram Client dari awal. Ini beda sama
# asyncio.run(main()) yang bikin event loop BARU -- itu yang kemarin bikin
# bot keliatan "jalan" tapi semua pesan masuk gak pernah beneran nyampe ke
# handler (nyangkut di loop yang beda). JANGAN ganti pola ini lagi.
if __name__ == "__main__":
    print("🤖 Bot jalan...")
    app.loop.create_task(periodic_link_check())
    print(f"🔍 Auto-check link aktif setiap {config.CHECK_INTERVAL_HOURS} jam.")
    app.run()
