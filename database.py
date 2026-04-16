import psycopg2
from psycopg2 import pool
import asyncio
import logging
from config import Config

logger = logging.getLogger(__name__)

class Database:
    """PostgreSQL bilan ishlash uchun asinxron wrapper va DAO."""
    def __init__(self):
        try:
            self.connection_pool = psycopg2.pool.ThreadedConnectionPool(
                1, 10,
                dbname=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASS,
                host=Config.DB_HOST
            )
        except Exception as e:
            logger.error(f"DB ulanishda xatolik: {e}")
            raise

    def _execute(self, query, params=None, fetchone=False, fetchall=False, commit=False):
        conn = self.connection_pool.getconn()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                if commit:
                    conn.commit()
                if fetchone:
                    return cursor.fetchone()
                if fetchall:
                    return cursor.fetchall()
        finally:
            self.connection_pool.putconn(conn)

    async def run_async(self, query, params=None, **kwargs):
        """Blocking DB chaqiruvlarini asinxron bajarish."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute, query, params, 
                                        kwargs.get('fetchone', False),
                                        kwargs.get('fetchall', False),
                                        kwargs.get('commit', False))

    # Biznes metodlar
    async def add_user(self, tg_id, username, full_name):
        query = "INSERT INTO users (tg_id, username, full_name) VALUES (%s, %s, %s) ON CONFLICT (tg_id) DO NOTHING"
        await self.run_async(query, (tg_id, username, full_name), commit=True)

    async def is_banned(self, tg_id):
        res = await self.run_async("SELECT is_banned FROM users WHERE tg_id = %s", (tg_id,), fetchone=True)
        return res[0] if res else False

    async def is_admin_db(self, tg_id):
        res = await self.run_async("SELECT is_admin FROM users WHERE tg_id = %s", (tg_id,), fetchone=True)
        return res[0] if res else False

    async def get_products(self):
        return await self.run_async("SELECT * FROM products", fetchall=True)

    async def get_stats(self):
        count = await self.run_async("SELECT COUNT(*) FROM users", fetchone=True)
        growth = await self.run_async("SELECT DATE(joined_at), COUNT(*) FROM users GROUP BY DATE(joined_at)", fetchall=True)
        return count[0], growth

    async def get_products_paginated(self, limit, offset):
        """Mahsulotlarni sahifalangan holda olish."""
        query = "SELECT * FROM products ORDER BY id LIMIT %s OFFSET %s"
        return await self.run_async(query, (limit, offset), fetchall=True)

    async def get_products_count(self):
        """Mahsulotlarning umumiy sonini aniqlash."""
        query = "SELECT COUNT(*) FROM products"
        res = await self.run_async(query, fetchone=True)
        return res[0] if res else 0

    async def get_product_by_id(self, product_id):
        """ID bo'yicha bitta mahsulotni olish."""
        return await self.run_async("SELECT * FROM products WHERE id = %s", (product_id,), fetchone=True)

    async def ban_user(self, tg_id):
        await self.run_async("UPDATE users SET is_banned = TRUE WHERE tg_id = %s", (tg_id,), commit=True)

    async def unban_user(self, tg_id):
        await self.run_async("UPDATE users SET is_banned = FALSE WHERE tg_id = %s", (tg_id,), commit=True)

    async def get_all_users(self):
        return await self.run_async("SELECT tg_id FROM users", fetchall=True)

    async def add_order(self, user_id, product_id, amount, pubg_id, phone, status='paid'):
        query = "INSERT INTO orders (user_id, product_id, amount, pubg_id, phone, status) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id"
        res = await self.run_async(query, (user_id, product_id, amount, pubg_id, phone, status), commit=True, fetchone=True)
        return res[0] if res else None

    async def get_user_orders(self, user_id):
        """Foydalanuvchining buyurtmalar tarixini olish."""
        query = """
            SELECT p.name, o.created_at, o.amount, o.pubg_id, o.status
            FROM orders o
            JOIN products p ON o.product_id = p.id
            WHERE o.user_id = %s
            ORDER BY o.created_at DESC
        """
        return await self.run_async(query, (user_id,), fetchall=True)

    async def get_all_orders(self):
        """Barcha buyurtmalarni olish (Admin uchun)."""
        query = """
            SELECT o.id, u.full_name, p.name, o.pubg_id, o.phone, o.amount, o.status, o.created_at
            FROM orders o
            JOIN users u ON o.user_id = u.tg_id
            JOIN products p ON o.product_id = p.id
            ORDER BY o.created_at DESC
        """
        return await self.run_async(query, fetchall=True)

    async def update_order_status(self, order_id, status):
        """Buyurtma holatini yangilash."""
        await self.run_async("UPDATE orders SET status = %s WHERE id = %s", (status, order_id), commit=True)

    async def get_cached_music(self, video_id):
        """Keshdan musiqani qidirish."""
        return await self.run_async("SELECT file_id, title, performer FROM music_cache WHERE video_id = %s", (video_id,), fetchone=True)

    async def cache_music(self, video_id, file_id, title, performer):
        """Yangi musiqani keshga saqlash."""
        query = "INSERT INTO music_cache (video_id, file_id, title, performer, download_count) VALUES (%s, %s, %s, %s, 1) ON CONFLICT (video_id) DO NOTHING"
        await self.run_async(query, (video_id, file_id, title, performer), commit=True)

    async def increment_music_count(self, video_id):
        """Musiqa yuklanganda hisoblagichni oshirish."""
        query = "UPDATE music_cache SET download_count = download_count + 1 WHERE video_id = %s"
        await self.run_async(query, (video_id,), commit=True)

    async def get_top_music(self):
        """Eng ko'p yuklangan 10 ta musiqani olish."""
        query = """
            SELECT title, performer, download_count, video_id
            FROM music_cache
            ORDER BY download_count DESC
            LIMIT 10
        """
        return await self.run_async(query, fetchall=True)

    async def save_search_history(self, user_id, query_text):
        """Foydalanuvchi qidiruv so'rovini saqlash."""
        q = "INSERT INTO search_history (user_id, query) VALUES (%s, %s)"
        await self.run_async(q, (user_id, query_text), commit=True)

    async def get_recommendations(self, user_id):
        """Foydalanuvchining oxirgi 10 ta qidiruv tarixini olish."""
        q = """
            SELECT query FROM search_history
            WHERE user_id = %s
            ORDER BY search_date DESC
            LIMIT 10
        """
        return await self.run_async(q, (user_id,), fetchall=True)

db = Database()