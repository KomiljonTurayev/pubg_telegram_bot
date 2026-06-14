import asyncio
import aiohttp
import logging
import yt_dlp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from config import Config

logger = logging.getLogger(__name__)
PARSE_MODE = "HTML"
OMDB = "http://www.omdbapi.com/"


async def _omdb(params: dict) -> dict:
    if not Config.OMDB_API_KEY:
        return {}
    params["apikey"] = Config.OMDB_API_KEY
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(OMDB, params=params) as r:
                if r.status == 200:
                    return await r.json()
    except Exception as e:
        logger.error(f"OMDB error: {e}")
    return {}


async def handle_movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = " ".join(context.args) if context.args else ""

    if not query_text:
        await update.message.reply_text(
            "🎬 <b>Film qidirish</b>\n\n"
            "Ishlatish: <code>/movies Film nomi</code>\n"
            "Misol: <code>/movies Inception</code>",
            parse_mode=PARSE_MODE,
        )
        return

    if not Config.OMDB_API_KEY:
        await update.message.reply_text(
            "⚠️ <b>Film xizmati hozircha faol emas.</b>\n"
            "<i>Admin OMDB_API_KEY ni sozlashi kerak.</i>",
            parse_mode=PARSE_MODE,
        )
        return

    status = await update.message.reply_text("🔍 <i>Film qidirilmoqda...</i>", parse_mode=PARSE_MODE)
    data = await _omdb({"s": query_text, "type": "movie"})

    if not data or data.get("Response") == "False":
        await status.edit_text(
            f"😔 <b>«{query_text}» topilmadi.</b>\n"
            "<i>Inglizcha nom bilan ham urinib ko'ring.</i>",
            parse_mode=PARSE_MODE,
        )
        return

    movies = data.get("Search", [])[:5]
    text = f"🎬 <b>Film natijalari: «{query_text}»</b>\n<code>──────────────────────</code>\n"
    keyboard = []

    for m in movies:
        text += f"🎞 <b>{m['Title']}</b> ({m['Year']})\n"
        label = f"🎞 {m['Title'][:32]} ({m['Year']})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"movie_{m['imdbID']}")])

    keyboard.append([InlineKeyboardButton("❌ Yopish", callback_data="close_search")])
    await status.edit_text(
        text + "\n👇 <i>Batafsil ma'lumot uchun tanlang:</i>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=PARSE_MODE,
    )


async def handle_movie_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    imdb_id = query.data[len("movie_"):]

    movie = await _omdb({"i": imdb_id, "plot": "short"})
    if not movie or movie.get("Response") == "False":
        await query.edit_message_text("❌ Ma'lumot topilmadi.")
        return

    rating = movie.get("imdbRating", "N/A")
    try:
        stars = "⭐" * round(float(rating) / 2)
    except Exception:
        stars = ""

    title_line = f"🎬 <b>{movie.get('Title')}</b> ({movie.get('Year')})"
    text = (
        f"{title_line}\n"
        f"<code>──────────────────────</code>\n"
        f"🎭 Janr: <i>{movie.get('Genre', 'N/A')}</i>\n"
        f"🎬 Rejissyor: <i>{movie.get('Director', 'N/A')}</i>\n"
        f"⏱ Davomiylik: <i>{movie.get('Runtime', 'N/A')}</i>\n"
        f"🌍 Til: <i>{movie.get('Language', 'N/A')}</i>\n"
        f"⭐ IMDb: <b>{rating}/10</b> {stars}\n"
        f"<code>──────────────────────</code>\n"
        f"📝 <i>{movie.get('Plot', '')[:300]}</i>"
    )

    title_encoded = movie.get("Title", "").replace(" ", "+")
    year = movie.get("Year", "")
    keyboard = [
        [InlineKeyboardButton(
            "🎬 IMDb sahifasi",
            url=f"https://www.imdb.com/title/{imdb_id}/"
        )],
        [InlineKeyboardButton(
            "▶️ Trailer (YouTube)",
            url=f"https://www.youtube.com/results?search_query={title_encoded}+{year}+trailer"
        )],
        [InlineKeyboardButton("📥 YouTube'dan topib yuklash", callback_data=f"movie_dl_{imdb_id}")],
        [InlineKeyboardButton("❌ Yopish", callback_data="close_search")],
    ]

    poster = movie.get("Poster", "")
    if poster and poster != "N/A":
        try:
            await query.message.delete()
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=poster,
                caption=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=PARSE_MODE,
            )
            return
        except Exception:
            pass

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)


async def handle_movie_download_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """OMDB film ma'lumotidan YouTube'da qidirib natijalarni ko'rsatish."""
    query = update.callback_query
    await query.answer("YouTube'dan qidirilmoqda...")

    imdb_id = query.data[len("movie_dl_"):]
    movie = await _omdb({"i": imdb_id})
    if not movie or movie.get("Response") == "False":
        await query.answer("❌ Film ma'lumoti topilmadi.", show_alert=True)
        return

    title = movie.get("Title", "")
    year = movie.get("Year", "")
    search_q = f"{title} {year} full movie"

    status_msg = await query.message.reply_text(
        f"🔍 <i>YouTube'dan «{title}» qidirilmoqda...</i>",
        parse_mode=PARSE_MODE
    )

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(opts) as ydl:
            results = await loop.run_in_executor(
                None, lambda: ydl.extract_info(f"ytsearch5:{search_q}", download=False)
            )

        entries = (results or {}).get("entries", [])
        if not entries:
            await status_msg.edit_text("😔 YouTube'da topilmadi. Qo'lda URL yuboring.")
            return

        keyboard = []
        for entry in entries[:5]:
            vid_title = (entry.get("title") or "")[:38]
            vid_id = entry.get("id", "")
            duration = entry.get("duration") or 0
            dur_str = f"{duration // 3600}:{(duration % 3600) // 60:02d}" if duration > 0 else ""
            label = f"▶️ {vid_title}" + (f" ({dur_str})" if dur_str else "")
            keyboard.append([InlineKeyboardButton(label[:64], callback_data=f"movie_yt_{vid_id}")])

        keyboard.append([InlineKeyboardButton("❌ Bekor qilish", callback_data="close_search")])
        await status_msg.edit_text(
            f"🎬 <b>«{title}» — YouTube natijalari:</b>\n"
            f"<i>Yuklab olish uchun tanlang:</i>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=PARSE_MODE,
        )
    except Exception as e:
        logger.error(f"Movie YT search error: {e}")
        await status_msg.edit_text("❌ YouTube'da qidirishda xatolik yuz berdi.")


async def handle_movie_yt_download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tanlangan YouTube videosini yuklab olish variantlarini ko'rsatish."""
    query = update.callback_query
    video_id = query.data[len("movie_yt_"):]
    await query.answer("Format tanlang...")

    keyboard = [
        [
            InlineKeyboardButton("🎧 Audio MP3", callback_data=f"dl_{video_id}"),
            InlineKeyboardButton("🎬 Video MP4", callback_data=f"vq_{video_id}"),
        ],
        [InlineKeyboardButton("📹 Video Note (Aylana)", callback_data=f"vnote_{video_id}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_dl")],
    ]
    await query.message.reply_text(
        "⬇️ <b>Format tanlang:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=PARSE_MODE,
    )
