import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
from database import db
from config import Config
import uvicorn

app = FastAPI(title="PUBG Marketplace API")

_raw_allowed_origins = os.getenv("WEBAPP_ALLOWED_ORIGINS", "").strip()
if _raw_allowed_origins:
    ALLOWED_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in _raw_allowed_origins.split(",")
        if origin.strip()
    ]
elif Config.SELF_URL:
    ALLOWED_ORIGINS = [Config.SELF_URL.rstrip("/")]
else:
    ALLOWED_ORIGINS = ["*"]

# CORS sozlamalari: TMA frontendi (React/Vue/HTML) boshqa domenda bo'lsa, 
# browser xavfsizlik to'sig'idan o'tish uchun zarur.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOWED_ORIGINS != ["*"],
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


MARKET_HTML = """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover"
    >
    <title>PUBG Marketplace</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: var(--tg-theme-bg-color, #f5efe4);
            --surface-color: var(--tg-theme-secondary-bg-color, rgba(255, 255, 255, 0.92));
            --text-color: var(--tg-theme-text-color, #1a1d17);
            --hint-color: var(--tg-theme-hint-color, #6e7667);
            --button-color: var(--tg-theme-button-color, #2d8f59);
            --button-text: var(--tg-theme-button-text-color, #ffffff);
            --line-color: rgba(41, 54, 35, 0.12);
            --shadow: 0 18px 40px rgba(22, 33, 17, 0.12);
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            color: var(--text-color);
            background:
                radial-gradient(circle at top left, rgba(255, 255, 255, 0.85), transparent 32%),
                linear-gradient(180deg, #f8f2e8 0%, var(--bg-color) 100%);
        }

        .shell {
            max-width: 960px;
            margin: 0 auto;
            padding: 20px 16px 28px;
        }

        .hero {
            padding: 22px 18px;
            border-radius: 24px;
            background:
                linear-gradient(135deg, rgba(34, 48, 28, 0.96), rgba(53, 91, 55, 0.92)),
                #22301c;
            color: #f5f7ef;
            box-shadow: var(--shadow);
        }

        .hero h1 {
            margin: 0 0 8px;
            font-size: 28px;
            line-height: 1.1;
        }

        .hero p {
            margin: 0;
            color: rgba(245, 247, 239, 0.82);
            font-size: 14px;
            line-height: 1.5;
        }

        .state {
            margin: 18px 0 10px;
            padding: 14px 16px;
            border-radius: 18px;
            background: var(--surface-color);
            border: 1px solid var(--line-color);
            color: var(--hint-color);
            box-shadow: 0 10px 24px rgba(22, 33, 17, 0.05);
        }

        .state.error {
            color: #a2362b;
            border-color: rgba(162, 54, 43, 0.18);
            background: rgba(255, 247, 245, 0.94);
        }

        .grid {
            display: grid;
            gap: 14px;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            margin-top: 16px;
        }

        .card {
            overflow: hidden;
            border-radius: 22px;
            border: 1px solid var(--line-color);
            background: var(--surface-color);
            box-shadow: 0 14px 36px rgba(22, 33, 17, 0.08);
        }

        .cover,
        .placeholder {
            width: 100%;
            aspect-ratio: 4 / 3;
            display: flex;
            align-items: center;
            justify-content: center;
            background:
                radial-gradient(circle at top, rgba(255, 255, 255, 0.26), transparent 30%),
                linear-gradient(135deg, #253426, #5f7d4d);
        }

        .cover {
            object-fit: cover;
        }

        .placeholder {
            font-size: 46px;
            font-weight: 700;
            color: rgba(255, 255, 255, 0.82);
        }

        .content {
            padding: 16px;
        }

        .title {
            margin: 0 0 8px;
            font-size: 18px;
            line-height: 1.25;
        }

        .description {
            min-height: 42px;
            margin: 0 0 14px;
            color: var(--hint-color);
            font-size: 13px;
            line-height: 1.5;
        }

        .meta {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }

        .price {
            font-size: 18px;
            font-weight: 700;
            color: #204f38;
        }

        .buy-btn {
            border: none;
            border-radius: 999px;
            padding: 11px 14px;
            background: var(--button-color);
            color: var(--button-text);
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
        }

        .buy-btn:active {
            transform: scale(0.98);
        }

        .footer-note {
            margin-top: 18px;
            color: var(--hint-color);
            font-size: 12px;
            text-align: center;
        }

        @media (max-width: 640px) {
            .shell {
                padding: 14px 12px 24px;
            }

            .hero h1 {
                font-size: 24px;
            }

            .grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <main class="shell">
        <section class="hero">
            <h1>PUBG Marketplace</h1>
            <p>Mahsulotni tanlang. Tanlovingiz botga yuboriladi va to'lovni chat ichida xavfsiz davom ettirasiz.</p>
        </section>

        <section id="state" class="state">Mahsulotlar yuklanmoqda...</section>
        <section id="app" class="grid" hidden></section>
        <p class="footer-note">Mini App Telegram ichida ochilganda mahsulotlar avtomatik yuklanadi.</p>
    </main>

    <script>
        const tg = window.Telegram?.WebApp;
        const stateEl = document.getElementById("state");
        const appEl = document.getElementById("app");

        if (tg) {
            tg.ready();
            tg.expand();
        }

        function escapeHtml(value) {
            return String(value ?? "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#39;");
        }

        function formatPrice(value) {
            const amount = Number(value || 0);
            return `${new Intl.NumberFormat("uz-UZ").format(amount)} UZS`;
        }

        function canRenderImage(url) {
            return typeof url === "string" && /^https?:\\/\\//i.test(url);
        }

        function showState(message, isError = false) {
            stateEl.hidden = false;
            stateEl.classList.toggle("error", isError);
            stateEl.textContent = message;
        }

        function renderProducts(products) {
            if (!Array.isArray(products) || products.length === 0) {
                appEl.hidden = true;
                showState("Hozircha marketplace bo'sh. Keyinroq yana urinib ko'ring.");
                return;
            }

            appEl.innerHTML = products.map((product) => {
                const imageBlock = canRenderImage(product.image_url)
                    ? `<img class="cover" src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}">`
                    : `<div class="placeholder">${escapeHtml((product.name || "P").slice(0, 1).toUpperCase())}</div>`;

                return `
                    <article class="card">
                        ${imageBlock}
                        <div class="content">
                            <h2 class="title">${escapeHtml(product.name)}</h2>
                            <p class="description">${escapeHtml(product.description || "Mahsulot tafsilotlari bot ichida ko'rsatiladi.")}</p>
                            <div class="meta">
                                <span class="price">${formatPrice(product.price)}</span>
                                <button class="buy-btn" type="button" data-product-id="${product.id}">
                                    Botda sotib olish
                                </button>
                            </div>
                        </div>
                    </article>
                `;
            }).join("");

            stateEl.hidden = true;
            appEl.hidden = false;
        }

        async function loadProducts() {
            try {
                const headers = {};
                if (tg?.initData) {
                    headers["X-Telegram-Init-Data"] = tg.initData;
                }

                const response = await fetch("/api/products", { headers });
                if (!response.ok) {
                    if (response.status === 401) {
                        throw new Error("Mini App faqat Telegram ichida ochilganda ishlaydi.");
                    }
                    throw new Error("Mahsulotlarni yuklab bo'lmadi. Keyinroq qayta urinib ko'ring.");
                }

                const products = await response.json();
                renderProducts(products);
            } catch (error) {
                showState(error.message || "Marketplace yuklanmadi.", true);
            }
        }

        appEl.addEventListener("click", (event) => {
            const button = event.target.closest("[data-product-id]");
            if (!button) {
                return;
            }

            if (!tg) {
                showState("Telegram WebApp obyektini topib bo'lmadi.", true);
                return;
            }

            tg.sendData(JSON.stringify({
                type: "buy_product",
                product_id: Number(button.dataset.productId),
            }));
            tg.close();
        });

        loadProducts();
    </script>
</body>
</html>
"""

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


@app.get("/healthz")
async def healthcheck():
    """Bot bilan birga ko'tariladigan HTTP health endpoint."""
    return {"status": "ok"}

@app.get("/market", response_class=HTMLResponse)
async def serve_market():
    """Butun ekranni egallaydigan Mini App interfeysi."""
    return MARKET_HTML


def run_api_server():
    """FastAPI serverini bot bilan bir jarayonda fon oqimida ishga tushirish."""
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

if __name__ == "__main__":
    run_api_server()
