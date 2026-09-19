from telebot import types
from config import bot, get_conn, get_setting, fmt_price, is_admin, ADMIN_ID

# ==================== واجهة الزبون ====================
@bot.message_handler(commands=['start'])
def start(message):
    shop_name = get_setting('shop_name', 'المتجر')
    welcome = get_setting('welcome_text',
        f"أهلاُ بك {message.from_user.first_name} في {shop_name}! 🎉\nاختر من القائمة:")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton('📂 الأقسام'),
               types.KeyboardButton('🛒 السلة'),
               types.KeyboardButton('📞 الدعم'))
    bot.send_message(message.chat.id, welcome, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📂 الأقسام')
def show_categories(message):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id,name,emoji FROM categories ORDER BY sort_order,id')
        cats = cur.fetchall()
    if not cats:
        return bot.send_message(message.chat.id, "⚠️ لا توجد أقسام بعد.")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cid, nm, em in cats:
        markup.add(types.InlineKeyboardButton(f"{em} {nm}", callback_data=f"cat_{cid}"))
    bot.send_message(message.chat.id, "📂 اختر القسم:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
def show_products(call):
    try:
        cid = int(call.data.split('_')[1])
    except Exception:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT name,emoji FROM categories WHERE id=%s', (cid,))
        cat = cur.fetchone()
        cur.execute('SELECT id,name,price,description,photo_id FROM products WHERE category_id=%s ORDER BY id', (cid,))
        prods = cur.fetchall()
    if not cat:
        return bot.answer_callback_query(call.id, "القسم غير موجود")
    if not prods:
        bot.answer_callback_query(call.id, "لا توجد منتجات في هذا القسم")
        return bot.send_message(call.message.chat.id, f"⚠️ لا توجد منتجات حالياً في قسم {cat[1]} {cat[0]}.")
    for pid, nm, pr, ds, ph in prods:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ إضافة للسلة", callback_data=f"add_{pid}"))
        caption = f"*{nm}*\n💰 السعر: {fmt_price(pr)}$\n📝 {ds or ''}"
        if ph:
            bot.send_photo(call.message.chat.id, ph, caption=caption, parse_mode='Markdown', reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_'))
def add_to_cart(call):
    pid = int(call.data.split('_')[1])
    uid = call.message.chat.id
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''INSERT INTO cart (user_id,product_id,quantity) VALUES (%s,%s,1)
                       ON CONFLICT (user_id,product_id) DO UPDATE SET quantity = cart.quantity + 1''', (uid, pid))
    bot.answer_callback_query(call.id, "✅ تمت الإضافة!")

@bot.message_handler(func=lambda m: m.text == '🛒 السلة')
def show_cart(message):
    uid = message.chat.id
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT p.name,p.price,c.quantity FROM cart c
                       JOIN products p ON c.product_id=p.id WHERE c.user_id=%s''', (uid,))
        items = cur.fetchall()
    if not items:
        return bot.send_message(uid, "🛒 السلة فارغة.")
    text = "🛒 *محتويات السلة:*\n\n"
    total = 0
    for nm, pr, q in items:
        sub = float(pr) * q
        text += f"▪️ {nm} | {q}x = {fmt_price(sub)}$\n"
        total += sub
    text += f"\n💵 *الإجمالي: {fmt_price(total)}$*"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ إتمام الشراء", callback_data="checkout"),
               types.InlineKeyboardButton("🗑 تفريغ", callback_data="clear_cart"))
    bot.send_message(uid, text, parse_mode='Markdown', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'clear_cart')
def clear_cart(call):
    uid = call.message.chat.id
    with get_conn() as conn:
        conn.cursor().execute('DELETE FROM cart WHERE user_id=%s', (uid,))
    bot.answer_callback_query(call.id, "🗑 تم التفريغ.")
    try:
        bot.edit_message_text("🛒 السلة فارغة الآن.", uid, call.message.message_id)
    except Exception:
        pass

@bot.callback_query_handler(func=lambda call: call.data == 'checkout')
def checkout(call):
    uid = call.message.chat.id
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT p.name,p.price,c.quantity FROM cart c
                       JOIN products p ON c.product_id=p.id WHERE c.user_id=%s''', (uid,))
        items = cur.fetchall()
    if not items:
        return bot.answer_callback_query(call.id, "السلة فارغة")
    total = sum(float(i[1]) * i[2] for i in items)
    pay_note = get_setting('payment_note', '💳 لإتمام الدفع، تواصل مع الإدارة.')
    pay_link = get_setting('payment_link', '')
    order = f"🔔 *طلب جديد!*\n\n👤 [{call.message.chat.first_name}](tg://user?id={uid})\n🆔 `{uid}`\n\n📦 *المنتجات:*\n"
    for nm, pr, q in items:
        order += f"- {nm} ({q}x) = {fmt_price(float(pr)*q)}$\n"
    order += f"\n💰 *الإجمالي: {fmt_price(total)}$*"
    try:
        bot.send_message(ADMIN_ID, order, parse_mode='Markdown')
    except Exception as e:
        print('admin notify err', e)
    reply = f"✅ تم تسجيل طلبك يا {call.message.chat.first_name}! 🎉\nالإجمالي: *{fmt_price(total)}$*\n\n{pay_note}"
    markup = None
    if pay_link:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 اضغط هنا للدفع", url=pay_link))
    with get_conn() as conn:
        conn.cursor().execute('DELETE FROM cart WHERE user_id=%s', (uid,))
    try:
        bot.edit_message_text(reply, uid, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
    except Exception:
        bot.send_message(uid, reply, parse_mode='Markdown', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📞 الدعم')
def support(message):
    bot.send_message(message.chat.id, "📞 للتواصل مع الدعم، أرسل رسالتك هنا وسنرد عليك قريباً.")
