import json
import logging
import os
import time
import warnings
import traceback
import threading
import urllib.request
warnings.filterwarnings("ignore", message=".*per_message=False.*", category=Warning)
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice,
    ReplyKeyboardMarkup, KeyboardButton, InlineQueryResultArticle,
    InputTextMessageContent, InlineQueryResultCachedAudio, WebAppInfo
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler, filters, ContextTypes, ConversationHandler, InlineQueryHandler
)
from telegram.error import Conflict, NetworkError, TimedOut
from config import Config
from database import db
from utils import admin_only, ban_check, create_stat_chart, generate_receipt_pdf, cleanup_temp_files
from music_menu import SEARCH_MUSIC # music_menu dan SEARCH_MUSIC import qilinadi
import music_search
import music_downloader
import shazam_handler
import trending as trending_mod
import movie_handler
import api as web_api

BOT_START_TIME = time.time()

# Buyurtma bosqichlari (Conversation states)
GET_PUBG_ID, GET_PHONE, CONFIRM_ORDER = range(3)
# SEARCH_MUSIC music_menu dan import qilinadi
ADD_PR_NAME, ADD_PR_DESC, ADD_PR_PRICE, ADD_PR_PHOTO = range(4, 8)

# Logging sozlamalari
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PARSE_MODE = "HTML"

ITEMS_PER_PAGE = 5

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botni boshlash va foydalanuvchini ro'yxatga olish."""
    user = update.effective_user
    logger.info(f"Yangi foydalanuvchi bog'landi: {user.full_name} (ID: {user.id})")
    await db.add_user(user.id, user.username, user.full_name)
    
    # Deep link orqali kelgan yuklab olish so'rovi
    if context.args and context.args[0].startswith("dl_"):
        video_id = context.args[0].split("_")[1]
        await music_downloader.handle_media_download(update, context, video_id=video_id, is_video=False)
        return

    is_admin = user.id == Config.ADMIN_ID or await db.is_admin_db(user.id)
    
    keyboard = [
        ["🎵 Musiqa qidirish", "🎙 Shazam"],
        ["🔝 Top 10", "👤 Profil va Bio"]
    ]
    if is_admin:
        keyboard.append(["📊 Statistika (Admin)", "📦 Barcha Buyurtmalar"])
        keyboard.append(["➕ Mahsulot qo'shish"])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"👋 <b>Assalomu alaykum, {user.full_name}! Musiqa olamiga xush kelibsiz.</b>\n"
        f"<code>─────────────────────</code>\n"
        f"🔍  Istalgan qo'shiq nomini yozing\n"
        f"🎙  Ovozli xabar orqali musiqani toping\n"
        f"⚡️  YouTube-dan tezkor yuklab oling\n"
        f"<code>─────────────────────</code>\n"
        f"👇 <i>Kerakli bo'limni tanlang:</i>",
        reply_markup=reply_markup,
        parse_mode=PARSE_MODE
    )

@ban_check
async def show_portfolio_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Portfolio ma'lumotlarini inline ko'rinishida chiqarish."""
    query = update.callback_query
    await query.answer()
    text = (
        "🚀 <b>Dasturlash Xizmatlari:</b>\n\n"
        "• 🤖 <b>Botlar:</b> Murakkab Telegram tizimlari.\n"
        "• 📱 <b>Mobil:</b> React Native & Flutter.\n"
        "• 🌐 <b>Web:</b> FastAPI & Django backend.\n\n"
        "📩 @developer_username"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Ortga", callback_data="back_to_bio")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)

@ban_check
async def show_bio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi profili va qo'shimcha xizmatlarni ko'rsatish."""
    marketplace_url = f"{Config.SELF_URL}/market" if Config.SELF_URL else None
    text = (
        "<b>Profil va xizmatlar</b>\n"
        "<code>---------------------</code>\n"
        "Marketplace: PUBG skinlari va UC xizmatlari.\n"
        "Portfolio: dasturlash bo'yicha xizmatlar.\n"
        "Buyurtmalar: xaridlaringiz tarixi.\n"
        "<code>---------------------</code>"
    )

    if marketplace_url:
        keyboard = [
            [InlineKeyboardButton("Marketplace", web_app=WebAppInfo(url=marketplace_url))],
            [InlineKeyboardButton("Portfolio", callback_data="view_portfolio")],
            [InlineKeyboardButton("Buyurtmalarim", callback_data="my_orders_list")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("Portfolio", callback_data="view_portfolio")],
            [InlineKeyboardButton("Buyurtmalarim", callback_data="my_orders_list")],
        ]
        text += "\n\n<i>Marketplace tugmasi chiqishi uchun `SELF_URL` yoki `RENDER_EXTERNAL_URL` sozlanishi kerak.</i>"

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)

