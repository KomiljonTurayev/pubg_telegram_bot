import asyncio
import yt_dlp
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from music_menu import SEARCH_MUSIC
from database import db

logger = logging.getLogger(__name__)
PARSE_MODE = "HTML"

NUMS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]


async def search_music(query: str) -> list:
    ydl_opts = {
        "noplaylist": True,
        "quiet": True,
        "extract_flat": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "geo_bypass": True,
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    try:
        loop = asyncio.get_running_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(
                None, lambda: ydl.extract_info(f"ytsearch5:{query}", download=False)
            ) or {}
            results = []
            for entry in info.get("entries", []):
                if not entry:
                    continue
                results.append({
                    "id":       entry.get("id"),
                    "title":    entry.get("title"),
                    "duration": entry.get("duration"),
                    "url":      f"https://www.youtube.com/watch?v={entry.get('id')}",
                })
            return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


def get_search_results_keyboard(results: list) -> InlineKeyboardMarkup:
    keyboard = []
    for i, res in enumerate(results):
        title = res["title"] or "Noma'lum"
        title = (title[:42] + "…") if len(title) > 42 else title
        dur = int(res["duration"]) if res["duration"] else 0
        dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else "–:––"
        num = NUMS[i] if i < len(NUMS) else f"{i+1}."
        keyboard.append([
            InlineKeyboardButton(
                f"{num} {title}  [{dur_str}]",
                callback_data=f"show_music_options_{res['id']}",
            )
        ])
    return InlineKeyboardMarkup(keyboard)


async def process_music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text

    if query_text.lower().strip() in ("⬅️ back", "⬅️ orqaga"):
        await update.message.reply_text("🏠 Asosiy menyuga qaytildi.")
        return ConversationHandler.END

    status_msg = await update.message.reply_text(
        f"🔍 <b>Qidirilmoqda:</b> <i>{query_text}</i>\n"
        f"<code>░░░░░░░░░░</code>",
        parse_mode=PARSE_MODE,
    )
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        await db.save_search_history(update.effective_user.id, query_text)
    except Exception as e:
        logger.warning(f"Search history save error: {e}")

    results = await search_music(query_text)

    if not results:
        await status_msg.edit_text(
            "😔 <b>Hech narsa topilmadi.</b>\n"
            "<i>Boshqa nom yoki ijrochi nomini yozib ko'ring.</i>",
            parse_mode=PARSE_MODE,
        )
        return SEARCH_MUSIC

    reply_markup = get_search_results_keyboard(results)
    await status_msg.edit_text(
        f"🎵 <b>«{query_text}»</b> bo'yicha natijalar\n"
        f"<code>─────────────────────</code>\n"
        f"👇 <i>Yuklab olish uchun tanlang:</i>",
        reply_markup=reply_markup,
        parse_mode=PARSE_MODE,
    )
    return ConversationHandler.END
