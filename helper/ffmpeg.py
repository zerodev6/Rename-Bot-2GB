import time
import os
import asyncio
import re
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#                    FIX THUMBNAIL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def fix_thumb(thumb):
    width = 320
    height = 320
    try:
        if thumb is not None and os.path.exists(thumb):
            parser = createParser(thumb)
            if parser:
                metadata = extractMetadata(parser)
                if metadata:
                    if metadata.has("width"):
                        width = metadata.get("width")
                    if metadata.has("height"):
                        height = metadata.get("height")
                parser.close()

            with Image.open(thumb) as img:
                img = img.convert("RGB")
                img = img.resize((width, height))
                img.save(thumb, "JPEG")
    except Exception as e:
        print(f"[fix_thumb Error] {e}")
        thumb = None

    return width, height, thumb


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#                   TAKE SCREENSHOT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def take_screen_shot(video_file, output_directory, ttl):
    out_put_file_name = os.path.join(output_directory, f"{time.time()}.jpg")
    command = [
        "ffmpeg", "-y",
        "-ss", str(ttl),
        "-i", video_file,
        "-vframes", "1",
        "-q:v", "2",
        out_put_file_name
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()
    if os.path.exists(out_put_file_name):
        return out_put_file_name
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#              DETECT SOURCE TAG
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def detect_source_tag(filename: str) -> str | None:
    name = filename.upper()
    if re.search(r"WEB[-\.]?DL", name):
        return None
    patterns = [
        r"BLU[-\s]?RAY", r"BLURAY", r"BDRIP", r"BDR",
        r"WEBRIP", r"WEB[-\s]?RIP",
        r"HDTV", r"PDTV",
        r"DVDRIP", r"DVDSCR", r"DVD",
        r"HDRIP", r"HDCAM", r"CAM",
        r"TS\b", r"TELESYNC",
        r"REMUX",
    ]
    for pat in patterns:
        m = re.search(pat, name)
        if m:
            return m.group(0)
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#         PROBE VIDEO — FULL STREAM INFO
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def probe_video(input_path: str) -> dict:
    """
    Probes video, audio, and subtitle streams.
    Returns a unified dict with all relevant info.
    """

    # ── Video stream ──────────────────────────────
    cmd_v = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,codec_name,color_transfer,color_primaries,pix_fmt,r_frame_rate",
        "-of", "default=noprint_wrappers=1",
        input_path,
    ]
    proc_v = await asyncio.create_subprocess_exec(
        *cmd_v,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_v, _ = await proc_v.communicate()

    info = {}
    for line in stdout_v.decode().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()

    # ── Audio streams (all of them) ───────────────
    cmd_a = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries",
        "stream=index,codec_name,channels,channel_layout,sample_rate,bit_rate",
        "-of", "default=noprint_wrappers=1",
        input_path,
    ]
    proc_a = await asyncio.create_subprocess_exec(
        *cmd_a,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_a, _ = await proc_a.communicate()

    audio_streams = []
    current = {}
    for line in stdout_a.decode().splitlines():
        if line.startswith("index=") and current:
            audio_streams.append(current)
            current = {}
        if "=" in line:
            k, v = line.split("=", 1)
            current[k.strip()] = v.strip()
    if current:
        audio_streams.append(current)

    info["audio_streams"] = audio_streams

    # Primary audio (first stream) for quick checks
    if audio_streams:
        info["audio_codec_name"]    = audio_streams[0].get("codec_name", "")
        info["audio_channels"]      = audio_streams[0].get("channels", "2")
        info["audio_channel_layout"]= audio_streams[0].get("channel_layout", "stereo")
    else:
        info["audio_codec_name"]     = ""
        info["audio_channels"]       = "2"
        info["audio_channel_layout"] = "stereo"

    # ── Subtitle streams (codec + language tag) ───
    cmd_s = [
        "ffprobe", "-v", "error",
        "-select_streams", "s",
        "-show_entries",
        "stream=index,codec_name:stream_tags=language,title",
        "-of", "default=noprint_wrappers=1",
        input_path,
    ]
    proc_s = await asyncio.create_subprocess_exec(
        *cmd_s,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_s, _ = await proc_s.communicate()

    sub_streams = []
    cur_s = {}
    for line in stdout_s.decode().splitlines():
        if line.startswith("index=") and cur_s:
            sub_streams.append(cur_s)
            cur_s = {}
        if "=" in line:
            k, v = line.split("=", 1)
            cur_s[k.strip()] = v.strip()
    if cur_s:
        sub_streams.append(cur_s)

    info["sub_streams"] = sub_streams

    return info


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#       RESOLUTION LABEL HELPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def resolution_label(width: int, height: int) -> str:
    """Returns human-readable label: 4K / 1080p / 720p / SD"""
    if width >= 3840 or height >= 2160:
        return "4K"
    elif height >= 1080 or width >= 1920:
        return "1080p"
    elif height >= 720 or width >= 1280:
        return "720p"
    else:
        return "SD"


def target_scale(res_label: str) -> str | None:
    """
    Returns ffmpeg scale filter string for downscale target.
    1080p  → 720p
    4K     → 1080p  (reasonable WEB-DL cap)
    720p   → no downscale (already target res)
    SD     → no downscale
    """
    if res_label == "1080p":
        return "scale=1280:720:flags=lanczos"
    elif res_label == "4K":
        return "scale=1920:1080:flags=lanczos"
    return None                   # 720p / SD → keep as-is


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#         REAL WEB-DL RE-ENCODE CONVERSION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def convert_to_webdl(input_path: str, output_dir: str, ms) -> str | None:
    """
    Full re-encode to proper WEB-DL spec:

    VIDEO
    ─────
    • SDR 1080p  → H.264 High@4.1, CRF 18, downscaled to 720p WEB-DL
    • SDR 720p   → H.264 High@4.1, CRF 18, kept at 720p
    • HDR / 4K   → HEVC 10-bit, CRF 20, downscaled to 1080p WEB-DL
    • Scale filter: lanczos (sharpest downscale)

    AUDIO
    ─────
    • Always re-encoded to EAC-3 (Dolby Digital Plus) 5.1 @ 640 kbps
    • Source with ≥6 channels  → 5.1 layout preserved
    • Source with <6 channels  → upmixed to 5.1 via pan filter
    • Label shown to user : DDP5.1

    SUBTITLES
    ─────────
    • Every subtitle stream is copied byte-for-byte
    • Original codec (ASS/SSA/SRT/PGS/DVDSUB etc.) preserved
    • Language & title tags re-applied from source
    • Default/forced disposition flags preserved

    CONTAINER : MKV
    """

    # ── Rename source tag in filename ──────────────
    base = os.path.splitext(os.path.basename(input_path))[0]
    new_base = re.sub(
        r"(BLU[-\s]?RAY|BLURAY|BDRIP|BDR|WEBRIP|WEB[-\s]?RIP|HDTV|PDTV"
        r"|DVDRIP|DVDSCR|DVD|HDRIP|HDCAM|CAM|TS(?=[\s.\-_])|TELESYNC|REMUX)",
        "WEB-DL",
        base,
        flags=re.IGNORECASE,
        count=1,
    )
    if new_base == base:
        new_base = base + ".WEB-DL"

    output_path = os.path.join(output_dir, new_base + ".mkv")

    # ── Probe ──────────────────────────────────────
    await ms.edit("🔍 <i>Probing source streams…</i>")
    info = await probe_video(input_path)

    width           = int(info.get("width",  1920) or 1920)
    height          = int(info.get("height", 1080) or 1080)
    color_transfer  = info.get("color_transfer",  "").lower()
    color_primaries = info.get("color_primaries", "").lower()
    pix_fmt         = info.get("pix_fmt", "yuv420p").lower()
    audio_streams   = info.get("audio_streams", [])
    sub_streams     = info.get("sub_streams",   [])

    is_hdr = (
        "smpte2084"    in color_transfer
        or "arib-std-b67" in color_transfer
        or "bt2020"    in color_primaries
        or "10le"      in pix_fmt
        or "10be"      in pix_fmt
    )

    res = resolution_label(width, height)
    scale_filter = target_scale(res)     # None = no downscale needed

    # ── Output resolution label for status msg ─────
    if scale_filter:
        out_res = "1080p" if res == "4K" else "720p"
    else:
        out_res = res

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # VIDEO CODEC ARGS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if is_hdr:
        vcodec_args = [
            "-c:v", "libx265",
            "-crf", "20",
            "-preset", "slow",
            "-pix_fmt", "yuv420p10le",
            "-x265-params",
            "hdr-opt=1:repeat-headers=1"
            ":colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
        ]
        video_label = f"HEVC 10-bit HDR → {out_res} WEB-DL (CRF 20)"
    else:
        vcodec_args = [
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "slow",
            "-profile:v", "high",
            "-level", "4.1",
            "-pix_fmt", "yuv420p",
        ]
        video_label = f"H.264 High → {out_res} WEB-DL (CRF 18)"

    # Inject scale filter if needed
    if scale_filter:
        vf_args = ["-vf", scale_filter]
    else:
        vf_args = []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # AUDIO — always EAC-3 DDP 5.1 @ 640k
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Build one EAC-3 5.1 output stream from the first audio source.
    # If source is already 6+ ch → standard 5.1 layout.
    # If source is stereo/mono   → upmix with pan filter to fill 5.1.

    src_channels = int((audio_streams[0].get("channels") if audio_streams else None) or 2)

    if src_channels >= 6:
        # Proper surround source → re-encode to DDP5.1 directly
        acodec_args = [
            "-c:a", "eac3",
            "-b:a", "640k",
            "-ac", "6",
            "-channel_layout", "5.1",
        ]
        upmix_filter = None
    else:
        # Stereo/mono source → upmix via pan to synthetic 5.1
        # FL=FR=FC=LFE from mix; BL/BR duplicated from L/R
        upmix_filter = (
            "pan=5.1|"
            "FL=FL|FR=FR|"
            "FC=0.5*FL+0.5*FR|"
            "LFE=0.3*FL+0.3*FR|"
            "BL=FL|BR=FR"
        )
        acodec_args = [
            "-c:a", "eac3",
            "-b:a", "640k",
            "-ac", "6",
        ]

    audio_label = "DDP5.1 (EAC-3 640k)"

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SUBTITLE CODEC INFO (for status display)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if sub_streams:
        sub_codecs = list(dict.fromkeys(
            s.get("codec_name", "copy") for s in sub_streams
        ))
        sub_label = f"{len(sub_streams)} stream(s) [{', '.join(sub_codecs)}] — copied"
    else:
        sub_label = "none"

    # ── Status message ─────────────────────────────
    await ms.edit(
        f"⚙️ <i>Re-encoding to WEB-DL…\n\n"
        f"📐 Source    : <b>{width}×{height} ({res})</b>\n"
        f"🎯 Output    : <b>{out_res} WEB-DL</b>\n"
        f"🎬 Video     : <b>{video_label}</b>\n"
        f"🔊 Audio     : <b>{audio_label}</b>\n"
        f"📝 Subtitles : <b>{sub_label}</b>\n\n"
        f"⏳ <i>This may take a while…</i></i>"
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BUILD FFMPEG COMMAND
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    command = [
        "ffmpeg", "-y",
        "-i", input_path,
    ]

    # Stream maps
    command += ["-map", "0:v:0"]           # first video only
    command += ["-map", "0:a:0"]           # first audio only → DDP5.1
    for i in range(len(sub_streams)):
        command += ["-map", f"0:s:{i}"]    # every subtitle stream

    # Video encode + optional scale
    command += vf_args
    command += vcodec_args

    # Audio encode (with optional upmix filter)
    if upmix_filter:
        command += ["-filter:a", upmix_filter]
    command += acodec_args

    # Subtitles — copy every stream in its original codec
    command += ["-c:s", "copy"]

    # Re-apply subtitle metadata (language + title) and disposition
    for idx, s in enumerate(sub_streams):
        lang  = s.get("TAG:language") or s.get("language") or ""
        title = s.get("TAG:title")    or s.get("title")    or ""
        if lang:
            command += [f"-metadata:s:s:{idx}", f"language={lang}"]
        if title:
            command += [f"-metadata:s:s:{idx}", f"title={title}"]

    # Strip old container metadata; stamp WEB-DL
    command += [
        "-map_metadata", "-1",
        "-metadata", "source=WEB-DL",
        output_path,
    ]

    # ── Run ────────────────────────────────────────
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        err = stderr.decode().strip()
        print(f"[convert_to_webdl FFmpeg Error]\n{err}")
        await ms.edit("❌ <i>WEB-DL re-encode failed. Check logs.</i>")
        return None

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path

    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#                    ADD METADATA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def add_metadata(input_path, output_path, metadata, ms):
    try:
        if not input_path or not os.path.exists(input_path):
            await ms.edit("❌ <i>Input file not found. Cannot add metadata.</i>")
            return None

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # ── WEB-DL check & real re-encode ─────────────────────────
        filename   = os.path.basename(input_path)
        source_tag = detect_source_tag(filename)

        if source_tag:
            await ms.edit(
                f"🎯 <i>Source detected: <b>{source_tag}</b>\n"
                f"Starting full WEB-DL re-encode…</i>"
            )
            converted = await convert_to_webdl(
                input_path,
                os.path.dirname(os.path.abspath(output_path)),
                ms,
            )
            if converted:
                await ms.edit("✅ <i>Re-encode complete! Adding metadata…</i>")
                input_path = converted
            else:
                await ms.edit("⚠️ <i>Re-encode failed — using original file.</i>")
        # ── end WEB-DL block ──────────────────────────────────────

        await ms.edit("📝 <i>Adding Metadata To Your File ⚡</i>")

        safe_metadata = (
            str(metadata)
            .replace("'", "")
            .replace('"', "")
            .replace("\\", "")
            .strip()
        )

        command = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-map", "0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-c:s", "copy",

            "-map_metadata", "-1",

            "-metadata", f"title={safe_metadata}",
            "-metadata", f"author={safe_metadata}",
            "-metadata", f"artist={safe_metadata}",
            "-metadata", f"comment={safe_metadata}",
            "-metadata", f"encoder={safe_metadata}",

            "-metadata:s:0", f"title={safe_metadata}",
            "-metadata:s:1", f"title={safe_metadata}",

            "-metadata:s:2", f"title=English {safe_metadata}",
            "-metadata:s:2", "language=eng",
            "-disposition:s:2", "default",

            "-metadata:s:3", f"title=Sinhala {safe_metadata}",
            "-metadata:s:3", "language=sin",
            "-disposition:s:3", "0",

            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error = stderr.decode().strip()
            print(f"[add_metadata FFmpeg Error]\n{error}")
            await ms.edit("❌ <i>FFmpeg Failed To Add Metadata.</i>")
            return None

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            await ms.edit("✅ <i>Metadata Added Successfully!</i>")
            return output_path
        else:
            await ms.edit("❌ <i>Metadata output file is missing or empty.</i>")
            return None

    except Exception as e:
        print(f"[add_metadata Exception] {e}")
        await ms.edit(f"❌ <i>Error While Adding Metadata: {e}</i>")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#               FAST PROGRESS BAR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def fast_progress(current, total, message, start_time, action="Processing"):
    try:
        now     = time.time()
        elapsed = now - start_time
        speed   = current / elapsed if elapsed > 0 else 0
        eta     = (total - current) / speed if speed > 0 else 0
        percent = current * 100 / total
        done    = int(percent / 5)
        bar     = "█" * done + "░" * (20 - done)

        text = (
            f"**{action}**\n"
            f"`{bar}` **{percent:.1f}%**\n\n"
            f"📦 **Size:** `{humanbytes(current)}` / `{humanbytes(total)}`\n"
            f"⚡ **Speed:** `{humanbytes(speed)}/s`\n"
            f"⏳ **ETA:** `{time_formatter(eta)}`"
        )
        await message.edit(text)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#                  HELPER FUNCTIONS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def humanbytes(size):
    if not size:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"


def time_formatter(seconds):
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes   = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Jishu Developer
# Don't Remove Credit 🥺
# Telegram Channel @MadflixBotz
# Backup Channel @JishuBotz
# Developer @JishuDeveloper
# Contact @MadflixSupport
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
