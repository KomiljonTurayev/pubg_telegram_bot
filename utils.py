from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import matplotlib.pyplot as plt
import io
import os
import datetime
import tempfile
import shutil
from database import db
from config import Config
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def admin_only(func):
    """Faqat admin ruxsatini tekshiruvchi dekorator (xabar va callback uchun)."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != Config.ADMIN_ID and not await db.is_admin_db(user_id):
            msg = update.effective_message
            if msg:
                await msg.reply_text("❌ Bu buyruq faqat adminlar uchun!")
            if update.callback_query:
                await update.callback_query.answer("❌ Faqat adminlar uchun!", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def ban_check(func):
    """Foydalanuvchi banlanganligini tekshiruvchi dekorator (xabar va callback uchun)."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if await db.is_banned(user_id):
            if update.callback_query:
                await update.callback_query.answer("🚫 Siz botdan chetlatilgansiz.", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text("🚫 Siz botdan foydalanishdan chetlatilgansiz.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def create_stat_chart(growth_data):
    """Matplotlib orqali foydalanuvchilar o'sishi grafigini chizish."""
    dates = [str(d[0]) for d in growth_data]
    counts = [d[1] for d in growth_data]
    
    plt.figure(figsize=(8, 4))
    plt.plot(dates, counts, marker='o')
    plt.title("Foydalanuvchilar o'sishi")
    plt.xlabel("Sana")
    plt.ylabel("Soni")
    plt.xticks(rotation=45)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

def generate_receipt_pdf(order_id, full_name, product_name, amount, pubg_id, phone):
    """To'lov kvitansiyasini PDF shaklida generatsiya qilish."""
    filename = os.path.join(tempfile.gettempdir(), f"receipt_{order_id}.pdf")
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    c.setFont("Helvetica-Bold", 20)
    c.drawString(100, height - 100, "TO'LOV KVITANSIYASI (RECEIPT)")
    
    c.setFont("Helvetica", 12)
    c.drawString(100, height - 140, f"Buyurtma ID: {order_id}")
    c.drawString(100, height - 160, f"Sana: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(100, height - 180, f"Mijoz: {full_name}")
    c.drawString(100, height - 200, f"Mahsulot: {product_name}")
    c.drawString(100, height - 220, f"PUBG ID: {pubg_id}")
    c.drawString(100, height - 240, f"Telefon: {phone}")
    c.drawString(100, height - 260, f"To'langan summa: {amount:,.2f} UZS")
    
    c.line(100, height - 280, 500, height - 280)
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(100, height - 300, "Bot orqali xarid qilganingiz uchun rahmat!")
    c.drawString(100, height - 315, "Sifat va xavfsizlik — ustuvor vazifamiz!")
    
    c.showPage()
    c.save()
    return filename

def cleanup_temp_files():
    """Bot ishga tushganda vaqtinchalik fayllarni tozalash."""
    tmp_folder = os.path.join(tempfile.gettempdir(), "botdl")
    if os.path.exists(tmp_folder):
        shutil.rmtree(tmp_folder)
    os.makedirs(tmp_folder)

    # /tmp/ da qolgan receipt PDF larni o'chirish
    tmp = tempfile.gettempdir()
    if os.path.exists(tmp):
        for f in os.listdir(tmp):
            if f.startswith("receipt_") and f.endswith(".pdf"):
                try:
                    os.remove(os.path.join(tmp, f))
                except OSError:
                    pass