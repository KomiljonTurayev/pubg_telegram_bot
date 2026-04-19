-- Foydalanuvchilar jadvali
CREATE TABLE IF NOT EXISTS users (
    tg_id BIGINT PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    is_admin BOOLEAN DEFAULT FALSE,
    is_banned BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Mahsulotlar jadvali
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    price DECIMAL(12, 2) NOT NULL,
    image_url TEXT
);

-- Buyurtmalar jadvali
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(tg_id),
    product_id INTEGER REFERENCES products(id),
    amount DECIMAL(12, 2),
    pubg_id TEXT,
    phone TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Musiqa kesh jadvali
CREATE TABLE IF NOT EXISTS music_cache (
    video_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    title TEXT,
    performer TEXT,
    download_count INTEGER DEFAULT 0
);

-- Qidiruv tarixi
CREATE TABLE IF NOT EXISTS search_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(tg_id),
    query TEXT,
    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Kunlik statistika (admin panel uchun)
CREATE TABLE IF NOT EXISTS daily_stats (
    stat_date DATE PRIMARY KEY DEFAULT CURRENT_DATE,
    active_users INTEGER DEFAULT 0,
    total_searches INTEGER DEFAULT 0,
    total_downloads INTEGER DEFAULT 0
);

-- Trending kesh (tez-tez o'zgarmaydigan ma'lumotlarni saqlash)
CREATE TABLE IF NOT EXISTS trending_cache (
    cache_key TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);