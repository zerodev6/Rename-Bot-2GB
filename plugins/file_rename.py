from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import jishubotz
import os, time, re, random, asyncio

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def rename_start(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry! This bot is limited to 2GB files.", quote=True)
    
    try:
        await message.reply_text(
            text=f"**Please Enter New Filename...**\n\n**Old Name**: `{filename}`",
            reply_to_message_id=message.id,
            reply_markup=ForceReply(True)
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
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
            new_name = f"{new_name}.{extn}"
        
        await reply_message.delete()

        button = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
        if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
            button.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
        elif file.media == MessageMediaType.AUDIO:
            button.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])
            
        await message.reply(
            text=f"**Select Output Type**\n\n**New Name**: `{new_name}`",
            reply_to_message_id=file.id,
            reply_markup=InlineKeyboardMarkup(button)
        )

@Client.on_callback_query(filters.regex("upload"))
async def doc(bot, update):
    # ── STEP 1: Fast Directory Setup
    user_id = update.from_user.id
    os.makedirs(f"downloads/{user_id}", exist_ok=True)
    os.makedirs("Metadata", exist_ok=True)

    # ── STEP 2: Parallel Database Fetch (SPEED UP)
    # Fetching all settings at once instead of individual requests
    prefix, suffix, _bool_metadata, c_caption, c_thumb, metadata_code = await asyncio.gather(
        jishubotz.get_prefix(update.message.chat.id),
        jishubotz.get_suffix(update.message.chat.id),
        jishubotz.get_metadata(update.message.chat.id),
        jishubotz.get_caption(update.message.chat.id),
        jishubotz.get_thumbnail(update.message.chat.id),
        jishubotz.get_metadata_code(update.message.chat.id)
    )

    new_name_raw = update.message.text.split(":-")[1].strip()
    new_filename = add_prefix_suffix(new_name_raw, prefix, suffix)

    file_path = f"downloads/{user_id}/{new_filename}"
    file = update.message.reply_to_message
    media = getattr(file, file.media.value)

    ms = await update.message.edit("🚀 **Initializing Ultra-Fast Download...**")

    # ── STEP 3: Optimized Download
    try:
        path = await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("🚀 **Downloading...**", ms, time.time())
        )
    except Exception as e:
        return await ms.edit(f"Download Error: {e}")

    # ── STEP 4: Processing
    upload_path = path
    if _bool_metadata:
        await ms.edit("⚙️ **Applying Metadata...**")
        metadata_path = f"Metadata/{new_filename}"
        await add_metadata(path, metadata_path, metadata_code, ms)
        if os.path.exists(metadata_path):
            upload_path = metadata_path

    # Extract Duration for better Video Uploads
    duration = 0
    try:
        parser = createParser(upload_path)
        meta = extractMetadata(parser)
        if meta and meta.has("duration"):
            duration = meta.get('duration').seconds
        parser.close()
    except:
        pass

    # Thumbnail Handling
    ph_path = None
    if c_thumb:
        ph_path = await bot.download_media(c_thumb)
        _, _, ph_path = await fix_thumb(ph_path)
    elif media.thumbs:
        # Take existing thumb if available
        ph_path = await bot.download_media(media.thumbs[0].file_id)
        _, _, ph_path = await fix_thumb(ph_path)

    # Caption logic
    if c_caption:
        caption = c_caption.format(filename=new_filename, filesize=humanbytes(media.file_size), duration=convert(duration))
    else:
        caption = f"**{new_filename}**"

    # ── STEP 5: Optimized Upload
    await ms.edit("💠 **Uploading at Max Speed...**")
    upload_type = update.data.split("_")[1]
    
    try:
        args = {
            "chat_id": update.message.chat.id,
            "thumb": ph_path,
            "caption": caption,
            "progress": progress_for_pyrogram,
            "progress_args": ("💠 **Uploading...**", ms, time.time())
        }

        if upload_type == "document":
            await bot.send_document(document=upload_path, **args)
        elif upload_type == "video":
            await bot.send_video(video=upload_path, duration=duration, **args)
        elif upload_type == "audio":
            await bot.send_audio(audio=upload_path, duration=duration, **args)
            
    except Exception as e:
        await ms.edit(f"Upload Error: {e}")
    finally:
        await ms.delete()
        # Cleanup
        for f in [file_path, ph_path]:
            if f and os.path.exists(f):
                os.remove(f)
        if _bool_metadata and os.path.exists(f"Metadata/{new_filename}"):
            os.remove(f"Metadata/{new_filename}")
