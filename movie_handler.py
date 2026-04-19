import aiohttp
import logging
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