@ban_check
async def show_marketplace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PUBG skinlari katalogini sahifalarga bo'lib ko'rsatish."""
    query = update.callback_query
    page = 0
    if query:
        await query.answer()
        data = query.data.split("_")
        page = int(data[-1]) if data[-1].isdigit() else 0

    offset = page * ITEMS_PER_PAGE
    products = await db.get_products_paginated(ITEMS_PER_PAGE, offset)
    total_products = await db.get_products_count()
    
    if not products:
        text = "🛒 Hozircha do'konimiz bo'sh."
        if query: await query.edit_message_text(text)
        else: await update.message.reply_text(text)
        return

    total_pages = (total_products + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    text = f"🛒 <b>Mahsulotlar katalogi</b> (Sahifa {page+1}/{total_pages})\n\nBatafsil ma'lumot uchun mahsulotni tanlang:"
    
    keyboard = []
    for p in products:
        keyboard.append([InlineKeyboardButton(f"📦 {p[1]} - {p[3]:,.0f} UZS", callback_data=f"view_pr_{p[0]}")])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"market_page_{page-1}"))
    if (page + 1) * ITEMS_PER_PAGE < total_products:
        nav_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"market_page_{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(update.effective_chat.id, text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        else:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)

async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bitta mahsulot haqida to'liq ma'lumot ko'rsatish."""
    query = update.callback_query
    product_id = int(query.data.split("_")[-1])
    p = await db.get_product_by_id(product_id)
    await query.answer()

    if not p: return

    text = (
        f"📦 <b>{p[1]}</b>\n\n"
        f"📝 {p[2]}\n\n"
        f"💰 <b>Narxi:</b> {p[3]:,.0f} UZS"
    )
    keyboard = [
        [InlineKeyboardButton("Sotib olish 💳", callback_data=f"buy_{p[0]}")],
        [InlineKeyboardButton("⬅️ Katalogga qaytish", callback_data="market_page_0")]
    ]

    if p[4]: # image_url
        try:
            await query.message.delete()
            await context.bot.send_photo(update.effective_chat.id, p[4], caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)
        except:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)
    else:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)

async def music_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Musiqa qidiruvini boshlash."""
    msg_text = (
        "🎵 <b>Musiqa qidirish markazi</b>\n"
        "<code>─────────────────────</code>\n"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(msg_text + "👇 Qo'shiq nomi yoki YouTube havolasini yuboring:", parse_mode=PARSE_MODE)
    else:
        await update.message.reply_text(msg_text + "👇 Qo'shiq nomi yoki YouTube havolasini yuboring:", parse_mode=PARSE_MODE)
    return SEARCH_MUSIC

async def shazam_btn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shazam tugmasi bosilganda ko'rsatma berish."""
    await update.message.reply_text(
        "🎙 <b>Musiqani aniqlash uchun:</b>\n\n"
        "Menga 5-10 soniyalik <b>ovozli xabar (voice)</b>, <b>audio</b> yoki <b>video</b> yuboring. Men uni darhol aniqlab beraman!",
        parse_mode=PARSE_MODE
    )

async def video_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Video yuborilganda conversion tugmasini ko'rsatish."""
    msg = update.message
    if msg.video or (msg.document and msg.document.mime_type.startswith("video/")):
        keyboard = [[InlineKeyboardButton("📹 Video Note (Aylana) ga o'tkazish", callback_data=f"convert_vn")]]
        await msg.reply_text(
            "🎬 <b>Video qabul qilindi!</b>\nUni Telegram formatiga (aylana video) o'tkazmoqchimisiz?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            reply_to_message_id=msg.message_id,
            parse_mode=PARSE_MODE
        )
    else:
        await shazam_handler.handle_shazam_request(update, context)

async def process_music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """YouTube qidiruv natijalarini ko'rsatish."""
    return await music_search.process_music_search(update, context)

async def _prepare_buy_context(context: ContextTypes.DEFAULT_TYPE, product_id: int):
    """Tanlangan mahsulotni user_data ga yozish."""
    product = await db.get_product_by_id(product_id)
    if not product:
        return None

    context.user_data['buy_product_id'] = product_id
    context.user_data['buy_product_name'] = product[1]
    context.user_data['buy_product_price'] = product[3]
    context.user_data['is_editing'] = False
    return product

