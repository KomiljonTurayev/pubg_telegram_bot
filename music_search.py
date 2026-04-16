import re
import asyncio
import yt_dlp
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from music_menu import SEARCH_MUSIC
from database import db

logger = logging.getLogger(__name__)
PARSE_MODE = "HTML"
NUMS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
URL_RE = re.compile(r'https?://[^\s]+')


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
            for entry in (info.get("entries") or []):
                if not entry or not entry.get("id"):
                    continue
                results.append({
                    "id":       entry.get("id"),
                    "title":    entry.get("title") or "Noma'lum",
                    "duration": entry.get("duration"),
                })
            return results
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


async def get_url_info(url: str) -> dict | None:
    opts = {
        "quiet": True, "no_warnings": True,
        "noplaylist": True, "extract_flat": True,
    }
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


def _build_results_keyboard(results: list) -> InlineKeyboardMarkup:
    keyboard = []
    for i, res in enumerate(results):
        title = (res["title"][:42] + "…") if len(res["title"]) > 42 else res["title"]
        dur = int(res["duration"]) if res["duration"] else 0
        dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else "–:––"
        num = NUMS[i] if i < len(NUMS) else f"{i+1}."
        keyboard.append([
            InlineKeyboardButton(
                f"{num} {title}  [{dur_str}]",
                callback_data=f"show_music_options_{res['id']}",
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Yopish", callback_data="close_search")])
    return InlineKeyboardMarkup(keyboard)


async def process_music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query_text = update.message.text.strip()

    # Bekor qilish
    if query_text.lower() in ("❌ bekor", "bekor", "/cancel"):
        await update.message.reply_text("🏠 Asosiy menyuga qaytildi.")
        return ConversationHandler.END

    # URL yuborilgan bo'lsa — to'g'ridan-to'g'ri format tanlash
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
        return SEARCH_MUSIC  # Suhbatda qolamiz

    # Oddiy matn qidiruvi
    status_msg = await update.message.reply_text(
        f"🔍 <b>Qidirilmoqda:</b> <i>{query_text}</i>\n<code>░░░░░░░░░░</code>",
        parse_mode=PARSE_MODE,
    )
    await update.get_bot().send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    try:
        await db.save_search_history(update.effective_user.id, query_text)
    except Exception:
        pass

    results = await search_music(query_text)

    if not results:
        await status_msg.edit_text(
            "😔 <b>Hech narsa topilmadi.</b>\n"
            "<i>Boshqa nom yoki ijrochi nomini yozib ko'ring:</i>",
            parse_mode=PARSE_MODE,
        )
        return SEARCH_MUSIC  # Qayta qidirishga ruxsat

    reply_markup = _build_results_keyboard(results)
    await status_msg.edit_text(
        f"🎵 <b>«{query_text}»</b> natijalari:\n"
        f"<code>─────────────────────</code>\n"
        f"👇 <i>Tanlang yoki yangi nom yozing:</i>",
        reply_markup=reply_markup,
        parse_mode=PARSE_MODE,
    )
    return SEARCH_MUSIC  # Foydalanuvchi qayta qidira oladi
