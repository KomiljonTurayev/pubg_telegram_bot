import re
import asyncio
import yt_dlp
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from music_menu import SEARCH_MUSIC
from database import db
from trending import search_deezer
import rate_limiter

logger = logging.getLogger(__name__)
PARSE_MODE = "HTML"
NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
URL_RE = re.compile(r"https?://[^\s]+")

# ── YouTube qidirish (fallback) ────────────────────────────

async def search_youtube(query: str) -> list[dict]:
    opts = {
        "noplaylist": True, "quiet": True, "extract_flat": True,
        "no_warnings": True, "ignoreerrors": True, "geo_bypass": True,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(f"ytsearch5:{query}", download=False)
            ) or {}
            results = []
            for entry in (info.get("entries") or []):
                if not entry or not entry.get("id"):
                    continue
                dur = int(entry.get("duration") or 0)
                results.append({
                    "id":       entry.get("id"),
                    "title":    entry.get("title") or "Noma'lum",
                    "artist":   entry.get("uploader", ""),
                    "duration": f"{dur // 60}:{dur % 60:02d}" if dur else "–",
                    "source":   "youtube",
                })
            return results
    except Exception as e:
        logger.error(f"YouTube search error: {e}")
        return []


async def get_url_info(url: str) -> dict | None:
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "extract_flat": True}
    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            if not info:
                return None
            return {
                "id":        info.get("id"),
                "title":     info.get("title", "Media"),
                "extractor": info.get("extractor_key", "Link"),
            }
    except Exception as e:
        logger.error(f"URL info error: {e}")
        return None


# ── Klaviatura yaratish ─────────────────────────────────────

def build_deezer_keyboard(results: list[dict]) -> InlineKeyboardMarkup:
    """Deezer natijalari uchun inline klaviatura."""
    keyboard = []
    for i, r in enumerate(results):
        title = r["title"]
        artist = r["artist"]
        label = f"{NUMS[i] if i < 5 else f'{i+1}.'} {artist} — {title}"
        if len(label) > 55:
            label = label[:54] + "…"
        label += f"  [{r['duration']}]"
        keyboard.append([
            InlineKeyboardButton(label, callback_data=f"dz_show_{r['deezer_id']}")
        ])
    keyboard.append([InlineKeyboardButton("❌ Yopish", callback_data="close_search")])
    return InlineKeyboardMarkup(keyboard)


def build_youtube_keyboard(results: list[dict]) -> InlineKeyboardMarkup:
    """YouTube natijalari uchun inline klaviatura (fallback)."""
    keyboard = []
    for i, res in enumerate(results):
        title = res["title"]
        if len(title) > 48:
            title = title[:47] + "…"
        num = NUMS[i] if i < len(NUMS) else f"{i+1}."
        keyboard.append([
            InlineKeyboardButton(
                f"{num} {title}  [{res['duration']}]",
                callback_data=f"show_music_options_{res['id']}",
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Yopish", callback_data="close_search")])
    return InlineKeyboardMarkup(keyboard)


# backward-compat alias used in bot.py for shazam results
build_results_keyboard = build_youtube_keyboard


# ── Deezer musiqa tanlash menyusi ──────────────────────────

async def show_deezer_track_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi Deezer natijasini tanlaganda format tanlash menyusini ko'rsatish."""
    query = update.callback_query
    deezer_id = query.data[len("dz_show_"):]
    await query.answer()

    cache = context.user_data.get("dz_cache", {})
    track = cache.get(deezer_id)

    if not track:
        await query.edit_message_text("❌ Ma'lumot topilmadi. Qayta qidiring.", parse_mode=PARSE_MODE)
        return

    title  = track["title"]
    artist = track["artist"]
    album  = track.get("album", "")
    dur    = track.get("duration", "–")
    preview = track.get("preview", "")

    text = (
        f"🎵 <b>{title}</b>\n"
        f"👤 <i>{artist}</i>\n"
        + (f"💿 {album}\n" if album else "")
        + f"⏱ {dur}\n"
        f"<code>─────────────────────</code>\n"
        f"⬇️ <i>Format tanlang:</i>"
    )

    keyboard_rows = [
        [
            InlineKeyboardButton("🎧 Audio MP3", callback_data=f"dz_dl_{deezer_id}"),
            InlineKeyboardButton("🎬 Video MP4", callback_data=f"dz_vq_{deezer_id}"),
        ],
    ]
    if preview:
        keyboard_rows.append([
            InlineKeyboardButton("▶️ 30s Preview", callback_data=f"dz_prev_{deezer_id}")
        ])
    keyboard_rows.append([InlineKeyboardButton("❌ Bekor", callback_data="cancel_dl")])

    cover = track.get("cover", "")
    if cover:
        try:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=cover,
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
                parse_mode=PARSE_MODE,
            )
            return
        except Exception:
            pass

    # Muqova yo'q yoki yuborib bo'lmadi — xabarni o'rnida tahrirlash
    try:
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard_rows),
            parse_mode=PARSE_MODE,
        )
    except Exception:
        await query.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard_rows),
            parse_mode=PARSE_MODE,
        )


