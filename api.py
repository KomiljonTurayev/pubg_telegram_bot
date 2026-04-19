import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends, Body
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from database import db
from config import Config
import uvicorn

app = FastAPI(title="PUBG Marketplace API")

# CORS sozlamalari: TMA frontendi (React/Vue/HTML) boshqa domenda bo'lsa, 
# browser xavfsizlik to'sig'idan o'tish uchun zarur.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production bosqichida buni faqat frontend domeningizga cheklang
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def verify_telegram_data(init_data: str) -> dict | bool:
    """Telegram initData ning haqiqiyligini tekshirish."""
    if not init_data:
        return False
    
    try:
        vals = dict(parse_qsl(init_data))
        hash_val = vals.pop('hash', None)
        if not hash_val:
            return False

        # Kalitlarni alifbo tartibida saralash
        data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(vals.items()))
        
        # HMAC-SHA256 tekshiruvi
        secret_key = hmac.new(b"WebAppData", Config.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_val:
            # Ma'lumotlar to'g'ri bo'lsa, user ob'ektini qaytaramiz
            user_json = vals.get('user')
            if user_json:
                return json.loads(user_json)
            return True
        return False
    except Exception:
        return False

async def get_current_user(x_telegram_init_data: str = Header(None)):
    """Har bir so'rovni xavfsizlikka tekshirib, user ma'lumotlarini qaytaradi."""
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="InitData topilmadi")
    
    user_data = verify_telegram_data(x_telegram_init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Ruxsat berilmagan yoki ma'lumotlar noto'g'ri")
    
    return user_data

# JSON ko'rinishini belgilovchi Pydantic modeli
class ProductSchema(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    image_url: Optional[str]
    audio_url: Optional[str] = None  # Preview uchun audio link

class OrderCreate(BaseModel):
    product_id: int
    pubg_id: str
    phone: str

@app.get("/api/products", response_model=List[ProductSchema], dependencies=[Depends(get_current_user)])
async def get_products(auth=Depends(get_current_user)):
    """Barcha mahsulotlar ro'yxatini JSON formatida qaytaradi."""
    try:
        products_raw = await db.get_products()
        return [
            ProductSchema(
                id=p[0], 
                name=p[1], 
                description=p[2], 
                price=float(p[3]), 
                image_url=p[4],
                audio_url=p[5] if len(p) > 5 else None
            )
            for p in products_raw
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/products/{product_id}", response_model=ProductSchema, dependencies=[Depends(get_current_user)])
async def get_product(product_id: int, auth=Depends(get_current_user)):
    """Bitta mahsulot haqida ma'lumot qaytaradi."""
    p = await db.get_product_by_id(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return ProductSchema(id=p[0], name=p[1], description=p[2], price=float(p[3]), image_url=p[4])

@app.post("/api/orders", dependencies=[Depends(get_current_user)])
async def create_order(order: OrderCreate, user=Depends(get_current_user)):
    """Mini App'dan kelgan buyurtmani xavfsiz qabul qilish."""
    # 1. Mahsulotni tekshiramiz
    product = await db.get_product_by_id(order.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    # 2. User ID ni xavfsiz headerdan olamiz (Frontend yuborgan ID ga ishonmaymiz)
    tg_id = user.get('id')
    
    try:
        # 3. Buyurtmani bazaga saqlash
        order_id = await db.add_order(tg_id, order.product_id, product[3], order.pubg_id, order.phone, status='pending')
        return {"status": "success", "order_id": order_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Buyurtmani saqlashda xatolik")

@app.get("/market", response_class=HTMLResponse)
async def serve_market():
    """Butun ekranni egallaydigan Mini App interfeysi."""
    return """
    <!DOCTYPE html>
    <html lang="uz">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            :root {
                --bg-color: var(--tg-theme-bg-color, #ffffff);
                --text-color: var(--tg-theme-text-color, #222222);
                --hint-color: var(--tg-theme-hint-color, #999999);
                --button-color: var(--tg-theme-button-color, #2481cc);
                --button-text: var(--tg-theme-button-text-color, #ffffff);
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                margin: 0;
                padding: 0;
                display: flex;
                flex-direction: column;
                height: 100vh; /* Full screen height */
                overflow: hidden;
            }
            .header {
                padding: 20px;
                text-align: center;
                border-bottom: 1px solid var(--hint-color);
            }
            .content {
                flex: 1;
                padding: 15px;
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
            }
            .product-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                padding-bottom: 120px; /* Player uchun joy */
            }
            .card {
                background: var(--bg-color);
                border: 1px solid var(--hint-color);
                border-radius: 12px;
                padding: 10px;
                text-align: center;
                position: relative;
            }
            .play-icon {
                position: absolute;
                top: 10px;
                right: 10px;
                background: var(--button-color);
                color: white;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
            }
            .buy-btn {
                background-color: var(--button-color);
                color: var(--button-text);
                border: none;
                padding: 8px 15px;
                border-radius: 6px;
                width: 100%;
                margin-top: 10px;
            }
            .player-bar {
                position: fixed;
                bottom: 0;
                left: 0;
                width: 100%;
                background: var(--tg-theme-secondary-bg-color, #f0f0f0);
                padding: 10px;
                display: none;
                border-top: 1px solid var(--hint-color);
                box-sizing: border-box;
                z-index: 1000;
            }
            .player-controls {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 5px;
            }
            .ctrl-btn {
                background: var(--button-color);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 5px 10px;
                cursor: pointer;
            }
            .ctrl-btn.active {
                background: #ff9500; /* Shuffle yoqilganda rang o'zgarishi */
            }
            audio { display: none; } /* Default pleerni yashiramiz */
            img { width: 100%; border-radius: 8px; margin-bottom: 5px; }
            .seek-container {
                display: flex;
                align-items: center;
                gap: 10px;
                width: 100%;
                margin-top: 8px;
            }
            #seekBar {
                flex: 1;
                height: 5px;
                cursor: pointer;
                accent-color: var(--button-color);
            }
            .time-display {
                font-size: 10px;
                font-family: monospace;
                color: var(--hint-color);
                min-width: 35px;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <h3>PUBG Marketplace</h3>
        </div>
        <div class="content">
            <div id="app" class="product-grid"></div>
        </div>
        <script>
            const tg = window.Telegram.WebApp;
            tg.ready();
            tg.expand(); // BUTUN EKRANNI EGALLASH UCHUN ASOSIY BUYRUQ
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    # Portni Render yoki boshqa hosting muhitiga moslash
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)