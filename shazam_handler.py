import os
import logging
import tempfile
from shazamio import Shazam
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)
PARSE_MODE = "HTML"


async def _recognize(file_path: str) -> dict | None:
    try:
        out = await Shazam().recognize(file_path)
        track = out.get("track")
        if not track:
            return None

        album = ""
        for section in track.get("sections", []):
            for meta in section.get("metadata", []):
                if meta.get("title", "").lower() in ("album", "albom"):
                    album = meta.get("text", "")
                    break

        return {
            "title":  track.get("title", ""),
            "artist": track.get("subtitle", ""),
            "album":  album,
            "cover":  (
                track.get("images", {}).get("coverarthq")
                or track.get("images", {}).get("coverart", "")
            ),
        }
    except Exception as e:
        logger.error(f"Shazam xatolik: {e}")
        return None


async def handle_shazam_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    status = await msg.reply_text("🎵 <i>Musiqa aniqlanmoqda...</i>", parse_mode=PARSE_MODE)

    msg_obj = msg.voice or msg.audio or msg.video or msg.video_note
    if not msg_obj:
        await status.delete()
        return

    ext = ".mp4" if (msg.video or msg.video_note) else (".mp3" if msg.audio else ".ogg")
    tmp = tempfile.mktemp(suffix=ext, dir="/tmp")

    try:
        tg_file = await context.bot.get_file(msg_obj.file_id)
        await tg_file.download_to_drive(tmp)
        result = await _recognize(tmp)
    except Exception as e:
        logger.error(f"Shazam fayl xatolik: {e}")
        result = None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    if not result or not result.get("title"):
        await status.edit_text(
            "😔 <b>Musiqa aniqlanmadi.</b>\n"
            "<i>Boshqa qo'shiq yuboring yoki nomini matn sifatida yozing.</i>",
            parse_mode=PARSE_MODE,
        )
        return

    title  = result["title"]
    artist = result["artist"]
    album  = result["album"]
    search_q = f"{artist} - {title}" if artist else title
    context.user_data["shazam_query"] = search_q

    text = (
        f"🎵 <b>{title}</b>\n"
        f"👤 <i>{artist}</i>\n"
        + (f"💿 {album}\n" if album else "")
        + "<code>─────────────────────</code>"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬇️ YouTube'dan yuklab olish", callback_data="shazam_dl")],
        [InlineKeyboardButton("❌ Yopish", callback_data="close_search")],
    ])

    if result.get("cover"):
        try:
            await status.delete()
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=result["cover"],
                caption=text,
                reply_markup=keyboard,
                parse_mode=PARSE_MODE,
            )
            return
        except Exception as e:
            logger.warning(f"Shazam muqova yuborishda xatolik: {e}")

    await status.edit_text(text, reply_markup=keyboard, parse_mode=PARSE_MODE)
