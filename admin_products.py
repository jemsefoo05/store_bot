from telebot import types
from config import bot, get_conn, get_setting, set_setting, fmt_price, is_admin, ADMIN_ID, PENDING

# ---------- المنتجات ----------
def _prods_list_markup():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT p.id,p.name,p.price,c.emoji FROM products p LEFT JOIN categories c ON p.category_id=c.id ORDER BY p.id')
        rows = cur.fetchall()
    m = types.InlineKeyboardMarkup(row_width=1)
    for pid, nm, pr, em in rows:
        m.add(types.InlineKeyboardButton(f"🗑 {em or ''} {nm} ({fmt_price(pr)}$)", callback_data=f"delprod_{pid}"))
    m.add(types.InlineKeyboardButton("➕ إضافة منتج جديد", callback_data="addprod"))
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
    return m, len(rows)

@bot.callback_query_handler(func=lambda c: c.data == 'adm_prods')
def adm_prods(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    m, n = _prods_list_markup()
    bot.edit_message_text(f"📦 المنتجات ({n}) — اضغط منتجاً لحذفه:", call.message.chat.id, call.message.message_id, reply_markup=m)

def _send_prods(chat_id):
    m, n = _prods_list_markup()
    bot.send_message(chat_id, f"📦 المنتجات ({n}):", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith('delprod_'))
def delprod(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM cart WHERE product_id=%s', (pid,))
        cur.execute('DELETE FROM products WHERE id=%s', (pid,))
    bot.answer_callback_query(call.id, "🗑 تم حذف المنتج")
    _send_prods(call.message.chat.id)

# إضافة منتج (خطوة بخطوة)
@bot.callback_query_handler(func=lambda c: c.data == 'addprod')
def addprod(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📝 1/5 أرسل اسم المنتج:")
    bot.register_next_step_handler(call.message, addprod_price)

def addprod_price(message):
    if not is_admin(message.chat.id):
        return
    name = message.text.strip()
    bot.send_message(message.chat.id, "💰 2/5 أرسل سعر المنتج (رقم فقط):")
    bot.register_next_step_handler(message, addprod_desc, name)

def addprod_desc(message, name):
    if not is_admin(message.chat.id):
        return
    try:
        price = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ السعر يجب أن يكون رقماً. أعد الإرسال:")
        return bot.register_next_step_handler(message, addprod_desc, name)
    bot.send_message(message.chat.id, "📝 3/5 أرسل وصف المنتج (أو اكتب: لا):")
    bot.register_next_step_handler(message, addprod_cat, name, price)

def addprod_cat(message, name, price):
    if not is_admin(message.chat.id):
        return
    desc = '' if message.text.strip() in ('لا','no','') else message.text.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id,name,emoji FROM categories ORDER BY sort_order,id')
        cats = cur.fetchall()
    if not cats:
        bot.send_message(message.chat.id, "⚠️ لا توجد أقسام! أنشئ قسماً أولاً من إدارة الأقسام.")
        return
    PENDING[str(message.chat.id)] = {'name': name, 'price': price, 'desc': desc}
    m = types.InlineKeyboardMarkup(row_width=1)
    for cid, nm, em in cats:
        m.add(types.InlineKeyboardButton(f"{em} {nm}", callback_data=f"selcat_{cid}"))
    bot.send_message(message.chat.id, "📂 4/5 اختر قسم المنتج:", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith('selcat_'))
def selcat(call):
    if not is_admin(call.message.chat.id):
        return
    cid = int(call.data.split('_')[1])
    data = PENDING.pop(str(call.message.chat.id), None)
    if not data:
        return bot.answer_callback_query(call.id, "انتهت الجلسة، أعد المحاولة من إدارة المنتجات")
    data['cat'] = cid
    bot.answer_callback_query(call.id, "🖼 5/5 أرسل صورة المنتج الآن (أو اكتب: لا)")
    bot.register_next_step_handler(call.message, addprod_photo, data)

def addprod_photo(message, data):
    if not is_admin(message.chat.id):
        return
    photo_id = message.photo[-1].file_id if message.content_type == 'photo' else ''
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('INSERT INTO products (name,price,description,photo_id,category_id) VALUES (%s,%s,%s,%s,%s)',
                    (data['name'], data['price'], data['desc'], photo_id, data['cat']))
    bot.send_message(message.chat.id, f"✅ أُضيف المنتج: {data['name']}")
    _send_prods(message.chat.id)

# ---------- إعدادات المتجر ----------
@bot.callback_query_handler(func=lambda c: c.data == 'adm_set')
def adm_set(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    sn = get_setting('shop_name', 'المتجر')
    wt = get_setting('welcome_text', '(افتراضي)')
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("✏️ تعديل اسم المتجر", callback_data="set_name"))
    m.add(types.InlineKeyboardButton("✏️ تعديل نص الترحيب", callback_data="set_welcome"))
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
    bot.edit_message_text(f"🏪 إعدادات المتجر\n\n🏷 الاسم: {sn}\n💬 الترحيب: {wt}", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data == 'set_name')
def set_name(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🏷 أرسل اسم المتجر الجديد:")
    bot.register_next_step_handler(call.message, save_name)

def save_name(message):
    if not is_admin(message.chat.id):
        return
    set_setting('shop_name', message.text.strip())
    bot.send_message(message.chat.id, "✅ تم تحديث اسم المتجر")

@bot.callback_query_handler(func=lambda c: c.data == 'set_welcome')
def set_welcome(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "💬 أرسل نص الترحيب (يظهر عند /start):")
    bot.register_next_step_handler(call.message, save_welcome)

def save_welcome(message):
    if not is_admin(message.chat.id):
        return
    set_setting('welcome_text', message.text.strip())
    bot.send_message(message.chat.id, "✅ تم تحديث نص الترحيب")

# ---------- إعدادات الدفع ----------
@bot.callback_query_handler(func=lambda c: c.data == 'adm_pay')
def adm_pay(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    pn = get_setting('payment_note', '(افتراضي)')
    pl = get_setting('payment_link', '(بدون رابط)')
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("✏️ تعديل تعليمات الدفع", callback_data="pay_note"))
    m.add(types.InlineKeyboardButton("✏️ تعديل رابط الدفع", callback_data="pay_link"))
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
    bot.edit_message_text(f"💳 إعدادات الدفع\n\n📄 التعليمات: {pn}\n🔗 الرابط: {pl}", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data == 'pay_note')
def pay_note(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📄 أرسل تعليمات الدفع (تظهر للعميل بعد الشراء):")
    bot.register_next_step_handler(call.message, save_pay_note)

def save_pay_note(message):
    if not is_admin(message.chat.id):
        return
    set_setting('payment_note', message.text.strip())
    bot.send_message(message.chat.id, "✅ تم تحديث تعليمات الدفع")

@bot.callback_query_handler(func=lambda c: c.data == 'pay_link')
def pay_link(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🔗 أرسل رابط الدفع (أو اكتب: لا لإزالته):")
    bot.register_next_step_handler(call.message, save_pay_link)

def save_pay_link(message):
    if not is_admin(message.chat.id):
        return
    val = '' if message.text.strip() in ('لا','no','') else message.text.strip()
    set_setting('payment_link', val)
    bot.send_message(message.chat.id, "✅ تم تحديث رابط الدفع")
