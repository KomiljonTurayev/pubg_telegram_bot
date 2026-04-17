import logging
import os
import time
import warnings
import traceback
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
warnings.filterwarnings("ignore", message=".*per_message=False.*", category=Warning)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, ReplyKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultCachedAudio
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler, filters, ContextTypes, ConversationHandler, InlineQueryHandler
)
from telegram.error import Conflict, NetworkError, TimedOut
from config import Config
from database import db
from utils import admin_only, ban_check, create_stat_chart, generate_receipt_pdf, cleanup_temp_files
from music_menu import SEARCH_MUSIC
import music_search
import music_downloader

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
        ["👨‍💻 Portfolio", "🛒 Marketplace"],
        ["🛍 Buyurtmalarim", "🎵 Musiqa"],
        ["🔝 Top 10"],
    ]
    if is_admin:
        keyboard.append(["📊 Statistika (Admin)", "📦 Barcha Buyurtmalar"])
        keyboard.append(["➕ Mahsulot qo'shish"])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"👋 <b>Assalomu alaykum, {user.full_name}!</b>\n"
        f"<code>─────────────────────</code>\n"
        f"🎵  Musiqa yuklab olish\n"
        f"🛒  Raqamli mahsulotlar\n"
        f"👨‍💻  Dasturlash xizmatlari\n"
        f"<code>─────────────────────</code>\n"
        f"👇 <i>Kerakli bo'limni tanlang:</i>",
        reply_markup=reply_markup,
        parse_mode=PARSE_MODE
    )

@ban_check
async def show_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dasturchi xizmatlarini ko'rsatish."""
    text = (
        "🚀 <b>Mening Xizmatlarim:</b>\n\n"
        "• 🤖 <b>Telegram Botlar:</b> Murakkab va yuqori yuklamaga chidamli tizimlar.\n"
        "• 🌐 <b>Web Backend:</b> Django, FastAPI va Flask orqali xavfsiz API'lar.\n"
        "• 📊 <b>Ma'lumotlar bazasi:</b> PostgreSQL, MySQL va MongoDB loyihalari.\n\n"
        "📩 <b>Muloqot uchun:</b> @developer_username\n"
        "<i>Sifat va xavfsizlik — ustuvor vazifamiz!</i>"
    )
    await update.message.reply_text(text, parse_mode=PARSE_MODE)

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
    await update.message.reply_text(
        "🎵 <b>Musiqa qidiruvi</b>\n"
        "<code>─────────────────────</code>\n"
        "🔎 Qo'shiq nomi, ijrochi yoki YouTube havolasini yozing:\n\n"
        "  • <i>Sherali Jo'rayev - Karvon</i>\n"
        "  • <i>Dua Lipa - Levitating</i>\n"
        "  • <i>youtube.com/watch?v=...</i>\n\n"
        "❌ <i>Chiqish uchun «bekor» yozing</i>",
        parse_mode=PARSE_MODE
    )
    return SEARCH_MUSIC

async def process_music_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """YouTube qidiruv natijalarini ko'rsatish."""
    return await music_search.process_music_search(update, context)

