import os
import gc
import asyncio
import yt_dlp
import re
import time
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database import db
from config import Config

logger = logging.getLogger(__name__)

download_semaphore = asyncio.Semaphore(2)
PARSE_MODE = "HTML"

URL_REGEX = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

TIKTOK_RE = re.compile(r"tiktok\.com|vm\.tiktok\.com", re.I)
INSTAGRAM_RE = re.compile(r"instagram\.com|instagr\.am", re.I)

VIDEO_QUALITIES = {
    "360": ("📱 360p  — Kichik", "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]"),
    "480": ("💻 480p  — O'rta",  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]"),
    "720": ("🖥️ 720p  — HD",     "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]"),
    "1080": ("✨ 1080p — Full HD", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]"),
}


def is_url(text: str) -> bool:
    return re.search(URL_REGEX, text) is not None


def _detect_platform(url: str) -> str:
    if TIKTOK_RE.search(url):
        return "tiktok"
    if INSTAGRAM_RE.search(url):
        return "instagram"
    return "other"


def _base_ydl_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if Config.FFMPEG_PATH and Config.FFMPEG_PATH != "ffmpeg":
        opts["ffmpeg_location"] = Config.FFMPEG_PATH
    return opts


async def get_link_info(url: str) -> dict | None:
    opts = {**_base_ydl_opts(), "extract_flat": True}
    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            return {
                "title":    info.get("title", "Media"),
                "extractor": info.get("extractor_key", "Link"),
                "webpage_url": info.get("webpage_url", url),
                "id":       info.get("id"),
            }
    except Exception as e:
        logger.error(f"Link info error: {e}")
        return None


# ──────────────────────────────────────────────────────────
#  FORMAT TANLASH MENYUSI  (qidiruv natijasidan so'ng)
# ──────────────────────────────────────────────────────────
async def show_music_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    video_id = query.data[len("show_music_options_"):]
    await query.answer()

    info = await get_link_info(f"https://www.youtube.com/watch?v={video_id}")
    title = info["title"] if info else "Noma'lum sarlavha"
    short_title = title[:50] + "…" if len(title) > 50 else title

    keyboard = [
        [
            InlineKeyboardButton("🎧 Audio  MP3", callback_data=f"dl_{video_id}"),
            InlineKeyboardButton("🎬 Video  MP4", callback_data=f"vq_{video_id}"),
        ],
        [InlineKeyboardButton("❌  Bekor qilish", callback_data="cancel_dl")],
    ]
    await query.message.reply_text(
        f"🎵 <b>{short_title}</b>\n"
        f"<code>─────────────────────</code>\n"
        f"⬇️  <i>Format tanlang:</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=PARSE_MODE,
    )


# ──────────────────────────────────────────────────────────
#  VIDEO SIFAT TANLASH MENYUSI
# ──────────────────────────────────────────────────────────
async def show_video_quality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    video_id = query.data[len("vq_"):]
    await query.answer()

    info = await get_link_info(f"https://www.youtube.com/watch?v={video_id}")
    title = info["title"] if info else "Noma'lum sarlavha"
    short_title = title[:50] + "…" if len(title) > 50 else title

    keyboard = [
        [
            InlineKeyboardButton("📱 360p", callback_data=f"vdl_360_{video_id}"),
            InlineKeyboardButton("💻 480p", callback_data=f"vdl_480_{video_id}"),
        ],
        [
            InlineKeyboardButton("🖥️ 720p  HD", callback_data=f"vdl_720_{video_id}"),
            InlineKeyboardButton("✨ 1080p  FHD", callback_data=f"vdl_1080_{video_id}"),
        ],
        [
            InlineKeyboardButton("⬅️  Ortga", callback_data=f"show_music_options_{video_id}"),
            InlineKeyboardButton("❌  Bekor", callback_data="cancel_dl"),
        ],
    ]
    await query.message.reply_text(
        f"🎬 <b>{short_title}</b>\n"
        f"<code>─────────────────────</code>\n"
        f"📊  <i>Video sifatini tanlang:</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=PARSE_MODE,
    )


