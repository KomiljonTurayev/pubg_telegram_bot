CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    tg_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    full_name VARCHAR(255),
    is_admin BOOLEAN DEFAULT FALSE,
    is_banned BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(10, 2) NOT NULL,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(tg_id),
    product_id INTEGER REFERENCES products(id),
    pubg_id VARCHAR(50),
    phone VARCHAR(20),
    status VARCHAR(20) DEFAULT 'pending', -- pending, paid, cancelled
    amount DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Boshlang'ich mahsulotlar (Misol)
INSERT INTO products (name, description, price, image_url) VALUES 
('M416 Glacier', 'Level 1 basic skin', 50000.00, 'https://example.com/m416.jpg'),
('660 UC', 'Fast delivery pack', 120000.00, 'https://example.com/uc.jpg');

-- Musiqa keshini saqlash uchun jadval
CREATE TABLE IF NOT EXISTS music_cache (
    video_id VARCHAR(50) PRIMARY KEY,
    file_id TEXT NOT NULL,
    title TEXT,
    performer TEXT,
    download_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Qidiruv tarixini saqlash uchun jadval
CREATE TABLE IF NOT EXISTS search_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(tg_id),
    query TEXT NOT NULL,
    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);