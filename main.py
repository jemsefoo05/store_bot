import os, time, threading
from config import bot, app, ENV, BOT_TOKEN, init_db, get_conn

# استيراد الملفات الفرعية = تسجيل كل معالجات الزبون والأدمن
import user_handlers
import admin_categories
import admin_products

# ---------- صفحات Flask (صحة + إبقاء حي) ----------
@app.route('/')
def home():
    return "Bot running on Neon via POLLING 🤖"

@app.route('/health')
def health():
    return "OK", 200

# ---------- حذف webhook بأمان (يمنع خطأ 409 نهائياً) ----------
def ensure_no_webhook():
    for attempt in range(5):
        try:
            bot.remove_webhook()
            if not bot.get_webhook_info().url:
                print("✅ Webhook fully removed")
                return True
            print(f"⚠️ webhook still set, retry {attempt+1}")
        except Exception as e:
            print(f"⚠️ remove_webhook err: {e}")
        time.sleep(2)
    print("❌ could not remove webhook")
    return False

# ---------- تهيئة قاعدة Neon مع إعادة محاولة ----------
def init_db_safe():
    for attempt in range(4):
        try:
            init_db()
            with get_conn() as conn:
                conn.cursor().execute('SELECT 1 FROM categories LIMIT 1')
            print("✅ DB ready on Neon")
            return True
        except Exception as e:
            print(f"⚠️ DB not ready (try {attempt+1}): {e}")
            time.sleep(3)
    print("❌ DB failed after retries")
    return False

# ---------- خيط السحب (Polling) ----------
def run_polling():
    try:
        print("🔄 polling thread started")
        bot.polling(none_stop=True, interval=0, timeout=60)
    except Exception as e:
        print("❌ polling error:", e)

# ---------- وضع الإنتاج (تحت gunicorn على Render) ----------
if ENV == 'production' and BOT_TOKEN:
    ensure_no_webhook()
    init_db_safe()
    threading.Thread(target=run_polling, daemon=True).start()
    print("🚀 production ready: flask + polling")

# ---------- وضع التطوير المحلي ----------
if __name__ == '__main__':
    init_db_safe()
    if ENV == 'development':
        ensure_no_webhook()
        bot.infinity_polling()
    else:
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
