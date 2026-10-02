import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    """إنشاء اتصال آمن مع قاعدة بيانات Neon"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    """إنشاء وتحديث الجداول تلقائياً في Neon عند تشغيل البوت لأول مرة"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                -- 1. جدول المستخدمين والعملاء
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(100),
                    first_name VARCHAR(150),
                    balance NUMERIC(10, 2) DEFAULT 0.00,
                    referred_by BIGINT,
                    referral_earnings NUMERIC(10, 2) DEFAULT 0.00,
                    has_purchased BOOLEAN DEFAULT FALSE,
                    last_bonus_at TIMESTAMP DEFAULT NULL,
                    language VARCHAR(10) DEFAULT 'ar',
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 2. جدول المنتجات مع مستويات تسعير الجملة
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    code_name VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(150) NOT NULL,
                    product_type VARCHAR(20) DEFAULT 'CODE',
                    price_usd NUMERIC(10, 2) NOT NULL,
                    bulk_price_20 NUMERIC(10, 2) DEFAULT NULL,
                    bulk_price_50 NUMERIC(10, 2) DEFAULT NULL,
                    description TEXT
                );

                -- 3. جدول مخزون الأكواد والحسابات
                CREATE TABLE IF NOT EXISTS product_items (
                    id SERIAL PRIMARY KEY,
                    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
                    item_data TEXT NOT NULL,
                    is_sold BOOLEAN DEFAULT FALSE,
                    sold_to BIGINT,
                    order_id INTEGER,
                    sold_at TIMESTAMP
                );

                -- 4. جدول الطلبات والمبيعات
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    product_id INTEGER REFERENCES products(id),
                    quantity INTEGER DEFAULT 1,
                    total_price NUMERIC(10, 2) NOT NULL,
                    status VARCHAR(20) DEFAULT 'APPROVED',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 5. جدول تنبيهات توفر المخزون
                CREATE TABLE IF NOT EXISTS stock_alerts (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, product_id)
                );
            """)
            conn.commit()
            print("✅ تم فحص وتجهيز جداول Neon تلقائياً بنجاح!")
    finally:
        conn.close()

# --- إحصائيات النشاط الحي (Social Proof) ---
def get_live_ticker_stats():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(id) AS sales_today,
                    COUNT(DISTINCT user_id) AS active_buyers
                FROM orders 
                WHERE status = 'APPROVED' AND created_at >= NOW() - INTERVAL '24 hours';
            """)
            row = cur.fetchone()
            return {
                "sales_today": row["sales_today"] if row else 0,
                "active_buyers": row["active_buyers"] if row else 0
            }
    finally:
        conn.close()

# --- إدارة العملاء والإحالة ---
def register_or_get_user(user_id: int, username: str, first_name: str, referrer_id: int = None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s;", (user_id,))
            user = cur.fetchone()
            if not user:
                valid_referrer = None
                if referrer_id and referrer_id != user_id:
                    cur.execute("SELECT user_id FROM users WHERE user_id = %s;", (referrer_id,))
                    if cur.fetchone():
                        valid_referrer = referrer_id

                cur.execute("""
                    INSERT INTO users (user_id, username, first_name, referred_by)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *;
                """, (user_id, username, first_name, valid_referrer))
                user = cur.fetchone()
                conn.commit()
            return user
    finally:
        conn.close()

def get_user_balance(user_id: int) -> float:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE user_id = %s;", (user_id,))
            row = cur.fetchone()
            return float(row["balance"]) if row else 0.00
    finally:
        conn.close()

def add_user_balance(user_id: int, amount: float):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET balance = balance + %s WHERE user_id = %s;", (amount, user_id))
            conn.commit()
            return True
    finally:
        conn.close()

def claim_daily_bonus(user_id: int, bonus_amount: float = 0.01):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET balance = balance + %s, last_bonus_at = NOW()
                WHERE user_id = %s 
                  AND (last_bonus_at IS NULL OR last_bonus_at < NOW() - INTERVAL '24 hours')
                RETURNING balance;
            """, (bonus_amount, user_id))
            updated = cur.fetchone()
            conn.commit()
            if updated:
                return {"success": True, "new_balance": float(updated["balance"])}
            return {"success": False, "msg": "لقد استلمت هديتك اليومية بالفعل! عد بعد 24 ساعة."}
    finally:
        conn.close()

def get_referral_stats(user_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(user_id) AS total_referred,
                    COALESCE(SUM(referral_earnings), 0.00) AS total_earnings
                FROM users 
                WHERE referred_by = %s;
            """, (user_id,))
            return cur.fetchone()
    finally:
        conn.close()

# --- إدارة المنتجات والأسعار ---
def get_all_products_with_stock():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.code_name, p.name, p.product_type, p.price_usd, p.description,
                       COUNT(i.id) FILTER (WHERE i.is_sold = FALSE) AS stock
                FROM products p
                LEFT JOIN product_items i ON p.id = i.product_id
                GROUP BY p.id
                ORDER BY p.id ASC;
            """)
            return cur.fetchall()
    finally:
        conn.close()

def get_product_by_id(prod_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.code_name, p.name, p.product_type, p.price_usd, p.bulk_price_20, p.bulk_price_50, p.description,
                       COUNT(i.id) FILTER (WHERE i.is_sold = FALSE) AS stock
                FROM products p
                LEFT JOIN product_items i ON p.id = i.product_id
                WHERE p.id = %s
                GROUP BY p.id;
            """, (prod_id,))
            return cur.fetchone()
    finally:
        conn.close()

