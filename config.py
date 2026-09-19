import os
import time
import telebot
from telebot import types
from flask import Flask
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

# ==================== الإعدادات ====================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))
ENV = os.environ.get('ENV', 'production')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
# تنظيف رابط Neon من خيار قد يسبب خطأ اتصال
DATABASE_URL = DATABASE_URL.replace('&channel_binding=require', '').replace('?channel_binding=require&', '?')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
PENDING = {}  # تخزين مؤقت لخطوات إضافة المنتج

# ==================== قاعدة البيانات (Neon) ====================
@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY, name TEXT NOT NULL,
                emoji TEXT DEFAULT '', sort_order INT DEFAULT 0)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY, name TEXT, price NUMERIC,
                description TEXT, photo_id TEXT, category_id INT)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS cart (
                user_id BIGINT, product_id INT, quantity INT,
                PRIMARY KEY (user_id, product_id))''')
            cur.execute('''CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT)''')
            cur.execute('SELECT COUNT(*) AS c FROM categories')
            if cur.fetchone()[0] == 0:
                for nm, em, so in [('حسابات ألعاب','🎮',1),('اشتراكات','📱',2),('برامج','💻',3)]:
                    cur.execute('INSERT INTO categories (name,emoji,sort_order) VALUES (%s,%s,%s)', (nm,em,so))
        print("✅ Database initialized on Neon")
    except Exception as e:
        print("❌ DB init error:", e)

def get_setting(key, default=''):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT value FROM settings WHERE key=%s', (key,))
            row = cur.fetchone()
            return row[0] if row else default
    except Exception as e:
        print('get_setting err', e)
        return default

def set_setting(key, value):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''INSERT INTO settings (key,value) VALUES (%s,%s)
                       ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value''', (key, str(value)))

def fmt_price(p):
    try:
        return f"{float(p):g}"
    except Exception:
        return str(p)

def is_admin(uid):
    return uid == ADMIN_ID