async def handle_deezer_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """30 soniyalik Deezer preview ni to'g'ridan-to'g'ri yuborish."""
    query = update.callback_query
    deezer_id = query.data[len("dz_prev_"):]
    await query.answer()

    cache = context.user_data.get("dz_cache", {})
    track = cache.get(deezer_id)
    if not track or not track.get("preview"):
        await query.answer("Preview mavjud emas.", show_alert=True)
        return

    status = await query.message.reply_text("⏳ <i>Preview yuklanmoqda...</i>", parse_mode=PARSE_MODE)
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(track["preview"]) as resp:
                audio_bytes = await resp.read()
        import io
        buf = io.BytesIO(audio_bytes)
        buf.name = "preview.mp3"
        await context.bot.send_audio(
            chat_id=update.effective_chat.id,
            audio=buf,
            title=f"{track['title']} (Preview)",
            performer=track["artist"],
            caption="▶️ <b>30s Preview</b> — Deezer",
            parse_mode=PARSE_MODE,
        )
        await status.delete()
    except Exception as e:
        logger.error(f"Preview error: {e}")
        await status.edit_text("❌ Preview yuborishda xatolik.", parse_mode=PARSE_MODE)


async def handle_deezer_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deezer tanlovidan YouTube orqali yuklab olish."""
    query = update.callback_query
    data = query.data  # dz_dl_ID  yoki  dz_vq_ID
    await query.answer()

    is_video = data.startswith("dz_vq_")
    deezer_id = data[len("dz_dl_"):] if not is_video else data[len("dz_vq_"):]

    cache = context.user_data.get("dz_cache", {})
    track = cache.get(deezer_id)
    if not track:
        await query.message.reply_text("❌ Ma'lumot topilmadi. Qayta qidiring.")
        return

    user_id = update.effective_user.id
    allowed, wait = rate_limiter.check_download(user_id)
    if not allowed:
        await query.message.reply_text(
            f"⚠️ <b>Juda ko'p yuklab olish!</b>\n"
            f"<i>{wait} soniyadan so'ng qayta urinib ko'ring.</i>",
            parse_mode=PARSE_MODE,
        )
        return

    yt_query = f"{track['artist']} - {track['title']}"
    status = await query.message.reply_text(
        f"🔍 <i>YouTube'dan qidirilmoqda: {yt_query[:50]}...</i>",
        parse_mode=PARSE_MODE,
    )

    yt_results = await search_youtube(yt_query)
    if not yt_results:
        await status.edit_text("❌ YouTube'dan topilmadi. URL orqali urinib ko'ring.", parse_mode=PARSE_MODE)
        return

    video_id = yt_results[0]["id"]
    await status.delete()

    import music_downloader
    if is_video:
        # Video sifat menyusini to'g'ridan-to'g'ri ko'rsatish
        short_title = f"{track['artist']} — {track['title']}"
        if len(short_title) > 50:
            short_title = short_title[:49] + "…"
        keyboard = [
            [
                InlineKeyboardButton("📱 360p", callback_data=f"vdl_360_{video_id}"),
                InlineKeyboardButton("💻 480p", callback_data=f"vdl_480_{video_id}"),
            ],
            [
                InlineKeyboardButton("🖥️ 720p HD",  callback_data=f"vdl_720_{video_id}"),
                InlineKeyboardButton("✨ 1080p FHD", callback_data=f"vdl_1080_{video_id}"),
            ],
            [InlineKeyboardButton("❌ Bekor", callback_data="cancel_dl")],
        ]
        await query.message.reply_text(
            f"🎬 <b>{short_title}</b>\n"
            f"<code>─────────────────────</code>\n"
            f"📊 <i>Video sifatini tanlang:</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=PARSE_MODE,
        )
    else:
        await music_downloader.handle_media_download(
            update, context, video_id=video_id, is_video=False
        )


# ── Asosiy qidiruv handler ─────────────────────────────────

async def search_music(query: str) -> list:
    """Backward compat: YouTube qidiruvi (shazam_dl_callback uchun)."""
    return await search_youtube(query)


async def process_music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()

    if query_text.lower() in ("❌ bekor", "bekor", "/cancel"):
        await update.message.reply_text("🏠 Asosiy menyuga qaytildi.")
        return ConversationHandler.END

    # URL tekshirish
    if URL_RE.search(query_text):
        status_msg = await update.message.reply_text(
            "🔍 <i>Havola tekshirilmoqda...</i>", parse_mode=PARSE_MODE
        )
        info = await get_url_info(query_text)
        if not info:
            await status_msg.edit_text(
                "❌ <b>Havoladan ma'lumot olib bo'lmadi.</b>\n"
                "<i>Boshqa havola yoki qo'shiq nomini yozib ko'ring:</i>",
                parse_mode=PARSE_MODE,
            )
            return SEARCH_MUSIC

        vid = info["id"] if info.get("id") else "external"
        context.user_data["last_url"] = query_text
        short_title = (info["title"][:55] + "…") if len(info["title"]) > 55 else info["title"]

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎧 Audio MP3", callback_data=f"dl_{vid}"),
                InlineKeyboardButton("🎬 Video MP4", callback_data=f"vq_{vid}"),
            ],
            [InlineKeyboardButton("❌ Bekor", callback_data="cancel_dl")],
        ])
        await status_msg.edit_text(
            f"🌐 <b>{info['extractor']}</b>\n"
            f"🎵 {short_title}\n"
            f"<code>─────────────────────</code>\n"
            f"⬇️ <i>Format tanlang:</i>",
            reply_markup=keyboard,
            parse_mode=PARSE_MODE,
        )
        return SEARCH_MUSIC

    # Rate limit tekshirish
    user_id = update.effective_user.id
    allowed, wait = rate_limiter.check_search(user_id)
    if not allowed:
        await update.message.reply_text(
            f"⚠️ <b>Juda ko'p qidiruv!</b>\n"
            f"<i>{wait} soniyadan so'ng qayta urinib ko'ring.</i>",
            parse_mode=PARSE_MODE,
        )
        return SEARCH_MUSIC

    status_msg = await update.message.reply_text(
        f"🔍 <b>Qidirilmoqda:</b> <i>{query_text[:40]}</i>\n<code>░░░░░░░░░░</code>",
        parse_mode=PARSE_MODE,
    )
    await update.get_bot().send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        await db.save_search_history(user_id, query_text)
    except Exception:
        pass

    # Deezer + YouTube parallel qidiruv
    deezer_task = asyncio.create_task(search_deezer(query_text))
    yt_task     = asyncio.create_task(search_youtube(query_text))
    deezer_results, yt_results = await asyncio.gather(deezer_task, yt_task)

    if deezer_results:
        # Deezer natijalarini user_data ga saqlash
        dz_cache = {r["deezer_id"]: r for r in deezer_results}
        context.user_data["dz_cache"] = dz_cache

        reply_markup = build_deezer_keyboard(deezer_results)
        await status_msg.edit_text(
            f"🎵 <b>Qidiruv natijalari:</b>\n"
            f"«{query_text[:40]}»\n"
            f"<code>─────────────────────</code>\n"
            f"👇 <i>Tanlang yoki yangi nom yozing:</i>",
            reply_markup=reply_markup,
            parse_mode=PARSE_MODE,
        )
    elif yt_results:
        # Deezer topilmasa YouTube ga fallback
        reply_markup = build_youtube_keyboard(yt_results)
        await status_msg.edit_text(
            f"🔍 <b>YouTube natijalari:</b>\n"
            f"«{query_text[:40]}»\n"
            f"<code>─────────────────────</code>\n"
            f"👇 <i>Tanlang:</i>",
            reply_markup=reply_markup,
            parse_mode=PARSE_MODE,
        )
    else:
        await status_msg.edit_text(
            "😔 <b>Hech narsa topilmadi.</b>\n"
            "<i>Boshqa nom yoki ijrochi nomini yozib ko'ring:</i>",
            parse_mode=PARSE_MODE,
        )

    return SEARCH_MUSIC