async def start_buy_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sotib olish jarayonini boshlash (PUBG ID so'rash)."""
    query = update.callback_query
    product_id = int(query.data.split("_")[1])
    product = await _prepare_buy_context(context, product_id)

    if not product:
        await query.answer("Mahsulot topilmadi.")
        return ConversationHandler.END

    await query.message.reply_text(
        f"<b>{product[1]}</b> tanlandi.\n\n"
        "<b>PUBG ID raqamingizni kiriting:</b>\n"
        "(Masalan: 5123456789)",
        parse_mode=PARSE_MODE,
    )
    await query.answer()
    return GET_PUBG_ID

@ban_check
async def handle_web_app_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mini App'dan tanlangan mahsulotni chat ichidagi buyurtma oqimiga ulash."""
    message = update.message
    data = getattr(getattr(message, "web_app_data", None), "data", "")

    try:
        payload = json.loads(data)
        if payload.get("type") != "buy_product":
            raise ValueError("unexpected payload type")
        product_id = int(payload["product_id"])
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        await message.reply_text("Mini App ma'lumoti noto'g'ri keldi. Qayta urinib ko'ring.")
        return ConversationHandler.END

    product = await _prepare_buy_context(context, product_id)
    if not product:
        await message.reply_text("Tanlangan mahsulot topilmadi.")
        return ConversationHandler.END

    await message.reply_text(
        f"<b>{product[1]}</b> marketplace'dan tanlandi.\n\n"
        "<b>PUBG ID raqamingizni kiriting:</b>\n"
        "(Masalan: 5123456789)",
        parse_mode=PARSE_MODE,
    )
    return GET_PUBG_ID

@ban_check
async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga o'z buyurtmalarini ko'rsatish."""
    query = update.callback_query
    user_id = update.effective_user.id
    orders = await db.get_user_orders(user_id)
    
    if query: await query.answer()
    
    if not orders:
        await update.effective_message.reply_text("📭 Sizda hali buyurtmalar mavjud emas.", parse_mode=PARSE_MODE)
        return

    text = "<b>🛍 Buyurtmalaringiz tarixi:</b>\n\n"
    for o in orders:
        # o[0]: name, o[1]: created_at, o[2]: amount, o[3]: pubg_id, o[4]: status
        date_str = o[1].strftime("%Y-%m-%d %H:%M")
        status_emoji = "✅" if o[4] == 'paid' else "⏳"
        text += (
            f"🔹 <b>{o[0]}</b>\n"
            f"📅 Sana: {date_str}\n"
            f"💰 Summa: {o[2]:,.0f} UZS\n"
            f"🆔 PUBG ID: {o[3]}\n"
            f"📊 Holati: {status_emoji} {o[4]}\n\n"
        )
    
    await update.effective_message.reply_text(text, parse_mode=PARSE_MODE)

async def get_pubg_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PUBG ID qabul qilish va telefonni so'rash (yoki xulosaga qaytish)."""
    context.user_data['pubg_id'] = update.message.text
    if context.user_data.get('is_editing'):
        context.user_data['is_editing'] = False
        return await show_summary(update, context)

    await update.message.reply_text("📞 <b>Telefon raqamingizni kiriting:</b>", parse_mode=PARSE_MODE)
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telefon raqamini qabul qilish va tasdiqlash xabarini ko'rsatish."""
    context.user_data['phone'] = update.message.text
    return await show_summary(update, context)

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga kiritilgan ma'lumotlarni tekshirish uchun ko'rsatish."""
    pubg_id = context.user_data.get('pubg_id')
    phone = context.user_data.get('phone')
    product_name = context.user_data.get('buy_product_name')
    price = context.user_data.get('buy_product_price')

    text = (
        f"📋 <b>Buyurtma ma'lumotlarini tekshiring:</b>\n\n"
        f"📦 Mahsulot: <b>{product_name}</b>\n"
        f"💰 Narxi: <b>{price:,.0f} UZS</b>\n"
        f"🆔 PUBG ID: <code>{pubg_id}</code>\n"
        f"📞 Telefon: <code>{phone}</code>\n\n"
        f"To'lovni boshlash uchun tasdiqlang yoki tahrirlang."
    )
    keyboard = [
        [InlineKeyboardButton("📝 PUBG ID ni tahrirlash", callback_data="edit_pubg_id")],
        [InlineKeyboardButton("📝 Telefonni tahrirlash", callback_data="edit_phone")],
        [InlineKeyboardButton("✅ Tasdiqlash va To'lash", callback_data="confirm_checkout")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_buy")]
    ]
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)
    else:
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)
    return CONFIRM_ORDER

async def process_confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasdiqlash yoki tahrirlash tugmalarini boshqarish."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "edit_pubg_id":
        context.user_data['is_editing'] = True
        await query.message.delete()
        await query.message.reply_text("🆔 Yangi PUBG ID raqamingizni kiriting:")
        return GET_PUBG_ID
    elif data == "edit_phone":
        context.user_data['is_editing'] = True
        await query.message.delete()
        await query.message.reply_text("📞 Yangi telefon raqamingizni kiriting:")
        return GET_PHONE
    elif data == "confirm_checkout":
        product_name = context.user_data['buy_product_name']
        price = context.user_data['buy_product_price']
        price_in_cents = int(float(price) * 100)
        await context.bot.send_invoice(
            chat_id=update.effective_user.id,
            title=f"To'lov: {product_name}",
            description=f"PUBG ID: {context.user_data['pubg_id']}",
            payload=f"payload_{context.user_data['buy_product_id']}",
            provider_token=Config.PAYMENT_TOKEN,
            currency="UZS",
            prices=[LabeledPrice(f"{product_name}", price_in_cents)]
        )
        return ConversationHandler.END
    elif data == "cancel_buy":
        await query.message.edit_text("❌ Buyurtma jarayoni bekor qilindi.")
        return ConversationHandler.END

@admin_only
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 <b>Yangi mahsulot nomini kiriting:</b>", parse_mode=PARSE_MODE)
    return ADD_PR_NAME

async def add_product_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_pr_name'] = update.message.text
    await update.message.reply_text("📝 <b>Mahsulot tavsifini kiriting:</b>", parse_mode=PARSE_MODE)
    return ADD_PR_DESC

async def add_product_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_pr_desc'] = update.message.text
    await update.message.reply_text("💰 <b>Mahsulot narxini kiriting:</b>", parse_mode=PARSE_MODE)
    return ADD_PR_PRICE

async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(" ", ""))
        context.user_data['new_pr_price'] = price
        await update.message.reply_text("🖼 <b>Mahsulot rasm havolasini yoki Telegram File ID yuboring:</b>", parse_mode=PARSE_MODE)
        return ADD_PR_PHOTO
    except ValueError:
        await update.message.reply_text("❌ Narxni raqamlarda kiriting!")
        return ADD_PR_PRICE

async def add_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    image_url = update.message.photo[-1].file_id if update.message.photo else update.message.text
    await db.add_product(context.user_data['new_pr_name'], context.user_data['new_pr_desc'], context.user_data['new_pr_price'], image_url)
    await update.message.reply_text("✅ <b>Mahsulot qo'shildi!</b>", parse_mode=PARSE_MODE)
    return ConversationHandler.END

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """To'lov muvaffaqiyatli yakunlanganda buyurtmani bazaga yozish."""
    payment = update.message.successful_payment
    product_id = int(payment.invoice_payload.split("_")[1])
    pubg_id = context.user_data.get('pubg_id', 'Noma\'lum')
    phone = context.user_data.get('phone', 'Noma\'lum')
    product_name = context.user_data.get('buy_product_name', 'Mahsulot')
    user_id = update.effective_user.id
    full_name = update.effective_user.full_name
    amount = payment.total_amount / 100

    order_id = await db.add_order(user_id, product_id, amount, pubg_id, phone)

    await update.message.reply_text(
        f"✅ <b>To'lov muvaffaqiyatli!</b>\n\n"
        f"Buyurtmangiz qabul qilindi. Tez orada operatorlarimiz bog'lanishadi.\n"
        f"🆔 PUBG ID: {pubg_id}\n💳 Buyurtma ID: <code>{order_id}</code>",
        parse_mode=PARSE_MODE
    )

    # Adminga yangi buyurtma haqida xabar berish
    await context.bot.send_message(
        Config.ADMIN_ID, 
        f"💰 **Yangi buyurtma!**\n\nFoydalanuvchi: {update.effective_user.full_name}\nSumma: {amount} UZS\nID: {user_id}"
    )

    # PDF Kvitansiya generatsiya qilish va yuborish
    try:
        pdf_file = generate_receipt_pdf(order_id, full_name, product_name, amount, pubg_id, phone)
        with open(pdf_file, 'rb') as doc:
            await update.message.reply_document(
                document=doc,
                caption="📄 Xaridingiz uchun kvitansiya."
            )
        os.remove(pdf_file)
    except Exception as e:
        logger.error(f"PDF generatsiya qilishda xatolik: {e}")

async def shazam_dl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shazam tomonidan topilgan qo'shiqni YouTube da qidirish va yuklash."""
    query = update.callback_query
    await query.answer()
    
    shazam_info = context.user_data.get("shazam_info")
    search_q = context.user_data.get("shazam_query", "")
    
    if not search_q:
        await query.edit_message_text("❌ Qidiruv ma'lumoti topilmadi.")
        return

    results = await music_search.search_music(search_q)
    if not results:
        err_text = "😔 <b>Topilmadi.</b>\n<i>Qo'lda nomini yozib qidiring.</i>"
        if query.message.photo:
            await query.edit_message_caption(caption=err_text, parse_mode=PARSE_MODE)
        else:
            await query.edit_message_text(text=err_text, parse_mode=PARSE_MODE)
        return

    if shazam_info:
        text = (
            f"🎵 <b>{shazam_info['title']}</b>\n"
            f"👤 <i>{shazam_info['artist']}</i>\n"
            + (f"💿 {shazam_info['album']}\n" if shazam_info.get('album') else "")
            + (f"🎸 Janr: {shazam_info.get('genre')}\n" if shazam_info.get('genre') else "")
            + "<code>─────────────────────</code>\n"
            "📥 <b>YouTube natijalari:</b>"
        )
    else:
        text = (
            f"🔍 <b>«{search_q[:40]}»</b> natijalari:\n"
            f"<code>─────────────────────</code>"
        )

    reply_markup = music_search.build_results_keyboard(results)
    if query.message.photo:
        await query.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    else:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=PARSE_MODE)


