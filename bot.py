import os
import telebot
from telebot import types
from flask import Flask, request
import sqlite3
import threading

# ==================== الإعدادات ====================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '123456789'))
ENV = os.environ.get('ENV', 'production')

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== قاعدة البيانات ====================
conn = sqlite3.connect('store.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS products
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL,
                   description TEXT, photo_id TEXT, category TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS cart
                  (user_id INTEGER, product_id INTEGER, quantity INTEGER,
                  PRIMARY KEY (user_id, product_id))''')
conn.commit()

# ==================== أوامر المستخدم ====================
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton('📂 الأقسام'),
        types.KeyboardButton('🛒 السلة'),
        types.KeyboardButton('📞 الدعم')
    )
    bot.send_message(message.chat.id,
                     f"أهلاُ بك {message.from_user.first_name} في المتجر! 🎉\nاختر من القائمة:",
                     reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📂 الأقسام')
def show_categories(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎮 حسابات ألعاب", callback_data="cat_games"),
        types.InlineKeyboardButton("📱 اشتراكات", callback_data="cat_subs"),
        types.InlineKeyboardButton("💻 برامج", callback_data="cat_soft")
    )
    bot.send_message(message.chat.id, "📂 اختر القسم:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
def show_products(call):
    category = call.data.split('_')[1]
    cursor.execute("SELECT * FROM products WHERE category = ?", (category,))
    products = cursor.fetchall()
    if not products:
        bot.answer_callback_query(call.id, "لا توجد منتجات في هذا القسم")
        return bot.send_message(call.message.chat.id, "⚠️ لا توجد منتجات حالياً في هذا القسم.")
    for p in products:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ إضافة للسلة", callback_data=f"add_{p[0]}"))
        caption = f"*{p[1]}*\n💰 السعر: {p[2]}$\n📝 {p[3]}"
        if p[4]:
            bot.send_photo(call.message.chat.id, p[4], caption=caption, parse_mode='Markdown', reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_'))
def add_to_cart(call):
    prod_id = int(call.data.split('_')[1])
    user_id = call.message.chat.id
    cursor.execute("""INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, 1)
        ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + 1""", (user_id, prod_id))
    conn.commit()
    bot.answer_callback_query(call.id, "✅ تمت الإضافة!")

@bot.message_handler(func=lambda m: m.text == '🛒 السلة')
def show_cart(message):
    cursor.execute("""SELECT p.name, p.price, c.quantity FROM cart c
        JOIN products p ON c.product_id = p.id WHERE c.user_id = ?""", (message.chat.id,))
    items = cursor.fetchall()
    if not items:
        return bot.send_message(message.chat.id, "🛒 السلة فارغة.")
    text = "🛒 *محتويات السلة:*\n\n"
    total = 0
    for item in items:
        item_total = item[1] * item[2]
        text += f"▪️ {item[0]} | {item[2]}x = {item_total}$\n"
        total += item_total
    text += f"\n💵 *الإجمالي: {total}$*"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ إتمام الشراء", callback_data="checkout"),
        types.InlineKeyboardButton("🗑 تفريغ", callback_data="clear_cart")
    )
    bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'clear_cart')
def clear_cart(call):
    cursor.execute("DELETE FROM cart WHERE user_id = ?", (call.message.chat.id,))
    conn.commit()
    bot.answer_callback_query(call.id, "🗑 تم التفريغ.")
    bot.edit_message_text("🛒 السلة فارغة الآن.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'checkout')
def checkout(call):
    user_id = call.message.chat.id
    cursor.execute("""SELECT p.name, p.price, c.quantity FROM cart c
        JOIN products p ON c.product_id = p.id WHERE c.user_id = ?""", (user_id,))
    items = cursor.fetchall()
    total = sum(i[1] * i[2] for i in items)
    order_text = f"🔔 *طلب جديد!*\n\n👤 العميل: [{call.message.chat.first_name}](tg://user?id={user_id})\n"
    order_text += f"🆔 ID: `{user_id}`\n\n📦 *المنتجات:*\n"
    for i in items:
        order_text += f"- {i[0]} ({i[2]}x) = {i[1]*i[2]}$\n"
    order_text += f"\n💰 *الإجمالي: {total}$*"
    bot.send_message(ADMIN_ID, order_text, parse_mode='Markdown')
    cursor.execute("DELETE FROM cart WHERE user_id = ?", (user_id,))
    conn.commit()
    bot.edit_message_text("✅ تم إرسال طلبك! سيتواصل معك المشرف.", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text == '📞 الدعم')
def support(message):
    bot.send_message(message.chat.id, "📞 للتواصل مع الدعم، أرسل رسالتك هنا.")

# ==================== أوامر المشرف ====================
@bot.message_handler(commands=['addproduct'])
def add_product_start(message):
    if message.chat.id != ADMIN_ID:
        return bot.reply_to(message, "⛔️ للمشرفين فقط.")
    bot.send_message(message.chat.id, "📝 أرسل اسم المنتج:")
    bot.register_next_step_handler(message, get_product_price)

def get_product_price(message):
    if message.chat.id != ADMIN_ID: return
    name = message.text
    bot.send_message(message.chat.id, "💰 أرسل السعر (رقم فقط):")
    bot.register_next_step_handler(message, get_product_desc, name)

def get_product_desc(message, name):
    if message.chat.id != ADMIN_ID: return
    try:
        price = float(message.text)
        bot.send_message(message.chat.id, "📝 أرسل الوصف:")
        bot.register_next_step_handler(message, get_product_category, name, price)
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ السعر يجب أن يكون رقماً.")
        bot.register_next_step_handler(message, get_product_price)

def get_product_category(message, name, price):
    if message.chat.id != ADMIN_ID: return
    desc = message.text
    bot.send_message(message.chat.id, "📂 أرسل القسم (games/subs/soft):")
    bot.register_next_step_handler(message, get_product_photo, name, price, desc)

def get_product_photo(message, name, price, desc):
    if message.chat.id != ADMIN_ID: return
    category = message.text
    bot.send_message(message.chat.id, "🖼 أرسل صورة المنتج (أو اكتب 'لا'):")
    bot.register_next_step_handler(message, save_product, name, price, desc, category)

def save_product(message, name, price, desc, category):
    if message.chat.id != ADMIN_ID: return
    photo_id = message.photo[-1].file_id if message.content_type == 'photo' else ""
    cursor.execute("INSERT INTO products (name, price, description, photo_id, category) VALUES (?, ?, ?, ?, ?)",
                   (name, price, desc, photo_id, category))
    conn.commit()
    bot.send_message(message.chat.id, f"✅ تمت إضافة '{name}' بنجاح!")

# ==================== صفحات Flask (للصحة والإيقاظ) ====================
@app.route('/')
def home():
    return "Bot is running via POLLING! 🤖"

@app.route('/health')
def health():
    return "OK", 200

# ==================== وضع التطوير المحلي ====================
if __name__ == '__main__':
    if ENV == 'development':
        print("🟢 Local polling mode...")
        bot.remove_webhook()
        bot.infinity_polling()

# ==================== وضع الإنتاج: Polling في خيط خلفي ====================
def run_polling():
    try:
        # مهم جداً: إزالة الـ webhook وإلا لن تصل الرسائل للـ polling
        bot.remove_webhook()
        print("🔄 Polling thread started (webhook removed)")
        bot.polling(none_stop=True, interval=0, timeout=60)
    except Exception as e:
        print("❌ Polling error:", e)

if ENV == 'production' and BOT_TOKEN:
    t = threading.Thread(target=run_polling, daemon=True)
    t.start()
    print("🚀 Production: polling launched in background thread")
