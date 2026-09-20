from telebot import types
from config import (bot, get_conn, get_setting, set_setting, fmt_price, is_admin,
                     ADMIN_ID, PENDING)

# ---------- المنتجات ----------

def _prods_list_markup():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('''SELECT p.id,p.name,p.price,c.emoji,p.is_active FROM products p
                       LEFT JOIN categories c ON p.category_id=c.id ORDER BY p.id''')
        rows = cur.fetchall()
    m = types.InlineKeyboardMarkup(row_width=1)
    for pid, nm, pr, em, active in rows:
        mark = '' if active else '🚫 '
        m.add(types.InlineKeyboardButton(f"{mark}{em or ''} {nm} ({fmt_price(pr)}$)", callback_data=f"prodmenu_{pid}"))
    m.add(types.InlineKeyboardButton("➕ إضافة منتج جديد", callback_data="addprod"))
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
    return m, len(rows)


@bot.callback_query_handler(func=lambda c: c.data == 'adm_prods')
def adm_prods(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    m, n = _prods_list_markup()
    bot.edit_message_text(f"📦 المنتجات ({n}) — اضغط منتجاً للتعديل عليه:", call.message.chat.id, call.message.message_id, reply_markup=m)


def _send_prods(chat_id):
    m, n = _prods_list_markup()
    bot.send_message(chat_id, f"📦 المنتجات ({n}):", reply_markup=m)


def _get_product(pid):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id,name,price,description,photo_id,category_id,is_active FROM products WHERE id=%s', (pid,))
        return cur.fetchone()


@bot.callback_query_handler(func=lambda c: c.data.startswith('prodmenu_'))
def prodmenu(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    p = _get_product(pid)
    if not p:
        return bot.answer_callback_query(call.id, "المنتج غير موجود")
    _, nm, pr, ds, ph, cid, active = p
    status = "🟢 مفعّل" if active else "🚫 معطّل (مخفي عن العملاء)"
    text = f"📦 {nm}\n💰 {fmt_price(pr)}$\n📝 {ds or '-'}\n{status}"
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("✏️ تعديل الاسم", callback_data=f"pename_{pid}"))
    m.add(types.InlineKeyboardButton("💰 تعديل السعر", callback_data=f"peprice_{pid}"))
    m.add(types.InlineKeyboardButton("📝 تعديل الوصف", callback_data=f"pedesc_{pid}"))
    m.add(types.InlineKeyboardButton("🖼 تغيير الصورة", callback_data=f"pephoto_{pid}"))
    m.add(types.InlineKeyboardButton("📂 تغيير القسم", callback_data=f"pecat_{pid}"))
    toggle_label = "🚫 تعطيل المنتج" if active else "🟢 تفعيل المنتج"
    m.add(types.InlineKeyboardButton(toggle_label, callback_data=f"ptoggle_{pid}"))
    m.add(types.InlineKeyboardButton("🗑 حذف نهائي", callback_data=f"pdelconfirm_{pid}"))
    m.add(types.InlineKeyboardButton("↩️ رجوع للمنتجات", callback_data="adm_prods"))
    if ph:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.send_photo(call.message.chat.id, ph, caption=text, reply_markup=m)
    else:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('ptoggle_'))
