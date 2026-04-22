import math, time, re, os, shutil, asyncio
from datetime import datetime
from pytz import timezone
from config import Config, Txt
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ─────────────────────────────────────────
# ⚡ SPEED CONFIG - Tune these for max speed
# ─────────────────────────────────────────
PROGRESS_UPDATE_DELAY = 3       # Update progress every N seconds
VIDEO_EXTENSIONS  = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']
AUDIO_EXTENSIONS  = ['.mp3', '.flac', '.aac', '.ogg', '.wav', '.m4a', '.opus']


# ─────────────────────────────────────────
# 📊 PROGRESS BAR
# ─────────────────────────────────────────
async def progress_for_pyrogram(current, total, ud_type, message, start):
    now  = time.time()
    diff = now - start

    # Skip update if less than 1s passed or not on the interval (except final)
    if diff < 1 or (round(diff % PROGRESS_UPDATE_DELAY) != 0 and current != total):
        return

    percentage          = current * 100 / total
    speed               = current / diff if diff > 0 else 0
    elapsed_ms          = round(diff) * 1000
    remaining_ms        = round((total - current) / speed) * 1000 if speed > 0 else 0
    estimated_total_ms  = elapsed_ms + remaining_ms

    elapsed_str         = TimeFormatter(milliseconds=elapsed_ms)
    estimated_str       = TimeFormatter(milliseconds=estimated_total_ms)

    filled   = math.floor(percentage / 5)
    progress = "▣" * filled + "▢" * (20 - filled)

    tmp = progress + Txt.PROGRESS_BAR.format(
        round(percentage, 2),
        humanbytes(current),
        humanbytes(total),
        humanbytes(speed),
        estimated_str if estimated_str else "0 s"
    )

    try:
        await message.edit(
            text=f"{ud_type}\n\n{tmp}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✖️ Cancel ✖️", callback_data="close")]]
            )
        )
    except:
        pass


# ─────────────────────────────────────────
# 🔢 HUMAN READABLE BYTES
# ─────────────────────────────────────────
def humanbytes(size):
    if not size:
        return ""
    power     = 2 ** 10
    n         = 0
    power_map = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n    += 1
    return str(round(size, 2)) + " " + power_map[n] + 'B'


# ─────────────────────────────────────────
# ⏱ TIME FORMATTER
# ─────────────────────────────────────────
def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds      = divmod(seconds, 60)
    hours,   minutes      = divmod(minutes, 60)
    days,    hours        = divmod(hours,   24)

    tmp = ((str(days)         + "d, ")  if days         else "") + \
          ((str(hours)        + "h, ")  if hours        else "") + \
          ((str(minutes)      + "m, ")  if minutes      else "") + \
          ((str(seconds)      + "s, ")  if seconds      else "") + \
          ((str(milliseconds) + "ms, ") if milliseconds else "")

    return tmp[:-2] if tmp else "0s"


# ─────────────────────────────────────────
# 🕐 CONVERT SECONDS → HH:MM:SS
# ─────────────────────────────────────────
def convert(seconds):
    seconds = seconds % (24 * 3600)
    hour    = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60
    return "%d:%02d:%02d" % (hour, minutes, seconds)


# ─────────────────────────────────────────
# 📋 LOG NEW USERS
# ─────────────────────────────────────────
async def send_log(b, u):
    if Config.LOG_CHANNEL is not None:
        curr     = datetime.now(timezone("Asia/Kolkata"))
        date_str = curr.strftime('%d %B, %Y')
        time_str = curr.strftime('%I:%M:%S %p')
        await b.send_message(
            Config.LOG_CHANNEL,
            f"<b><u>New User Started The Bot :</u></b>\n\n"
            f"<b>User Mention</b> : {u.mention}\n"
            f"<b>User ID</b>      : <code>{u.id}</code>\n"
            f"<b>First Name</b>   : {u.first_name}\n"
            f"<b>Last Name</b>    : {u.last_name}\n"
            f"<b>User Name</b>    : @{u.username}\n"
            f"<b>User Link</b>    : <a href='tg://openmessage?user_id={u.id}'>Click Here</a>\n\n"
            f"<b>Date</b>         : {date_str}\n"
            f"<b>Time</b>         : {time_str}"
        )


