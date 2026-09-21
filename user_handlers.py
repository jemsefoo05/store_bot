from telebot import types
from config import (bot, get_conn, get_setting, fmt_price, add_user, create_order,
                     list_orders_by_user, get_admin_ids, get_balance, deduct_balance,
                     set_order_status, is_admin)

# ==================== واجهة الزبون ====================

@bot.message_handler(commands=['start'])
def start(message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    shop_name = get_setting('shop_name', 'المتجر')
    welcome = get_setting('welcome_text',
        f"أهلاُ بك {message.from_user.first_name} في {shop_name}!\nاختر من القائمة:")

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton('📂 الأقسام'),
               types.KeyboardButton('🛒 السلة'),
               types.KeyboardButton('📦 طلباتي'),
               types.KeyboardButton('💰 رصيدي'),
               types.KeyboardButton('📞 الدعم'))
    if is_admin(message.from_user.id):
        markup.add(types.KeyboardButton('🛠 لوحة التحكم'))

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
        cur.execute('''SELECT id,name,price,description,photo_id FROM products
                       WHERE category_id=%s AND is_active = TRUE ORDER BY id''', (cid,))
        prods = cur.fetchall()
    if not cat:
        return bot.answer_callback_query(call.id, "القسم غير موجود")
    if not prods:
        bot.answer_callback_query(call.id, "لا توجد منتجات في هذا القسم")
        return bot.send_message(call.message.chat.id, f"⚠️ لا توجد منتجات حالياً في قسم {cat[1]} {cat[0]}.")
    for pid, nm, pr, ds, ph in prods:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("➕ إضافة للسلة", callback_data=f"add_{pid}"))
        caption = f"{nm}\n💰 السعر: {fmt_price(pr)}$\n📝 {ds or ''}"
        if ph:
            bot.send_photo(call.message.chat.id, ph, caption=caption, reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, caption, reply_markup=markup)


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
    text = "🛒 محتويات السلة:\n\n"
    total = 0
    for nm, pr, q in items:
        sub = float(pr) * q
        text += f"▪️ {nm} | {q}x = {fmt_price(sub)}$\n"
        total += sub
    text += f"\n💵 الإجمالي: {fmt_price(total)}$"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ إتمام الشراء", callback_data="choose_payment"),
               types.InlineKeyboardButton("🗑 تفريغ", callback_data="clear_cart"))
    bot.send_message(uid, text, reply_markup=markup)


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


@bot.callback_query_handler(func=lambda call: call.data == 'choose_payment')
def choose_payment(call):
    uid = call.message.chat.id
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM cart WHERE user_id=%s', (uid,))
        n = cur.fetchone()[0]
    if not n:
        return bot.answer_callback_query(call.id, "السلة فارغة")
    bal = get_balance(uid)
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton(f"💰 الدفع من الرصيد ({fmt_price(bal)}$)", callback_data="pay_balance"))
    m.add(types.InlineKeyboardButton("🏦 طريقة دفع أخرى (مراجعة الأدمن)", callback_data="pay_external"))
    bot.answer_callback_query(call.id)
    bot.edit_message_text("اختر طريقة الدفع:", uid, call.message.message_id, reply_markup=m)