def ptoggle(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('UPDATE products SET is_active = NOT is_active WHERE id=%s', (pid,))
    bot.answer_callback_query(call.id, "✅ تم تحديث حالة المنتج")
    _send_prods(call.message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('pdelconfirm_'))
def pdelconfirm(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("⚠️ نعم، احذف", callback_data=f"pdy_{pid}"))
    m.add(types.InlineKeyboardButton("↩️ إلغاء", callback_data=f"prodmenu_{pid}"))
    bot.send_message(call.message.chat.id, "🗑 متأكد من حذف هذا المنتج نهائياً؟", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('pdy_'))
def pdy(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM cart WHERE product_id=%s', (pid,))
        cur.execute('DELETE FROM products WHERE id=%s', (pid,))
    bot.answer_callback_query(call.id, "🗑 تم حذف المنتج")
    _send_prods(call.message.chat.id)


# ---- تعديل الاسم ----
@bot.callback_query_handler(func=lambda c: c.data.startswith('pename_'))
def pename(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "✏️ أرسل الاسم الجديد للمنتج:")
    bot.register_next_step_handler(call.message, save_pename, pid)

def save_pename(message, pid):
    if not is_admin(message.chat.id):
        return
    with get_conn() as conn:
        conn.cursor().execute('UPDATE products SET name=%s WHERE id=%s', (message.text.strip(), pid))
    bot.send_message(message.chat.id, "✅ تم تحديث الاسم")
    _send_prods(message.chat.id)


# ---- تعديل السعر ----
@bot.callback_query_handler(func=lambda c: c.data.startswith('peprice_'))
def peprice(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "💰 أرسل السعر الجديد (رقم فقط):")
    bot.register_next_step_handler(call.message, save_peprice, pid)

def save_peprice(message, pid):
    if not is_admin(message.chat.id):
        return
    try:
        price = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ يجب أن يكون رقماً. أعد المحاولة:")
        return bot.register_next_step_handler(message, save_peprice, pid)
    with get_conn() as conn:
        conn.cursor().execute('UPDATE products SET price=%s WHERE id=%s', (price, pid))
    bot.send_message(message.chat.id, "✅ تم تحديث السعر")
    _send_prods(message.chat.id)


# ---- تعديل الوصف ----
@bot.callback_query_handler(func=lambda c: c.data.startswith('pedesc_'))
def pedesc(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📝 أرسل الوصف الجديد (أو اكتب: لا لحذفه):")
    bot.register_next_step_handler(call.message, save_pedesc, pid)

def save_pedesc(message, pid):
    if not is_admin(message.chat.id):
        return
    val = '' if message.text.strip() in ('لا', 'no') else message.text.strip()
    with get_conn() as conn:
        conn.cursor().execute('UPDATE products SET description=%s WHERE id=%s', (val, pid))
    bot.send_message(message.chat.id, "✅ تم تحديث الوصف")
    _send_prods(message.chat.id)


# ---- تغيير الصورة ----
@bot.callback_query_handler(func=lambda c: c.data.startswith('pephoto_'))
def pephoto(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🖼 أرسل الصورة الجديدة (أو اكتب: حذف لإزالة الصورة):")
    bot.register_next_step_handler(call.message, save_pephoto, pid)

def save_pephoto(message, pid):
    if not is_admin(message.chat.id):
        return
    if message.content_type == 'photo':
        photo_id = message.photo[-1].file_id
    elif message.text and message.text.strip() in ('حذف', 'لا'):
        photo_id = ''
    else:
        bot.send_message(message.chat.id, "⚠️ أرسل صورة فعلية أو اكتب: حذف")
        return bot.register_next_step_handler(message, save_pephoto, pid)
    with get_conn() as conn:
        conn.cursor().execute('UPDATE products SET photo_id=%s WHERE id=%s', (photo_id, pid))
    bot.send_message(message.chat.id, "✅ تم تحديث الصورة")
    _send_prods(message.chat.id)


# ---- تغيير القسم ----
@bot.callback_query_handler(func=lambda c: c.data.startswith('pecat_'))
def pecat(call):
    if not is_admin(call.message.chat.id):
        return
    pid = int(call.data.split('_')[1])
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id,name,emoji FROM categories ORDER BY sort_order,id')
        cats = cur.fetchall()
    if not cats:
        return bot.answer_callback_query(call.id, "لا توجد أقسام")
    m = types.InlineKeyboardMarkup(row_width=1)
    for cid, nm, em in cats:
        m.add(types.InlineKeyboardButton(f"{em} {nm}", callback_data=f"pesetcat_{pid}_{cid}"))
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📂 اختر القسم الجديد:", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith('pesetcat_'))
def pesetcat(call):
    if not is_admin(call.message.chat.id):
        return
    _, pid, cid = call.data.split('_')
    with get_conn() as conn:
        conn.cursor().execute('UPDATE products SET category_id=%s WHERE id=%s', (int(cid), int(pid)))
    bot.answer_callback_query(call.id, "✅ تم تغيير القسم")
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
    desc = '' if message.text.strip() in ('لا', 'no', '') else message.text.strip()
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
        cur.execute('INSERT INTO products (name,price,description,photo_id,category_id,is_active) VALUES (%s,%s,%s,%s,%s,TRUE)',
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
    val = '' if message.text.strip() in ('لا', 'no') else message.text.strip()
    set_setting('payment_link', val)
    bot.send_message(message.chat.id, "✅ تم تحديث رابط الدفع")