# ──────────────────────────────────────────────────────────
#  UNIVERSAL YUKLAB OLISH
# ──────────────────────────────────────────────────────────
async def handle_media_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    video_id: str = None,
    is_video: bool = False,
    quality: str = None,
):
    if update.callback_query:
        query = update.callback_query
        data = query.data
        await query.answer()
        message = query.message

        if data.startswith("dl_"):
            is_video = False
            video_id = data[3:]
            quality = None
        elif data.startswith("vdl_"):
            is_video = True
            # vdl_720_VIDEO_ID  →  quality=720, video_id=VIDEO_ID
            rest = data[4:]                        # "720_VIDEO_ID"
            quality, video_id = rest.split("_", 1)
        else:
            return
    else:
        message = update.message

    if not video_id:
        return

    # URL yasash
    if video_id == "external":
        video_url = context.user_data.get("last_url")
    else:
        video_url = f"https://www.youtube.com/watch?v={video_id}"

    if not video_url:
        await message.reply_text("❌ Yuklab olish uchun havola topilmadi.")
        return

    # Kesh tekshirish (faqat audio + YouTube ID)
    if not is_video and video_id != "external":
        cached = await db.get_cached_music(video_id)
        if cached:
            try:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=cached[0],
                    title=cached[1],
                    performer=cached[2],
                    caption=(
                        f"🎵 <b>{cached[1]}</b>\n"
                        f"👤 {cached[2]}\n"
                        f"<code>─────────────────────</code>\n"
                        f"⚡️ <i>Keshdan yuborildi</i>"
                    ),
                    parse_mode=PARSE_MODE,
                )
                await db.increment_music_count(video_id)
                return
            except Exception as e:
                logger.warning(f"Cache send error: {e}")

    # Status xabari
    media_type = "🎬 Video" if is_video else "🎵 Audio"
    qual_text = f"  •  {quality}p" if (is_video and quality) else ""
    status_msg = await message.reply_text(
        f"⏳ <b>{media_type}{qual_text} yuklanmoqda...</b>\n"
        f"<code>░░░░░░░░░░</code>  0%",
        parse_mode=PARSE_MODE,
    )

    loop = asyncio.get_running_loop()
    last_edit_time = 0

    def progress_hook(d):
        nonlocal last_edit_time
        if d["status"] != "downloading":
            return
        now = time.time()
        if now - last_edit_time < 2.5:
            return
        last_edit_time = now

        raw_percent = d.get("_percent_str", "0%").strip()
        clean = re.sub(r"\x1b\[[0-9;]*m", "", raw_percent)
        try:
            p = float(clean.replace("%", ""))
            filled = int(p // 10)
            bar = "▓" * filled + "░" * (10 - filled)
            speed = d.get("_speed_str", "").strip()
            speed = re.sub(r"\x1b\[[0-9;]*m", "", speed)
            eta = d.get("_eta_str", "").strip()
            text = (
                f"⏳ <b>{media_type}{qual_text} yuklanmoqda...</b>\n"
                f"<code>{bar}</code>  {clean}\n"
                f"🚀 {speed}   ⏱ ETA: {eta}"
            )
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(text, parse_mode=PARSE_MODE), loop
            )
        except Exception:
            pass

    async with download_semaphore:
        folder = "/tmp/botdl"
        os.makedirs(folder, exist_ok=True)
        ts = int(time.time())
        out_stem = f"{folder}/dl_{ts}"
        outtmpl = out_stem + ".%(ext)s"

        ydl_opts = {
            **_base_ydl_opts(),
            "outtmpl": outtmpl,
            "progress_hooks": [progress_hook],
        }

        if is_video:
            if quality == "social":
                platform = context.user_data.get("last_platform", "other")
                if platform == "tiktok":
                    # H.265 oqimi TikTok da odatda suv belgisiz bo'ladi
                    ydl_opts["format"] = (
                        "bestvideo[vcodec^=h265]+bestaudio"
                        "/bestvideo[vcodec^=hevc]+bestaudio"
                        "/bestvideo+bestaudio/best"
                    )
                else:
                    ydl_opts["format"] = "bestvideo+bestaudio/best"
            else:
                fmt = VIDEO_QUALITIES.get(str(quality), VIDEO_QUALITIES["720"])[1] if quality else VIDEO_QUALITIES["720"][1]
                ydl_opts["format"] = fmt
            ydl_opts["merge_output_format"] = "mp4"
        else:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        file_path = None
        files_before = set(os.listdir(folder))
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(
                    None, lambda: ydl.extract_info(video_url, download=True)
                )
                title = info.get("title", "Media")
                uploader = info.get("uploader", "Artist")

                if is_video:
                    file_path = out_stem + ".mp4"
                    if not os.path.exists(file_path):
                        files_after = set(os.listdir(folder))
                        new_files = files_after - files_before
                        mp4_files = [f for f in new_files if f.endswith(".mp4")]
                        if mp4_files:
                            file_path = os.path.join(folder, mp4_files[0])
                        else:
                            raise FileNotFoundError(f"Merged MP4 not found. New files: {new_files}")

                    qual_label = VIDEO_QUALITIES.get(str(quality), ("", ""))[0] if quality else "720p"
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    caption = (
                        f"🎬 <b>{title}</b>\n"
                        f"<code>─────────────────────</code>\n"
                        f"📊 Sifat: {qual_label}  •  {file_size_mb:.1f} MB"
                    )
                    with open(file_path, "rb") as f:
                        await context.bot.send_video(
                            chat_id=update.effective_chat.id,
                            video=f,
                            caption=caption,
                            parse_mode=PARSE_MODE,
                            supports_streaming=True,
                            read_timeout=120,
                            write_timeout=120,
                            connect_timeout=30,
                        )
                else:
                    file_path = out_stem + ".mp3"
                    if not os.path.exists(file_path):
                        files_after = set(os.listdir(folder))
                        new_files = files_after - files_before
                        mp3_files = [f for f in new_files if f.endswith(".mp3")]
                        if mp3_files:
                            file_path = os.path.join(folder, mp3_files[0])
                        else:
                            raise FileNotFoundError(f"MP3 not found. New files: {new_files}")

                    caption = (
                        f"🎵 <b>{title}</b>\n"
                        f"👤 <i>{uploader}</i>\n"
                        f"<code>─────────────────────</code>\n"
                        f"🎧 MP3 • 192 kbps"
                    )
                    with open(file_path, "rb") as f:
                        sent = await context.bot.send_audio(
                            chat_id=update.effective_chat.id,
                            audio=f,
                            title=title,
                            performer=uploader,
                            caption=caption,
                            parse_mode=PARSE_MODE,
                            read_timeout=120,
                            write_timeout=120,
                        )
                    if video_id != "external":
                        await db.cache_music(video_id, sent.audio.file_id, title, uploader)
                        await db.increment_music_count(video_id)

            await status_msg.delete()

        except Exception as e:
            logger.error(f"Download error: {e}")
            await status_msg.edit_text(
                "❌ <b>Yuklashda xatolik yuz berdi.</b>\n"
                "<i>Fayl o'chirilgan, juda katta yoki internet muammosi bo'lishi mumkin.</i>",
                parse_mode=PARSE_MODE,
            )
        finally:
            # Shu download sessiyasida yaratilgan BARCHA fayllarni o'chirish
            for f in os.listdir(folder):
                if f.startswith(f"dl_{ts}"):
                    try:
                        os.remove(os.path.join(folder, f))
                    except OSError:
                        pass
            # Python garbage collector ni qo'lda ishga tushirish
            gc.collect()


