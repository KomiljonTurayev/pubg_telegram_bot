import os
import asyncio
import yt_dlp
import re
import time
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from database import db

# Bir vaqtning o'zida yuklashlarni cheklash uchun Semaphore
download_semaphore = asyncio.Semaphore(3)
PARSE_MODE = "HTML"

# Linklarni tekshirish uchun regex
URL_REGEX = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

def is_url(text):
    """Matn havola ekanligini tekshirish."""
    return re.search(URL_REGEX, text) is not None

def sanitize_filename(name):
    """Fayl nomidagi noqonuniy belgilarni olib tashlash."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

async def search_music(query: str):
    """YouTube-dan eng yaxshi 5 ta audio natijani qidirish."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'extract_flat': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(f"ytsearch5:{query}", download=False))
            results = []
            for entry in info.get('entries', []):
                results.append({
                    'id': entry.get('id'),
                    'title': entry.get('title'),
                    'duration': entry.get('duration'),
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}"
                })
            return results
    except Exception as e:
        logging.error(f"Search error: {e}")
        return []

async def get_link_info(url: str):
    """Havola haqida ma'lumot olish (Sarlavha va platforma)."""
    ydl_opts = {'quiet': True, 'noplaylist': True, 'no_warnings': True, 'extract_flat': True}
    try:
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
            return {
                'title': info.get('title', 'Media'),
                'extractor': info.get('extractor_key', 'Link'),
                'webpage_url': info.get('webpage_url', url)
            }
    except Exception as e:
        logging.error(f"Link info error: {e}")
        return None

async def download_and_send_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: str = None):
    """Tanlangan videoni audio formatida yuklab olib yuborish (Legacy wrapper)."""
    return await handle_media_download(update, context, video_id=video_id, is_video=False)

async def handle_media_download(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: str = None, is_video: bool = False):
    """Universal yuklab olish funksiyasi."""
    if update.callback_query:
        query = update.callback_query
        data = query.data.split("_")
        is_video = data[0] == 'vdl'
        video_id = data[1]
        await query.answer()
        message = query.message
    else:
        message = update.message

    if not video_id: return

    # YouTube ID bo'lsa link yasaymiz, aks holda 'external' bo'lsa contextdan olamiz
    video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id != 'external' else context.user_data.get('last_url')
    if not video_url: return

    if not is_video and video_id != 'external':
        cached = await db.get_cached_music(video_id)
        if cached:
            try:
                await context.bot.send_audio(chat_id=update.effective_chat.id, audio=cached[0], title=cached[1], performer=cached[2], caption=f"🎵 {cached[1]}\n⚡️ <i>Keshdan yuborildi</i>", parse_mode=PARSE_MODE)
                return
            except Exception as e:
                logging.error(f"Cache error: {e}")

    status_msg = await message.reply_text(f"⏳ {'Video' if is_video else 'Audio'} yuklanmoqda...", parse_mode=PARSE_MODE)

    loop = asyncio.get_event_loop()
    last_edit_time = 0

    def progress_hook(d):
        nonlocal last_edit_time
        if d['status'] == 'downloading':
            current_time = time.time()
            if current_time - last_edit_time < 2.5: return
            last_edit_time = current_time
            percent = d.get('_percent_str', '0%').strip()
            clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', percent)
            
            try:
                p_float = float(clean_percent.replace('%', ''))
                bar = "█" * int(p_float // 10) + "░" * (10 - int(p_float // 10))
                text = f"⏳ <b>Yuklanmoqda...</b>\n\n<code>{bar}</code> {percent}"
                asyncio.run_coroutine_threadsafe(status_msg.edit_text(text, parse_mode=PARSE_MODE), loop)
            except: pass

    async with download_semaphore:
        folder = 'downloads'
        if not os.path.exists(folder): os.makedirs(folder)
        outtmpl = f"{folder}/%(id)s_{int(time.time())}.%(ext)s"

        file_path = None
        ydl_opts = {
            'outtmpl': outtmpl,
            'progress_hooks': [progress_hook],
            'quiet': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'noplaylist': True
        }

        if is_video:
            ydl_opts['format'] = 'best[ext=mp4]/best'
        else:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(video_url, download=True))
                file_ext = 'mp3' if not is_video else 'mp4'
                file_path = ydl.prepare_filename(info).rsplit('.', 1)[0] + '.' + file_ext
                title = info.get('title', 'Media')

                if is_video:
                    await context.bot.send_video(chat_id=update.effective_chat.id, video=open(file_path, 'rb'), caption=f"🎬 <b>{title}</b>", parse_mode=PARSE_MODE)
                else:
                    uploader = info.get('uploader', 'Artist')
                    sent = await context.bot.send_audio(chat_id=update.effective_chat.id, audio=open(file_path, 'rb'), title=title, performer=uploader, caption=f"🎵 <b>{title}</b>", parse_mode=PARSE_MODE)
                    if video_id != 'external': await db.cache_music(video_id, sent.audio.file_id, title, uploader)

                await status_msg.delete()
        except Exception as e:
            logging.error(f"Download error: {e}")
            await status_msg.edit_text("❌ Xatolik yuz berdi. Fayl o'chirilgan yoki juda katta bo'lishi mumkin.")
        finally:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

async def cancel_dl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yuklashni bekor qilish."""
    await update.callback_query.message.delete()
    await update.callback_query.answer("Bekor qilindi.")

def get_search_results_keyboard(results):
    """Qidiruv natijalari uchun Inline Keyboard yaratish."""
    keyboard = []
    for res in results:
        # Sarlavha uzunligini cheklash (InlineKeyboardButton limiti 64 byte callback_data uchun)
        title = res['title'][:40] + "..." if len(res['title']) > 40 else res['title']
        duration_min = f"{res['duration'] // 60}:{res['duration'] % 60:02d}" if res['duration'] else ""
        
        keyboard.append([
            InlineKeyboardButton(
                f"🎵 {title} [{duration_min}]", 
                callback_data=f"dl_{res['id']}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)