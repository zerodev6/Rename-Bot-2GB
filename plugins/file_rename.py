from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import jishubotz
from asyncio import sleep
from PIL import Image
import os, time, re, random, asyncio


# ─────────────────────────────────────────
# ⚡ SPEED CONFIG
# ─────────────────────────────────────────
MAX_FILE_SIZE = 2000 * 1024 * 1024   # 2GB limit
DOWNLOAD_DIR  = "downloads"
METADATA_DIR  = "Metadata"


# ─────────────────────────────────────────
# 📥 STEP 1 — ASK FOR NEW FILE NAME
# ─────────────────────────────────────────
@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def rename_start(client, message):
    file     = getattr(message, message.media.value)
    filename = getattr(file, "file_name", "Unknown")

    # ── File size guard ──
    if file.file_size > MAX_FILE_SIZE:
        return await message.reply_text(
            "❌ **File Too Large!**\n\nThis bot does not support files bigger than **2GB**.",
            quote=True
        )

    text = (
        f"✏️ **Please Enter New Filename...**\n\n"
        f"📄 **Old File Name :-** `{filename}`"
    )

    try:
        await message.reply_text(
            text=text,
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True)
        )
    except FloodWait as e:
        await sleep(e.value)
        await message.reply_text(
            text=text,
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True)
        )
    except Exception as e:
        print(f"[rename_start] Error: {e}")


# ─────────────────────────────────────────
# ✏️ STEP 2 — RECEIVE NEW NAME & PICK TYPE
# ─────────────────────────────────────────
@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message

    # Only handle ForceReply responses
    if not (reply_message.reply_markup and isinstance(reply_message.reply_markup, ForceReply)):
        return

    new_name = message.text.strip()
    await message.delete()

    msg  = await client.get_messages(message.chat.id, reply_message.id)
    file = msg.reply_to_message

    if not file or not file.media:
        return

    media = getattr(file, file.media.value)

    # ── Auto-add extension if missing ──
    if "." not in new_name:
        extn = (
            media.file_name.rsplit('.', 1)[-1]
            if (hasattr(media, "file_name") and media.file_name and "." in media.file_name)
            else "mkv"
        )
        new_name = f"{new_name}.{extn}"

    await reply_message.delete()

    # ── Build upload type buttons ──
    button = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]

    if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
        button.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
    elif file.media == MessageMediaType.AUDIO:
        button.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])

    # ✅ CRITICAL: Keep ":-" so doc() can split filename correctly
    await message.reply(
        text=(
            f"📂 **Select Output File Type**\n\n"
            f"📄 **File Name :-** `{new_name}`"
        ),
        reply_to_message_id=file.id,
        reply_markup=InlineKeyboardMarkup(button)
    )


