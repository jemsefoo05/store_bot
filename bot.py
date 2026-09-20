import os, time, traceback
from flask import request
from telebot import types as tb_types
from config import bot, app, ENV, BOT_TOKEN, init_db, get_conn
import user_handlers
import admin_categories
import admin_products

WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '').rstrip('/')

@app.route('/')
def home():
    return "Bot running on Neon via WEBHOOK 🤖"

@app.route('/health')
def health():
    return "OK", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    try:
        update = tb_types.Update.de_json(request.get_json(force=True))
        bot.process_new_updates([update])
    except Exception:
        print("❌ WEBHOOK HANDLER ERROR:\n" + traceback.format_exc())
    return "ok", 200

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
    return False

def setup_webhook():
    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL missing")
        return False
    for attempt in range(5):
        try:
            bot.set_webhook(url=f'{WEBHOOK_URL}/{BOT_TOKEN}')
            info = bot.get_webhook_info()
            if info.url:
                print(f"✅ Webhook active: {info.url}")
                return True
        except Exception as e:
            print(f"⚠️ set_webhook err: {e}")
        time.sleep(2)
    return False

if ENV == 'production' and BOT_TOKEN:
    init_db_safe()
    setup_webhook()
    print("🚀 production ready: flask + webhook (no polling, no 409)")

if __name__ == '__main__':
    init_db_safe()
    if ENV == 'development':
        bot.remove_webhook()
        bot.infinity_polling()
    else:
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