async def start_buy_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sotib olish jarayonini boshlash (PUBG ID so'rash)."""
    query = update.callback_query
    product_id = int(query.data.split("_")[1])
    products = await db.get_products()
    product = next((p for p in products if p[0] == product_id), None)

    if not product:
        await query.answer("Mahsulot topilmadi.")
        return ConversationHandler.END

    context.user_data['buy_product_id'] = product_id
    context.user_data['buy_product_name'] = product[1]
    context.user_data['buy_product_price'] = product[3]
    context.user_data['is_editing'] = False
    
    await query.message.reply_text(
        "🆔 <b>PUBG ID raqamingizni kiriting:</b>\n"
        "(Masalan: 5123456789)",
        parse_mode=PARSE_MODE
    )
    await query.answer()
    return GET_PUBG_ID

@ban_check
async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchiga o'z buyurtmalarini ko'rsatish."""
    user_id = update.effective_user.id
    orders = await db.get_user_orders(user_id)
    
    if not orders:
        await update.message.reply_text("📭 Sizda hali buyurtmalar mavjud emas.", parse_mode=PARSE_MODE)
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
    
    await update.message.reply_text(text, parse_mode=PARSE_MODE)

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

async def cancel_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Jarayonni bekor qilish."""
    await update.message.reply_text("❌ Jarayon bekor qilindi.")
    return ConversationHandler.END

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Barcha xatolarni markazlashgan holda boshqarish."""
    error = context.error
    if isinstance(error, Conflict):
        logger.warning("⚠️ 409 Conflict: Boshqa bot instansiyasi ishlayapti. Qayta ulanilmoqda...")
        return
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning(f"Tarmoq xatoligi (avtomatik qayta uriniladi): {error}")
        return
    logger.error(f"Kutilmagan xatolik: {error}")
    logger.debug(traceback.format_exc())

@admin_only
async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uchun statistika grafigi bilan."""
    total_users, growth = await db.get_stats()
    chart_buf = create_stat_chart(growth)
    
    await update.message.reply_photo(
        photo=chart_buf,
        caption=f"📈 <b>Bot statistikasi:</b>\n\nJami foydalanuvchilar: <b>{total_users}</b>",
        parse_mode=PARSE_MODE
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
    """Render uchun minimal HTTP health-check serveri."""
    port = int(os.getenv("PORT", 10000))

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *args):
            pass  # HTTP loglarni o'chirish

    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def keep_alive_ping():
    """Har 14 daqiqada serverning o'ziga ping yuborib uxlab qolishini oldini oladi."""
    url = Config.SELF_URL
    if not url:
        return
    ping_url = url.rstrip("/") + "/"
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

    # Render uchun health-check serverni fon oqimida ishga tushirish
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=keep_alive_ping, daemon=True).start()

    # Vaqtinchalik fayllarni tozalash
    cleanup_temp_files()

    app = ApplicationBuilder().token(Config.BOT_TOKEN).build()

    # Sotib olish muloqoti (Conversation)
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_buy_process, pattern="^buy_")],
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
        entry_points=[MessageHandler(filters.Text("🎵 Musiqa"), music_start)],
        states={
            SEARCH_MUSIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, music_search.process_music_search)],
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
    app.add_handler(MessageHandler(filters.Text("👨‍💻 Portfolio"), show_portfolio))
    app.add_handler(MessageHandler(filters.Text("🛒 Marketplace"), show_marketplace))
    app.add_handler(MessageHandler(filters.Text("🛍 Buyurtmalarim"), show_my_orders))
    app.add_handler(MessageHandler(filters.Text("🔝 Top 10"), show_top_music))
    app.add_handler(MessageHandler(filters.Text("📦 Barcha Buyurtmalar"), view_all_orders_admin))
    app.add_handler(MessageHandler(filters.Text("📊 Statistika (Admin)"), admin_dashboard))
    app.add_handler(MessageHandler(filters.Entity("url"), music_downloader.handle_incoming_link))

    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(music_conv)
    app.add_handler(add_product_conv)
    app.add_handler(CallbackQueryHandler(show_marketplace, pattern="^market_page_"))
    app.add_handler(CallbackQueryHandler(view_product, pattern="^view_pr_"))
    app.add_handler(CallbackQueryHandler(music_downloader.show_music_options, pattern="^show_music_options_"))
    app.add_handler(CallbackQueryHandler(music_downloader.show_video_quality, pattern="^vq_"))
    app.add_handler(CallbackQueryHandler(music_downloader.handle_media_download, pattern="^(dl|vdl)_"))
    app.add_handler(CallbackQueryHandler(music_downloader.cancel_dl_callback, pattern="^cancel_dl$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.message.delete(), pattern="^close_search$"))
    app.add_handler(CallbackQueryHandler(update_status_callback, pattern="^st_"))
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