def calculate_unit_price(product: dict, quantity: int) -> float:
    base_price = float(product["price_usd"])
    bulk_20 = float(product["bulk_price_20"]) if product.get("bulk_price_20") else base_price
    bulk_50 = float(product["bulk_price_50"]) if product.get("bulk_price_50") else bulk_20

    if quantity >= 50 and product.get("bulk_price_50"):
        return bulk_50
    elif quantity >= 20 and product.get("bulk_price_20"):
        return bulk_20
    return base_price

# --- تنفيذ عملية الشراء الذري والتسليم الفوري ---
def purchase_from_balance(user_id: int, product_id: int, quantity: int, commission_per_referral: float = 0.05):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id = %s;", (product_id,))
            product = cur.fetchone()
            if not product:
                return {"success": False, "error": "المنتج غير موجود."}

            unit_price = calculate_unit_price(product, quantity)
            total_cost = unit_price * quantity

            cur.execute("SELECT balance, referred_by, has_purchased FROM users WHERE user_id = %s FOR UPDATE;", (user_id,))
            user = cur.fetchone()
            if not user or float(user["balance"]) < total_cost:
                return {"success": False, "error": "رصيدك غير كافٍ لإتمام العملية!"}

            cur.execute("""
                SELECT id, item_data 
                FROM product_items 
                WHERE product_id = %s AND is_sold = FALSE 
                LIMIT %s 
                FOR UPDATE SKIP LOCKED;
            """, (product_id, quantity))
            items = cur.fetchall()

            if len(items) < quantity:
                return {"success": False, "error": "المخزون المتوفر أقل من الكمية المطلوبة."}

            cur.execute("UPDATE users SET balance = balance - %s WHERE user_id = %s;", (total_cost, user_id))

            # تسجيل الطلب أولاً لربطه بالأكواد المسلمة
            cur.execute("""
                INSERT INTO orders (user_id, product_id, quantity, total_price, status)
                VALUES (%s, %s, %s, %s, 'APPROVED')
                RETURNING id;
            """, (user_id, product_id, quantity, total_cost))
            order_id = cur.fetchone()["id"]

            item_ids = [item["id"] for item in items]
            cur.execute("""
                UPDATE product_items 
                SET is_sold = TRUE, sold_to = %s, order_id = %s, sold_at = NOW() 
                WHERE id = ANY(%s);
            """, (user_id, order_id, item_ids))

            referrer_id = user["referred_by"]
            if referrer_id and not user["has_purchased"]:
                cur.execute("""
                    UPDATE users 
                    SET balance = balance + %s, referral_earnings = referral_earnings + %s 
                    WHERE user_id = %s;
                """, (commission_per_referral, commission_per_referral, referrer_id))
                cur.execute("UPDATE users SET has_purchased = TRUE WHERE user_id = %s;", (user_id,))

            conn.commit()
            return {
                "success": True,
                "order_id": order_id,
                "items": [i["item_data"] for i in items],
                "product_name": product["name"],
                "product_type": product["product_type"],
                "total_cost": total_cost,
                "referrer_id": referrer_id if (referrer_id and not user["has_purchased"]) else None
            }
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

# --- طلباتي وتاريخ المشتريات ---
def get_user_orders(user_id: int):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT o.id, p.name, o.quantity, o.total_price, o.created_at,
                       ARRAY_AGG(i.item_data) AS delivered_items
                FROM orders o
                JOIN products p ON o.product_id = p.id
                LEFT JOIN product_items i ON o.id = i.order_id
                WHERE o.user_id = %s AND o.status = 'APPROVED'
                GROUP BY o.id, p.name, o.quantity, o.total_price, o.created_at
                ORDER BY o.created_at DESC
                LIMIT 10;
            """, (user_id,))
            return cur.fetchall()
    finally:
        conn.close()

# --- تنبيهات توفر المخزون وإضافة الأكواد ---
def add_stock_alert(user_id: int, product_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO stock_alerts (user_id, product_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, product_id) DO NOTHING
                RETURNING id;
            """, (user_id, product_id))
            res = cur.fetchone()
            conn.commit()
            return res is not None
    finally:
        conn.close()

def get_and_clear_alert_users(product_id: int) -> list:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM stock_alerts WHERE product_id = %s;", (product_id,))
            users = [r["user_id"] for r in cur.fetchall()]
            cur.execute("DELETE FROM stock_alerts WHERE product_id = %s;", (product_id,))
            conn.commit()
            return users
    finally:
        conn.close()

def bulk_insert_stock(code_name: str, items: list) -> int:
    clean_items = [i.strip() for i in items if i.strip()]
    if not clean_items:
        return 0
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM products WHERE code_name = %s;", (code_name,))
            product = cur.fetchone()
            if not product:
                return -1
            records = [(product["id"], item) for item in clean_items]
            cur.executemany("INSERT INTO product_items (product_id, item_data) VALUES (%s, %s);", records)
            conn.commit()
            return len(records)
    except Exception:
        conn.rollback()
        return 0
    finally:
        conn.close()

# --- إدارة المنتجات من أوامر الأدمن ---
def create_product(code_name: str, name: str, price_usd: float, bulk_20: float = None, bulk_50: float = None, description: str = "") -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO products (code_name, name, price_usd, bulk_price_20, bulk_price_50, description)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (code_name) DO NOTHING
                RETURNING id;
            """, (code_name.strip(), name.strip(), price_usd, bulk_20, bulk_50, description.strip()))
            res = cur.fetchone()
            conn.commit()
            return res is not None
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_product(code_name: str) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE code_name = %s RETURNING id;", (code_name.strip(),))
            res = cur.fetchone()
            conn.commit()
            return res is not None
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()
        
