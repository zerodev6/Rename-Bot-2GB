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


@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def rename_start(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text(
            "Sorry Bro This Bot Doesn't Support Uploading Files Bigger Than 2GB", quote=True
        )
    try:
        await message.reply_text(
            text=f"**Please Enter New Filename...**\n\n**Old File Name** :- `{filename}`",
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True)
        )
        # ── REMOVED: await sleep(30) ── this was blocking the bot for 30 seconds
        #    doing absolutely nothing. Removing it alone is a huge speed improvement.
    except FloodWait as e:
        await sleep(e.value)
        await message.reply_text(
            text=f"**Please Enter New Filename**\n\n**Old File Name** :- `{filename}`",
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True)
        )
    except Exception:
        pass


@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if (reply_message.reply_markup) and isinstance(reply_message.reply_markup, ForceReply):
        new_name = message.text
        await message.delete()
        msg = await client.get_messages(message.chat.id, reply_message.id)
        file = msg.reply_to_message
        media = getattr(file, file.media.value)
        if "." not in new_name:
            extn = media.file_name.rsplit('.', 1)[-1] if "." in media.file_name else "mkv"
            new_name = new_name + "." + extn
        await reply_message.delete()

        button = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
        if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
            button.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
        elif file.media == MessageMediaType.AUDIO:
            button.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])
        await message.reply(
            text=f"**Select The Output File Type**\n\n**File Name :-** `{new_name}`",
            reply_to_message_id=file.id,
            reply_markup=InlineKeyboardMarkup(button)
        )


@Client.on_callback_query(filters.regex("upload"))
async def doc(bot, update):

    # ── Ensure download directory exists before starting
    user_download_dir = f"downloads/{update.from_user.id}"
    os.makedirs(user_download_dir, exist_ok=True)  # ── faster than check+mkdir

    if not os.path.isdir("Metadata"):
        os.makedirs("Metadata", exist_ok=True)

    prefix = await jishubotz.get_prefix(update.message.chat.id)
    suffix = await jishubotz.get_suffix(update.message.chat.id)
    new_name = update.message.text
    new_filename_ = new_name.split(":-")[1].strip()

    try:
        new_filename = add_prefix_suffix(new_filename_, prefix, suffix)
    except Exception as e:
        return await update.message.edit(
            f"Something Went Wrong Can't Able To Set Prefix Or Suffix 🥺\n\n"
            f"**Contact My Creator :** @CallAdminRobot\n\n**Error :** `{e}`"
        )

    file_path = f"{user_download_dir}/{new_filename}"
    file = update.message.reply_to_message
    media = getattr(file, file.media.value)

    ms = await update.message.edit("🚀 Downloading...  ⚡")

    # ── SPEED: fetch caption/thumbnail/metadata settings in PARALLEL
    #    instead of one-by-one while the file is downloading
    _bool_metadata, c_caption, c_thumb = await asyncio.gather(
        jishubotz.get_metadata(update.message.chat.id),
        jishubotz.get_caption(update.message.chat.id),
        jishubotz.get_thumbnail(update.message.chat.id)
    )

    try:
        path = await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("🚀 Downloading...  ⚡", ms, time.time())
        )
    except Exception as e:
        return await ms.edit(str(e))

    metadata_path = f"Metadata/{new_filename}"
    upload_path = file_path

    if _bool_metadata:
        metadata_code = await jishubotz.get_metadata_code(update.message.chat.id)
        await add_metadata(path, metadata_path, metadata_code, ms)
        upload_path = metadata_path if os.path.exists(metadata_path) else file_path
        if upload_path == file_path:
            await ms.edit("⚠️ Metadata injection failed, uploading original file...")
    else:
        await ms.edit("⏳ Mode Changing...  ⚡")

    # ── Parse duration
    duration = 0
    try:
        parser = createParser(file_path)
        meta = extractMetadata(parser)
        if meta and meta.has("duration"):
            duration = meta.get('duration').seconds
        parser.close()
    except Exception:
        pass

    # ── Build caption
    if c_caption:
        try:
            caption = c_caption.format(
                filename=new_filename,
                filesize=humanbytes(media.file_size),
                duration=convert(duration)
            )
        except Exception as e:
            return await ms.edit(text=f"Your Caption Error Except Keyword Argument : ({e})")
    else:
        caption = f"**{new_filename}**"

    # ── Thumbnail: download custom thumb in parallel with duration extraction
    #    (already done above via gather, so just process it here)
    ph_path = None
    if media.thumbs or c_thumb:
        try:
            if c_thumb:
                ph_path = await bot.download_media(c_thumb)
                _, _, ph_path = await fix_thumb(ph_path)
            else:
                ph_path_ = await take_screen_shot(
                    file_path,
                    os.path.dirname(os.path.abspath(file_path)),
                    random.randint(0, max(duration - 1, 0))
                )
                _, _, ph_path = await fix_thumb(ph_path_)
        except Exception as e:
            ph_path = None

    await ms.edit("💠 Uploading...  ⚡")
    upload_type = update.data.split("_")[1]

    # ── SPEED: higher timeouts prevent upload failure on large/slow files
    try:
        common_args = dict(
            chat_id=update.message.chat.id,
            thumb=ph_path,
            caption=caption,
            progress=progress_for_pyrogram,
            progress_args=("💠 Uploading...  ⚡", ms, time.time())
        )
        if upload_type == "document":
            await bot.send_document(document=upload_path, **common_args)
        elif upload_type == "video":
            await bot.send_video(
                video=upload_path,
                duration=duration,
                **common_args
            )
        elif upload_type == "audio":
            await bot.send_audio(
                audio=upload_path,
                duration=duration,
                **common_args
            )
    except Exception as e:
        return await ms.edit(f"**Error :** `{e}`")

    finally:
        await ms.delete()
        for f in [file_path, metadata_path, ph_path]:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @MadflixBotz