async def cancel_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jarayonni bekor qilish."""
    await update.message.reply_text("❌ Jarayon bekor qilindi.")
    return ConversationHandler.END

async def close_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline qidiruv kartasini toza yopish."""
    await update.callback_query.answer()
    await update.callback_query.message.delete()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Barcha xatolarni markazlashgan holda boshqarish."""
    error = context.error
    if isinstance(error, Conflict):
        logger.warning("[!] 409 Conflict: Boshqa bot instansiyasi ishlayapti. Qayta ulanilmoqda...")
        return
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning(f"Tarmoq xatoligi (avtomatik qayta uriniladi): {error}")
        return
    logger.error(f"Kutilmagan xatolik: {error}")
    logger.debug(traceback.format_exc())

@admin_only
async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uchun keng qamrovli statistika paneli."""
    total_users, growth      = await db.get_stats()
    total_searches           = await db.get_total_searches()
    dau                      = await db.get_daily_active_users()
    most_searched            = await db.get_most_searched(5)
    cache_count              = await db.get_cache_count()
    total_downloads          = await db.get_total_downloads()

    uptime_sec  = int(time.time() - BOT_START_TIME)
    uptime_str  = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m {uptime_sec % 60}s"

    top_queries = "\n".join(
        f"  {i+1}. «{q[0][:30]}» — {q[1]} marta"
        for i, q in enumerate(most_searched)
    ) or "  (ma'lumot yo'q)"

    text = (
        f"📊 <b>Admin Panel</b>\n"
        f"<code>──────────────────────</code>\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users}</b>\n"
        f"🟢 Bugungi faol foydalanuvchilar: <b>{dau}</b>\n"
        f"🔍 Jami qidiruvlar: <b>{total_searches}</b>\n"
        f"📥 Jami yuklab olingan: <b>{total_downloads}</b>\n"
        f"🎵 Keshlangan musiqalar: <b>{cache_count}</b>\n"
        f"⏱ Bot uptime: <code>{uptime_str}</code>\n"
        f"<code>──────────────────────</code>\n"
        f"🔝 <b>Eng ko'p qidiruvlar:</b>\n{top_queries}"
    )

    chart_buf = create_stat_chart(growth)
    await update.message.reply_photo(
        photo=chart_buf,
        caption=text,
        parse_mode=PARSE_MODE,
    )

