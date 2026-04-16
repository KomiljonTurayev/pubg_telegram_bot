from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import matplotlib.pyplot as plt
import io
import os
import datetime
import shutil
from database import db
from config import Config
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def admin_only(func):
    """Faqat admin ruxsatini tekshiruvchi dekorator."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != Config.ADMIN_ID and not await db.is_admin_db(user_id):
            await update.message.reply_text("❌ Bu buyruq faqat adminlar uchun!")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def ban_check(func):
    """Foydalanuvchi banlanganligini tekshiruvchi dekorator."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if await db.is_banned(user_id):
            await update.message.reply_text("🚫 Siz botdan foydalanishdan chetlatilgansiz.")
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
    filename = f"receipt_{order_id}.pdf"
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
    """Bot ishga tushganda downloads papkasini va qolgan PDF-larni tozalash."""
    folders = ['downloads']
    for folder in folders:
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder)
    
    for file in os.listdir('.'):
        if file.startswith("receipt_") and file.endswith(".pdf"):
            os.remove(file)