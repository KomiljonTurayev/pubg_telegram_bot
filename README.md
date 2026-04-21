# PUBG Marketplace & Music Downloader Bot

Ushbu Telegram bot orqali foydalanuvchilar PUBG mahsulotlarini sotib olishlari va YouTube orqali musiqa/videolarni yuklab olishlari mumkin.

## Imkoniyatlar

- **Marketplace:** PUBG skinlari va UC-larni sotib olish (Click/Payme integratsiyasi).
- **Music Downloader:** YouTube-dan MP3 va MP4 formatida yuklab olish.
- **Admin Panel:** Statistika, buyurtmalarni boshqarish va foydalanuvchilarni ban qilish.
- **Kesh tizimi:** Bir marta yuklangan musiqalar bazada saqlanadi va qayta yuklashda tezkor yuboriladi.

## O'rnatish

1. Loyihani klon qiling:
   ```bash
   git clone https://github.com/KomiljonTurayev/pubg_telegram_bot.git
   cd pubg_telegram_bot
   ```

2. Virtual muhit yarating va kutubxonalarni o'rnating:
   ```bash
   python -m venv venv
   source venv/bin/scripts/activate  # Windows uchun: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. `.env` faylini yarating va quyidagi o'zgaruvchilarni to'ldiring:
   ```env
   BOT_TOKEN=your_bot_token
   ADMIN_ID=your_id
   POSTGRES_DB=postgres
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=password
   POSTGRES_HOST=localhost
   PAYMENT_TOKEN=your_payment_provider_token
   SELF_URL=https://your-public-domain.uz
   ```

4. Botni ishga tushiring: `python bot.py`

`bot.py` endi Telegram polling bilan birga ichki FastAPI mini-app serverini ham ko'taradi. `SELF_URL` yoki Render'dagi `RENDER_EXTERNAL_URL` sozlangan bo'lsa, bot ichidagi `Marketplace` tugmasi `/market` mini-app sahifasini ochadi.