# ─────────────────────────────────────────
# 🚀 STEP 3 — DOWNLOAD → METADATA → UPLOAD
# ─────────────────────────────────────────
@Client.on_callback_query(filters.regex("upload"))
async def doc(bot, update):

    # ── Ensure directories exist ──
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(METADATA_DIR, exist_ok=True)

    chat_id     = update.message.chat.id
    upload_type = update.data.split("_")[1]   # document / video / audio

    # ── Extract new filename safely ──
    prefix = await jishubotz.get_prefix(chat_id)
    suffix = await jishubotz.get_suffix(chat_id)

    # ✅ Safe split with backtick cleanup & fallback error
    try:
        raw_name = update.message.text.split(":-")[1].strip()
        raw_name = raw_name.replace("`", "").strip()
    except IndexError:
        return await update.message.edit(
            "❌ **Could not read filename.**\n\nPlease try renaming again."
        )

    try:
        new_filename = add_prefix_suffix(raw_name, prefix, suffix)
    except Exception as e:
        return await update.message.edit(
            f"❌ **Prefix/Suffix Error**\n\n"
            f"**Contact :** @CallAdminRobot\n"
            f"**Error :** `{e}`"
        )

    file      = update.message.reply_to_message
    media     = getattr(file, file.media.value)
    file_path = f"{DOWNLOAD_DIR}/{update.from_user.id}/{new_filename}"
    meta_path = f"{METADATA_DIR}/{new_filename}"

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # ────────────────────────────────
    # ⚡ FAST DOWNLOAD
    # ⚡ progress_for_pyrogram uses
    #    time-gate so edits NEVER
    #    block the transfer loop
    # ────────────────────────────────
    ms         = await update.message.edit("🚀 **Downloading...**  ⚡")
    start_time = time.time()
    try:
        path = await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("🚀 **Downloading...**  ⚡", ms, start_time)
        )
    except Exception as e:
        return await ms.edit(f"❌ **Download Failed**\n\n`{e}`")

    # ────────────────────────────────
    # 🏷 METADATA
    # ────────────────────────────────
    _bool_metadata = await jishubotz.get_metadata(chat_id)

    if _bool_metadata:
        metadata_code = await jishubotz.get_metadata_code(chat_id)
        await ms.edit("🏷 **Adding Metadata...**  ⚡")
        await add_metadata(path, meta_path, metadata_code, ms)
        upload_path = meta_path
    else:
        await ms.edit("⚙️ **Processing...**  ⚡")
        upload_path = file_path

    # ────────────────────────────────
    # ⏱ GET DURATION
    # ────────────────────────────────
    duration = 0
    try:
        parser = createParser(file_path)
        if parser:
            meta = extractMetadata(parser)
            if meta and meta.has("duration"):
                duration = meta.get("duration").seconds
            parser.close()
    except:
        pass

    # ────────────────────────────────
    # 🖼 THUMBNAIL
    # ────────────────────────────────
    ph_path = None
    c_thumb = await jishubotz.get_thumbnail(chat_id)

    try:
        if c_thumb:
            # ── User custom thumbnail ──
            ph_path = await bot.download_media(c_thumb)
            _, _, ph_path = await fix_thumb(ph_path)
        elif getattr(media, "thumbs", None):
            # ── Auto-generate from video ──
            safe_duration = max(duration - 1, 0)
            ph_path_ = await take_screen_shot(
                file_path,
                os.path.dirname(os.path.abspath(file_path)),
                random.randint(0, safe_duration)
            )
            _, _, ph_path = await fix_thumb(ph_path_)
    except Exception as e:
        ph_path = None
        print(f"[Thumbnail] Error: {e}")

    # ────────────────────────────────
    # 📝 CAPTION
    # ────────────────────────────────
    c_caption = await jishubotz.get_caption(chat_id)

    if c_caption:
        try:
            caption = c_caption.format(
                filename=new_filename,
                filesize=humanbytes(media.file_size),
                duration=convert(duration)
            )
        except Exception as e:
            return await ms.edit(
                f"❌ **Caption Error**\n\n"
                f"Invalid keyword argument: `{e}`"
            )
    else:
        caption = f"**{new_filename}**"

    # ────────────────────────────────
    # ⚡ FAST UPLOAD
    # ⚡ fresh start_time so upload
    #    progress is accurate
    # ────────────────────────────────
    await ms.edit("💠 **Uploading...**  ⚡")
    start_time = time.time()    # ✅ Reset timer for upload progress

    try:
        progress_args = ("💠 **Uploading...**  ⚡", ms, start_time)

        if upload_type == "document":
            await bot.send_document(
                chat_id,
                document=upload_path,
                thumb=ph_path,
                caption=caption,
                force_document=True,
                progress=progress_for_pyrogram,
                progress_args=progress_args
            )

        elif upload_type == "video":
            await bot.send_video(
                chat_id,
                video=upload_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                supports_streaming=True,    # ⚡ Faster streaming upload
                progress=progress_for_pyrogram,
                progress_args=progress_args
            )

        elif upload_type == "audio":
            await bot.send_audio(
                chat_id,
                audio=upload_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=progress_args
            )

    except Exception as e:
        return await ms.edit(f"❌ **Upload Failed**\n\n`{e}`")

    finally:
        # ✅ Always clean up — even if upload crashes
        try:
            await ms.delete()
        except:
            pass
        for path_to_clean in [file_path, meta_path, ph_path]:
            try:
                if path_to_clean and os.path.exists(path_to_clean):
                    os.remove(path_to_clean)
            except:
                pass


# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @MadflixBotz
# Backup Channel @JishuBotz
# Developer @JishuDeveloper
# Contact @MadflixSupport