@bot.callback_query_handler(func=lambda call: call.data == 'pay_balance')
def pay_balance(call):
    uid = call.message.chat.id
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT p.name,p.price,c.quantity FROM cart c
                       JOIN products p ON c.product_id=p.id WHERE c.user_id=%s''', (uid,))
        items = cur.fetchall()
    if not items:
        return bot.answer_callback_query(call.id, "السلة فارغة")
    total = sum(float(i[1]) * i[2] for i in items)
    bal = get_balance(uid)
    if bal < total:
        bot.answer_callback_query(call.id, "الرصيد غير كافٍ")
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("➕ شحن الرصيد", callback_data="topup_menu"))
        return bot.edit_message_text(
            f"⚠️ رصيدك ({fmt_price(bal)}$) غير كافٍ لإتمام هذا الطلب ({fmt_price(total)}$).",
            uid, call.message.message_id, reply_markup=m)

    items_lines = [f"- {nm} ({q}x) = {fmt_price(float(pr) * q)}$" for nm, pr, q in items]
    items_text = "\n".join(items_lines)
    deduct_balance(uid, total)
    order_id = create_order(uid, call.message.chat.username or '', items_text, total)
    set_order_status(order_id, 'paid')

    for admin_id in get_admin_ids():
        try:
            bot.send_message(admin_id,
                f"✅ طلب جديد مدفوع بالرصيد #{order_id}\n👤 {call.message.chat.first_name} (ID: {uid})\n"
                f"📦:\n{items_text}\n💰 {fmt_price(total)}$")
        except Exception:
            pass

    with get_conn() as conn:
        conn.cursor().execute('DELETE FROM cart WHERE user_id=%s', (uid,))
    bot.answer_callback_query(call.id, "✅ تم الدفع من رصيدك")
    bot.edit_message_text(
        f"✅ تم الدفع من رصيدك لطلبك #{order_id}!\nسيتم التواصل معك لتسليم طلبك قريبًا.",
        uid, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == 'pay_external')
def pay_external(call):
    uid = call.message.chat.id
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT p.name,p.price,c.quantity FROM cart c
                       JOIN products p ON c.product_id=p.id WHERE c.user_id=%s''', (uid,))
        items = cur.fetchall()
    if not items:
        return bot.answer_callback_query(call.id, "السلة فارغة")

    total = sum(float(i[1]) * i[2] for i in items)
    items_lines = [f"- {nm} ({q}x) = {fmt_price(float(pr) * q)}$" for nm, pr, q in items]
    items_text = "\n".join(items_lines)

    order_id = create_order(uid, call.message.chat.username or '', items_text, total)

    pay_note = get_setting('payment_note', '💳 لإتمام الدفع، تواصل مع الإدارة.')
    pay_link = get_setting('payment_link', '')

    order_msg = (f"🔔 طلب جديد #{order_id}\n\n👤 {call.message.chat.first_name}\n🆔 {uid}\n\n"
                 f"📦 المنتجات:\n{items_text}\n\n💰 الإجمالي: {fmt_price(total)}$")
    review_kb = types.InlineKeyboardMarkup(row_width=2)
    review_kb.add(types.InlineKeyboardButton("✅ تأكيد الدفع", callback_data=f"ord_ok_{order_id}"),
                  types.InlineKeyboardButton("❌ رفض", callback_data=f"ord_no_{order_id}"))
    for admin_id in get_admin_ids():
        try:
            bot.send_message(admin_id, order_msg, reply_markup=review_kb)
        except Exception as e:
            print('admin notify err', e)

    reply = (f"✅ تم تسجيل طلبك رقم #{order_id} يا {call.message.chat.first_name}!\n"
             f"الإجمالي: {fmt_price(total)}$\n\n{pay_note}")
    markup = types.InlineKeyboardMarkup()
    if pay_link:
        markup.add(types.InlineKeyboardButton("💳 اضغط هنا للدفع", url=pay_link))

    with get_conn() as conn:
        conn.cursor().execute('DELETE FROM cart WHERE user_id=%s', (uid,))
    try:
        bot.edit_message_text(reply, uid, call.message.message_id, reply_markup=markup)
    except Exception:
        bot.send_message(uid, reply, reply_markup=markup)


@bot.message_handler(func=lambda m: m.text == '📦 طلباتي')
def show_my_orders(message):
    uid = message.chat.id
    orders = list_orders_by_user(uid)
    if not orders:
        return bot.send_message(uid, "📦 لا توجد طلبات سابقة.")
    status_ar = {'pending': '⏳ قيد المراجعة', 'paid': '✅ مؤكد', 'cancelled': '❌ ملغي'}
    lines = ["📦 طلباتك:\n"]
    for oid, items_text, total, status in orders:
        lines.append(f"#{oid} — {fmt_price(total)}$ — {status_ar.get(status, status)}")
    bot.send_message(uid, "\n".join(lines))


@bot.message_handler(func=lambda m: m.text == '📞 الدعم')
def support(message):
    bot.send_message(message.chat.id, "📞 للتواصل مع الدعم، أرسل رسالتك هنا وسنرد عليك قريباً.")