# ─────────────────────────────────────────
# ✏️ ADD PREFIX / SUFFIX TO FILENAME
# ─────────────────────────────────────────
def add_prefix_suffix(input_string, prefix=None, suffix=None):
    pattern = r'(?P<filename>.*?)(\.\w+)?$'
    match   = re.search(pattern, input_string)

    if not match:
        return input_string

    filename  = match.group('filename')
    extension = match.group(2) or ''

    if prefix is None and suffix is None:
        return f"{filename}{extension}"
    elif prefix is None:
        return f"{filename} {suffix}{extension}"
    elif suffix is None:
        return f"{prefix} {filename}{extension}"
    else:
        return f"{prefix} {filename} {suffix}{extension}"


# ─────────────────────────────────────────
# 📁 MAKE DIRECTORY (safe)
# ─────────────────────────────────────────
def makedir(name: str):
    """
    Create a directory. Removes existing one first to ensure clean state.
    """
    if os.path.exists(name):
        shutil.rmtree(name)
    os.makedirs(name, exist_ok=True)


# ─────────────────────────────────────────
# ⚡ FAST DOWNLOAD (optimized)
# ─────────────────────────────────────────
async def fast_download(client, message, file_name, progress_msg=None):
    """
    High-speed file download using Pyrogram's native downloader.
    Pass progress_msg to show a live progress bar during download.
    
    Usage:
        path = await fast_download(client, message, "video.mp4", progress_msg=msg)
    """
    start_time = time.time()

    path = await client.download_media(
        message,
        file_name=file_name,
        progress=progress_for_pyrogram if progress_msg else None,
        progress_args=(
            f"📥 <b>Downloading:</b> <code>{os.path.basename(file_name)}</code>",
            progress_msg,
            start_time
        ) if progress_msg else ()
    )
    return path


# ─────────────────────────────────────────
# ⚡ FAST UPLOAD (optimized, auto file type)
# ─────────────────────────────────────────
async def fast_upload(client, chat_id, file_path, caption="", progress_msg=None, thumb=None):
    """
    High-speed upload with auto file-type detection.
    Supports: video, audio, document.
    Pass progress_msg to show a live progress bar during upload.

    Usage:
        msg = await fast_upload(client, chat_id, "/path/file.mp4", caption="Here!", progress_msg=sent_msg)
    """
    start_time = time.time()
    ext        = os.path.splitext(file_path)[1].lower()
    file_name  = os.path.basename(file_path)

    progress_args = (
        f"📤 <b>Uploading:</b> <code>{file_name}</code>",
        progress_msg,
        start_time
    ) if progress_msg else ()

    progress_fn = progress_for_pyrogram if progress_msg else None

    # ── VIDEO ──
    if ext in VIDEO_EXTENSIONS:
        return await client.send_video(
            chat_id,
            video=file_path,
            caption=caption,
            thumb=thumb,
            supports_streaming=True,          # ⚡ Enables faster streaming upload
            progress=progress_fn,
            progress_args=progress_args
        )

    # ── AUDIO ──
    elif ext in AUDIO_EXTENSIONS:
        return await client.send_audio(
            chat_id,
            audio=file_path,
            caption=caption,
            thumb=thumb,
            progress=progress_fn,
            progress_args=progress_args
        )

    # ── DOCUMENT (any other file) ──
    else:
        return await client.send_document(
            chat_id,
            document=file_path,
            caption=caption,
            thumb=thumb,
            force_document=True,
            progress=progress_fn,
            progress_args=progress_args
        )


# ─────────────────────────────────────────
# 🗑 DELETE FILE SAFELY
# ─────────────────────────────────────────
def safe_delete(path: str):
    """
    Delete a file or directory without raising errors if it doesn't exist.
    """
    try:
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
    except Exception as e:
        print(f"[safe_delete] Could not delete {path}: {e}")


# ─────────────────────────────────────────
# 📦 GET FILE SIZE (human readable)
# ─────────────────────────────────────────
def get_file_size(path: str) -> str:
    """
    Returns the human-readable file size of a local file.
    """
    try:
        size = os.path.getsize(path)
        return humanbytes(size)
    except:
        return "Unknown"


# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @MadflixBotz
# Backup Channel @JishuBotz
# Developer @JishuDeveloper
# Contact @MadflixSupport