async def developer_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dasturchi haqida ma'lumot."""
    text = (
        "👨‍💻 <b>Dasturchi haqida</b>\n"
        "<code>──────────────────────</code>\n"
        "🧑 Ism: <b>Komiljon Turayev</b>\n"
        "💼 Lavozim: <i>Android Developer & Software Engineer</i>\n"
        "🐙 GitHub: <a href=\"https://github.com/KomiljonTurayev\">KomiljonTurayev</a>\n"
        "📱 Telegram: @KomiljonTurayev\n"
        "<code>──────────────────────</code>\n"
        "🤖 <i>Bu bot Python + python-telegram-bot asosida qurilgan media va marketplace boti.</i>"
    )
    keyboard = [
        [InlineKeyboardButton("🐙 GitHub", url="https://github.com/KomiljonTurayev")],
    ]
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=PARSE_MODE,
        disable_web_page_preview=True,
    )


async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trending musiqa, video va filmlarni ko'rsatish."""
    status = await update.message.reply_text(
        "📡 <i>Trending ma'lumotlar yuklanmoqda...</i>", parse_mode=PARSE_MODE
    )

    music_list  = await trending_mod.get_trending_music()
    videos_list = await trending_mod.get_trending_videos()

    # ── Trending musiqalar ──────────────────────────────────
    if music_list:
        dz_cache = {r["deezer_id"]: r for r in music_list}
        context.user_data["dz_cache"] = {**context.user_data.get("dz_cache", {}), **dz_cache}

        music_text = "🔥 <b>Trending Musiqalar</b> (Deezer World Chart)\n<code>──────────────────────</code>\n"
        keyboard = []
        for i, t in enumerate(music_list[:10], 1):
            music_text += f"{i}. <b>{t['artist']}</b> — {t['title']}  [{t['duration']}]\n"
            label = f"{i}. {t['artist']} — {t['title']}"
            if len(label) > 55:
                label = label[:54] + "…"
            keyboard.append([
                InlineKeyboardButton(label, callback_data=f"dz_show_{t['deezer_id']}")
            ])
        keyboard.append([InlineKeyboardButton("❌ Yopish", callback_data="close_search")])

        await status.edit_text(
            music_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=PARSE_MODE,
        )
    else:
        await status.edit_text("😔 Hozirda trending ma'lumotlar mavjud emas.", parse_mode=PARSE_MODE)
        return

    # ── Trending YouTube videolar (agar API key bor bo'lsa) ──
    if videos_list:
        vid_text = "🎬 <b>Trending YouTube Videolar</b>\n<code>──────────────────────</code>\n"
        vid_keyboard = []
        for i, v in enumerate(videos_list[:5], 1):
            vid_text += f"{i}. {v['title'][:50]}\n   📺 {v['channel']}\n"
            vid_keyboard.append([
                InlineKeyboardButton(
                    f"▶️ {v['title'][:40]}",
                    callback_data=f"show_music_options_{v['video_id']}",
                )
            ])
        vid_keyboard.append([InlineKeyboardButton("❌ Yopish", callback_data="close_search")])

        await update.message.reply_text(
            vid_text,
            reply_markup=InlineKeyboardMarkup(vid_keyboard),
            parse_mode=PARSE_MODE,
        )