# ──────────────────────────────────────────────────────────
#  TASHQI HAVOLA (URL yuborilganda)
# ──────────────────────────────────────────────────────────
async def handle_incoming_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not is_url(url):
        return

    platform = _detect_platform(url)
    context.user_data["last_platform"] = platform

    status_msg = await update.message.reply_text(
        "🔍 <i>Havola tekshirilmoqda...</i>", parse_mode=PARSE_MODE
    )
    info = await get_link_info(url)

    if not info:
        await status_msg.edit_text(
            "❌ <b>Ma'lumot olib bo'lmadi.</b>\n"
            "<i>Havola noto'g'ri yoki mavjud emas.</i>",
            parse_mode=PARSE_MODE,
        )
        return

    context.user_data["last_url"] = url
    vid = info["id"] if info.get("extractor") == "Youtube" else "external"
    short_title = info["title"][:60] + "…" if len(info["title"]) > 60 else info["title"]

    if platform == "tiktok":
        platform_label = "📱 TikTok"
        video_label = "🎬 Video (suv belgisiz)"
        video_cb = "vdl_social_external"
    elif platform == "instagram":
        platform_label = "📸 Instagram"
        video_label = "🎬 Video / Rasm"
        video_cb = "vdl_social_external"
    else:
        platform_label = f"🌐 {info['extractor']}"
        video_label = "🎬 Video  MP4"
        video_cb = f"vq_{vid}"

    keyboard = [
        [
            InlineKeyboardButton("🎧 Audio  MP3", callback_data=f"dl_{vid}"),
            InlineKeyboardButton(video_label, callback_data=video_cb),
        ],
        [InlineKeyboardButton("❌  Bekor qilish", callback_data="cancel_dl")],
    ]
    await status_msg.edit_text(
        f"{platform_label}  •  {short_title}\n"
        f"<code>─────────────────────</code>\n"
        f"⬇️  <i>Format tanlang:</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=PARSE_MODE,
    )


# ──────────────────────────────────────────────────────────
#  BEKOR QILISH
# ──────────────────────────────────────────────────────────
async def cancel_dl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Bekor qilindi.")
    await update.callback_query.message.delete()
