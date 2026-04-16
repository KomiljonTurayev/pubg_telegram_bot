import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database import db

logger = logging.getLogger(__name__)
PARSE_MODE = "HTML"

# Conversation states for music module
SEARCH_MUSIC = 3

async def music_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Musiqa bo'limining asosiy menyusini ko'rsatish."""
    keyboard = [
        ["🔎 Search Music"],
        ["🔥 Trending Music", "📥 My Downloads"],
        ["⬅️ Back"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🎵 <b>Musiqa menyusi:</b>\n\n"
        "Qidirish, trenddagi musiqalarni ko'rish yoki yuklamalaringizni boshqarish uchun tanlang.",
        reply_markup=reply_markup,
        parse_mode=PARSE_MODE
    )
    return ConversationHandler.END # Bu yerda ConversationHandler tugaydi, chunki keyingi bosqichlar alohida handlerlar orqali boshqariladi

async def music_start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Musiqa qidiruvini boshlash."""
    await update.message.reply_text(
        "🎵 <b>Musiqa nomini yoki ijrochini yozing:</b>\n\n"
        "Masalan: <i>Sherali Jo'rayev - Karvon</i>",
        parse_mode=PARSE_MODE
    )
    return SEARCH_MUSIC

async def show_trending_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eng ko'p yuklangan musiqalar ro'yxatini ko'rsatish."""
    top_music = await db.get_top_music()
    if not top_music:
        return await update.message.reply_text("📉 Trenddagi musiqalar topilmadi.")
    
    text = "🔥 <b>Trenddagi top musiqalar:</b>\n\n"
    keyboard = []
    for i, m in enumerate(top_music, 1):
        text += f"{i}. {m[1]} - {m[0]}\n"
        keyboard.append([InlineKeyboardButton(f"🎧 {m[0]}", callback_data=f"dl_{m[3]}")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)

async def show_my_downloads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchining qidiruv tarixiga asoslangan tavsiyalar."""
    history = await db.get_recommendations(update.effective_user.id)
    if not history:
        return await update.message.reply_text("📥 Sizda hali qidiruv tarixi mavjud emas.")
    
    text = "📜 <b>Sizning oxirgi qidiruvlaringiz:</b>\n\n"
    for i, h in enumerate(history, 1):
        text += f"{i}. <code>{h[0]}</code>\n"
    
    text += "\n<i>Tavsiya: Yuqoridagi nomlarni nusxalab qidiruvga berishingiz mumkin.</i>"
    await update.message.reply_text(text, parse_mode=PARSE_MODE)