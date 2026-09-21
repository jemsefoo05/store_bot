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
DATABASE_URL = DATABASE_URL.replace('&channel_binding=require', '').replace('?channel_binding=require&', '?')

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

PENDING = {}  # تخزين مؤقت لخطوات الإضافة/التعديل متعددة الخطوات


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
            cur.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, username TEXT, first_name TEXT,
                joined_at TIMESTAMP DEFAULT NOW())''')
            cur.execute('''CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY, user_id BIGINT, username TEXT,
                items_text TEXT, total NUMERIC, status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW())''')
            cur.execute('''CREATE TABLE IF NOT EXISTS topups (
                id SERIAL PRIMARY KEY, user_id BIGINT, method TEXT, amount NUMERIC,
                proof TEXT, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT NOW())''')
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance NUMERIC DEFAULT 0")

            cur.execute('SELECT COUNT(*) FROM categories')
            if cur.fetchone()[0] == 0:
                for nm, em, so in [('حسابات ألعاب', '🎮', 1), ('اشتراكات', '📱', 2), ('برامج', '💻', 3)]:
                    cur.execute('INSERT INTO categories (name,emoji,sort_order) VALUES (%s,%s,%s)', (nm, em, so))
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


# ==================== المشرفون ====================
def get_extra_admin_ids():
    raw = get_setting('extra_admins', '')
    out = []
    for part in raw.split(','):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def get_admin_ids():
    ids = {ADMIN_ID}
    ids.update(get_extra_admin_ids())
    return [i for i in ids if i]


def is_admin(uid):
    return uid in get_admin_ids()


def add_extra_admin(uid):
    ids = set(get_extra_admin_ids())
    ids.add(int(uid))
    set_setting('extra_admins', ','.join(str(i) for i in ids))


def remove_extra_admin(uid):
    ids = set(get_extra_admin_ids())
    ids.discard(int(uid))
    set_setting('extra_admins', ','.join(str(i) for i in ids))


# ==================== المستخدمون ====================
def add_user(uid, username, first_name):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('''INSERT INTO users (user_id, username, first_name) VALUES (%s,%s,%s)
                           ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name''',
                        (uid, username, first_name))
    except Exception as e:
        print('add_user err', e)


def get_all_user_ids():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT user_id FROM users')
            return [r[0] for r in cur.fetchall()]
    except Exception as e:
        print('get_all_user_ids err', e)
        return []


def count_users():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM users')
            return cur.fetchone()[0]
    except Exception:
        return 0


def get_user_info(uid):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT user_id, username, first_name, balance FROM users WHERE user_id=%s', (uid,))
            return cur.fetchone()
    except Exception:
        return None


# ==================== الطلبات ====================
def create_order(user_id, username, items_text, total):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''INSERT INTO orders (user_id, username, items_text, total, status)
                       VALUES (%s,%s,%s,%s,'pending') RETURNING id''', (user_id, username, items_text, total))
        return cur.fetchone()[0]


def get_order(order_id):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id,user_id,username,items_text,total,status FROM orders WHERE id=%s', (order_id,))
        return cur.fetchone()


def set_order_status(order_id, status):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE orders SET status=%s WHERE id=%s', (status, order_id))


def list_orders(status=None, limit=20):
    with get_conn() as conn:
        cur = conn.cursor()
        if status:
            cur.execute('''SELECT id,user_id,username,items_text,total,status FROM orders
                           WHERE status=%s ORDER BY id DESC LIMIT %s''', (status, limit))
        else:
            cur.execute('''SELECT id,user_id,username,items_text,total,status FROM orders
                           ORDER BY id DESC LIMIT %s''', (limit,))
        return cur.fetchall()


def list_orders_by_user(uid, limit=20):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT id,items_text,total,status FROM orders
                       WHERE user_id=%s ORDER BY id DESC LIMIT %s''', (uid, limit))
        return cur.fetchall()


def revenue_total():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status='paid'")
            return cur.fetchone()[0]
    except Exception:
        return 0


# ==================== الرصيد ====================
def get_balance(uid):
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT balance FROM users WHERE user_id=%s', (uid,))
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except Exception as e:
        print('get_balance err', e)
        return 0.0


def add_balance(uid, amount):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = COALESCE(balance,0) + %s WHERE user_id=%s', (amount, uid))


def deduct_balance(uid, amount):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = COALESCE(balance,0) - %s WHERE user_id=%s', (amount, uid))


# ==================== طلبات شحن الرصيد ====================
def create_topup(uid, method, amount, proof):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''INSERT INTO topups (user_id,method,amount,proof,status)
                       VALUES (%s,%s,%s,%s,'pending') RETURNING id''', (uid, method, amount, proof))
        return cur.fetchone()[0]


def get_topup(tid):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id,user_id,method,amount,proof,status FROM topups WHERE id=%s', (tid,))
        return cur.fetchone()


def set_topup_status(tid, status):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE topups SET status=%s WHERE id=%s', (status, tid))


def list_topups(status=None, limit=20):
    with get_conn() as conn:
        cur = conn.cursor()
        if status:
            cur.execute('''SELECT id,user_id,method,amount,proof,status FROM topups
                           WHERE status=%s ORDER BY id DESC LIMIT %s''', (status, limit))
        else:
            cur.execute('''SELECT id,user_id,method,amount,proof,status FROM topups
                           ORDER BY id DESC LIMIT %s''', (limit,))
        return cur.fetchall()


def topup_revenue_total():
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COALESCE(SUM(amount),0) FROM topups WHERE status='approved'")
            return cur.fetchone()[0]
    except Exception:
        return 0