@admin_only
async def view_all_orders_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha buyurtmalarni adminga ko'rsatish."""
    orders = await db.get_all_orders()
    if not orders:
        return await update.message.reply_text("📦 Hozircha buyurtmalar yo'q.")

    for o in orders:
        # o[0]: id, o[1]: full_name, o[2]: product_name, o[3]: pubg_id, o[4]: phone, o[5]: amount, o[6]: status, o[7]: created_at
        text = (
            f"🆔 <b>Buyurtma #{o[0]}</b>\n"
            f"👤 Mijoz: {o[1]}\n"
            f"📦 Mahsulot: {o[2]}\n"
            f"🎮 PUBG ID: {o[3]}\n"
            f"📞 Tel: {o[4]}\n"
            f"💰 Summa: {o[5]:,.0f} UZS\n"
            f"📅 Sana: {o[7].strftime('%Y-%m-%d %H:%M')}\n"
            f"📊 Holati: <b>{o[6]}</b>"
        )
        keyboard = [[
            InlineKeyboardButton("✅ Bajarildi", callback_data=f"st_paid_{o[0]}"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"st_cancelled_{o[0]}")
        ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)

@admin_only
async def update_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buyurtma holatini yangilash."""
    query = update.callback_query
    _, status, oid = query.data.split("_")
    await db.update_order_status(int(oid), status)
    await query.answer(f"Buyurtma #{oid} holati '{status}' ga o'zgartirildi.")
    new_text = query.message.text_html.split("📊 Holati:")[0] + f"📊 Holati: <b>{status}</b>"
    await query.edit_message_text(new_text, parse_mode=PARSE_MODE)

async def show_top_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eng ko'p yuklangan musiqalar ro'yxatini ko'rsatish."""
    top_music = await db.get_top_music()
    if not top_music:
        await update.message.reply_text("📉 Hozircha yuklab olingan musiqalar yo'q.")
        return
    
    text = "<b>🔝 Eng ko'p yuklangan 10 ta musiqa:</b>\n\n"
    keyboard = []
    for i, m in enumerate(top_music, 1):
        # m[0]: title, m[1]: performer, m[2]: count, m[3]: video_id
        text += f"{i}. {m[1]} - {m[0]} (💾 {m[2]} marta)\n"
        keyboard.append([InlineKeyboardButton(f"{i}. {m[0]}", callback_data=f"dl_{m[3]}")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=PARSE_MODE)

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """To'lov oldidan tasdiqlash."""
    query = update.pre_checkout_query
    await query.answer(ok=True)

@admin_only
async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Foydalanuvchi ID sini kiriting: /ban 123456")
    user_id = int(context.args[0])
    await db.ban_user(user_id)
    await update.message.reply_text(f"🚫 Foydalanuvchi {user_id} banlandi.")

@admin_only
async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Foydalanuvchi ID sini kiriting: /unban 123456")
    user_id = int(context.args[0])
    await db.unban_user(user_id)
    await update.message.reply_text(f"✅ Foydalanuvchi {user_id} bandan chiqarildi.")

@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Xabarni kiriting: /broadcast Salom hammaga!")
    msg = " ".join(context.args)
    users = await db.get_all_users()
    sent_count = 0
    for user in users:
        try: 
            await context.bot.send_message(user[0], msg)
            sent_count += 1
        except Exception as e:
            logger.error(f"Xabar yuborishda xatolik (User: {user[0]}): {e}")
            continue
    await update.message.reply_text(f"📢 Xabar {sent_count}/{len(users)} ta foydalanuvchiga yuborildi.")

def run_health_server():
    """Backward-compatible wrapper: FastAPI mini-app serverini ishga tushiradi."""
    web_api.run_api_server()


def keep_alive_ping():
    """Har 14 daqiqada FastAPI health endpoint ga ping yuboradi."""
    url = Config.SELF_URL
    if not url:
        return
    ping_url = url.rstrip("/") + "/healthz"
    # Birinchi ping uchun 14 daqiqa kutish
    time.sleep(14 * 60)
    while True:
        try:
            with urllib.request.urlopen(ping_url, timeout=10) as resp:
                logger.info(f"Keep-alive ping: {resp.status} OK")
        except Exception as e:
            logger.warning(f"Keep-alive ping xatolik: {e}")
        time.sleep(14 * 60)


def main():
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    # FastAPI mini-app serverini fon oqimida ishga tushirish
    threading.Thread(target=web_api.run_api_server, daemon=True).start()
    threading.Thread(target=keep_alive_ping, daemon=True).start()

    # Vaqtinchalik fayllarni tozalash
    cleanup_temp_files()

    telegram_app = ApplicationBuilder().token(Config.BOT_TOKEN).build()
    app = telegram_app

    # Sotib olish muloqoti (Conversation)
    buy_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_buy_process, pattern="^buy_"),
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_purchase),
        ],
        states={
            GET_PUBG_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_pubg_id)],
            GET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            CONFIRM_ORDER: [CallbackQueryHandler(process_confirm_order, pattern="^(edit_|confirm_checkout|cancel_buy)")],
        },
        fallbacks=[CommandHandler("cancel", cancel_process)],
        per_chat=True,
        per_message=False
    )

    # Mahsulot qo'shish muloqoti (Faqat admin uchun)
    add_product_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("➕ Mahsulot qo'shish"), add_product_start)],
        states={
            ADD_PR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_name)],
            ADD_PR_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_desc)],
            ADD_PR_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            ADD_PR_PHOTO: [MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, add_product_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel_process), MessageHandler(filters.Text("❌ Bekor qilish"), cancel_process)],
        per_chat=True,
        allow_reentry=True
    )

    # Musiqa qidirish muloqoti
    music_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text("🎵 Musiqa qidirish"), music_start)],
        states={
            SEARCH_MUSIC: [
                MessageHandler(
                    filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE,
                    shazam_handler.handle_shazam_request,
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, music_search.process_music_search),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_process),
            MessageHandler(filters.Text(["❌ Bekor", "bekor"]), cancel_process),
        ],
        allow_reentry=True,
    )

    async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.inline_query.query
        if not query:
            return

        results = await music_search.search_music(query)
        inline_results = []

        for res in results:
            cached = await db.get_cached_music(res['id'])
            if cached and cached[0]: # cached[0] - file_id
                # Agar keshda bo'lsa, audio faylni darhol yuborish
                inline_results.append(
                    InlineQueryResultCachedAudio(
                        id=res['id'],
                        audio_file_id=cached[0],
                        caption=f"🎵 {res['title']}"
                    )
                )
            else:
                # Agar keshda bo'lmasa, botga yo'naltirish
                inline_results.append(
                    InlineQueryResultArticle(
                        id=res['id'],
                        title=res['title'],
                        description=f"YouTube-dan yuklab olish uchun bosing",
                        input_message_content=InputTextMessageContent(
                            f"🎵 <b>{res['title']}</b>\n\nYuklab olish uchun botga o'ting: t.me/{context.bot.username}?start=dl_{res['id']}", # Deep link
                            parse_mode="HTML"
                        ),
                        thumb_url=f"https://img.youtube.com/vi/{res['id']}/default.jpg"
                    )
                )
        await update.inline_query.answer(inline_results, cache_time=300)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("developer", developer_info))
    app.add_handler(CommandHandler("trending", trending_command))
    app.add_handler(CommandHandler("movies", movie_handler.handle_movie_search))
    app.add_handler(CommandHandler("admin", admin_dashboard))
    app.add_handler(MessageHandler(filters.Text("👤 Profil va Bio"), show_bio))
    app.add_handler(MessageHandler(filters.Text("🎙 Shazam"), shazam_btn_handler))
    app.add_handler(MessageHandler(filters.Text("🔥 Trending"), trending_command))
    app.add_handler(CallbackQueryHandler(show_portfolio_inline, pattern="^view_portfolio$"))
    app.add_handler(CallbackQueryHandler(show_my_orders, pattern="^my_orders_list$"))
    app.add_handler(CallbackQueryHandler(show_bio, pattern="^back_to_bio$"))

    app.add_handler(MessageHandler(filters.Text("🔝 Top 10"), show_top_music))
    app.add_handler(MessageHandler(filters.Text("📦 Barcha Buyurtmalar"), view_all_orders_admin))
    app.add_handler(MessageHandler(filters.Text("📊 Statistika (Admin)"), admin_dashboard))
    app.add_handler(MessageHandler(filters.Entity("url"), music_downloader.handle_incoming_link))

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(music_conv)
    app.add_handler(add_product_conv)

    # Deezer callbacklari
    app.add_handler(CallbackQueryHandler(music_search.show_deezer_track_options, pattern="^dz_show_"))
    app.add_handler(CallbackQueryHandler(music_search.handle_deezer_download, pattern="^dz_(dl|vq)_"))
    app.add_handler(CallbackQueryHandler(music_search.handle_deezer_preview, pattern="^dz_prev_"))

    # Film callbacklari
    app.add_handler(CallbackQueryHandler(movie_handler.handle_movie_detail, pattern="^movie_"))

    app.add_handler(CallbackQueryHandler(show_marketplace, pattern="^market_page_"))
    app.add_handler(CallbackQueryHandler(view_product, pattern="^view_pr_"))
    app.add_handler(CallbackQueryHandler(music_downloader.show_music_options, pattern="^show_music_options_"))
    app.add_handler(CallbackQueryHandler(music_downloader.show_video_quality, pattern="^vq_"))
    app.add_handler(CallbackQueryHandler(music_downloader.handle_media_download, pattern="^(dl|vdl)_"))
    app.add_handler(CallbackQueryHandler(music_downloader.download_and_send_video_note, pattern="^vnote_")) # Yangi video note handler
    app.add_handler(CallbackQueryHandler(music_downloader.cancel_dl_callback, pattern="^cancel_dl$"))
    app.add_handler(CallbackQueryHandler(close_search_callback, pattern="^close_search$"))
    app.add_handler(CallbackQueryHandler(shazam_dl_callback, pattern="^shazam_dl$"))
    app.add_handler(CallbackQueryHandler(update_status_callback, pattern="^st_"))
    app.add_handler(CallbackQueryHandler(music_downloader.handle_direct_video_conversion, pattern="^convert_vn$"))

    app.add_handler(MessageHandler(
        filters.VOICE | filters.AUDIO | filters.VIDEO | filters.VIDEO_NOTE | filters.Document.MimeType("video/"),
        video_message_handler,
    ))
    app.add_handler(buy_conv)
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    app.add_handler(CommandHandler("ban", ban_user_command))
    app.add_handler(CommandHandler("unban", unban_user_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_error_handler(error_handler)

    logger.info("Bot ishga tushdi...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
