from telebot import types
from config import bot, get_conn, is_admin, ADMIN_ID

def _admin_menu():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("📂 إدارة الأقسام", callback_data="adm_cats"))
    m.add(types.InlineKeyboardButton("📦 إدارة المنتجات", callback_data="adm_prods"))
    m.add(types.InlineKeyboardButton("🧾 الطلبات", callback_data="adm_orders"))
    m.add(types.InlineKeyboardButton("💰 طلبات الشحن", callback_data="adm_topups"))
    m.add(types.InlineKeyboardButton("🔍 بحث عن عميل", callback_data="adm_search"))
    m.add(types.InlineKeyboardButton("🏪 إعدادات المتجر", callback_data="adm_set"))
    m.add(types.InlineKeyboardButton("💳 إعدادات الدفع", callback_data="adm_pay"))
    m.add(types.InlineKeyboardButton("📊 الإحصائيات", callback_data="adm_stats"))
    m.add(types.InlineKeyboardButton("📢 بث رسالة", callback_data="adm_broadcast"))
    m.add(types.InlineKeyboardButton("👤 المشرفون", callback_data="adm_admins"))
    return m


def _open_admin_panel(chat_id):
    bot.send_message(chat_id, "🛠 لوحة تحكم المشرف — اختر:", reply_markup=_admin_menu())


@bot.message_handler(commands=['admin'])
def admin_home_cmd(message):
    if not is_admin(message.chat.id):
        return
    _open_admin_panel(message.chat.id)


@bot.message_handler(func=lambda m: m.text == '🛠 لوحة التحكم')
def admin_home_button(message):
    if not is_admin(message.chat.id):
        return
    _open_admin_panel(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data == 'adm_home')
def adm_home(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    bot.edit_message_text("🛠 لوحة تحكم المشرف — اختر:", call.message.chat.id, call.message.message_id, reply_markup=_admin_menu())


def _cats_list_markup():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT id,name,emoji FROM categories ORDER BY sort_order,id')
        cats = cur.fetchall()
    m = types.InlineKeyboardMarkup(row_width=1)
    for cid, nm, em in cats:
        m.add(types.InlineKeyboardButton(f"✏️ {em} {nm}", callback_data=f"catmenu_{cid}"))
    m.add(types.InlineKeyboardButton("➕ إضافة قسم جديد", callback_data="addcat"))
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
    return m, len(cats)


@bot.callback_query_handler(func=lambda c: c.data == 'adm_cats')
def adm_cats(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    m, n = _cats_list_markup()
    bot.edit_message_text(f"📂 الأقسام ({n}) — اضغط قسماً لتعديله أو حذفه:", call.message.chat.id, call.message.message_id, reply_markup=m)


def _send_cats(chat_id):
    m, n = _cats_list_markup()
    bot.send_message(chat_id, f"📂 الأقسام ({n}):", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('catmenu_'))
def catmenu(call):
    if not is_admin(call.message.chat.id):
        return
    cid = int(call.data.split('_')[1])
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT name,emoji FROM categories WHERE id=%s', (cid,))
        row = cur.fetchone()
    if not row:
        return bot.answer_callback_query(call.id, "القسم غير موجود")
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("✏️ إعادة تسمية", callback_data=f"ren_{cid}"))
    m.add(types.InlineKeyboardButton("🎨 تغيير الإيموجي", callback_data=f"remoji_{cid}"))
    m.add(types.InlineKeyboardButton("🗑 حذف القسم", callback_data=f"delcat_{cid}"))
    m.add(types.InlineKeyboardButton("↩️ رجوع للأقسام", callback_data="adm_cats"))
    bot.edit_message_text(f"📂 القسم: {row[1]} {row[0]}", call.message.chat.id, call.message.message_id, reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'addcat')
def addcat(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📝 أرسل اسم القسم الجديد:")
    bot.register_next_step_handler(call.message, addcat_emoji)


def addcat_emoji(message):
    if not is_admin(message.chat.id):
        return
    name = message.text.strip()
    bot.send_message(message.chat.id, "😀 أرسل إيموجي القسم (مثل 🎮) أو اكتب: لا")
    bot.register_next_step_handler(message, addcat_save, name)


def addcat_save(message, name):
    if not is_admin(message.chat.id):
        return
    emoji = '' if message.text.strip() in ('لا', 'no', '') else message.text.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM categories')
        so = cur.fetchone()[0]
        cur.execute('INSERT INTO categories (name,emoji,sort_order) VALUES (%s,%s,%s)', (name, emoji, so))
    bot.send_message(message.chat.id, f"✅ أُضيف القسم: {emoji} {name}")
    _send_cats(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('ren_'))
def ren(call):
    if not is_admin(call.message.chat.id):
        return
    cid = int(call.data.split('_')[1])
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📝 أرسل الاسم الجديد للقسم:")
    bot.register_next_step_handler(call.message, ren_save, cid)


def ren_save(message, cid):
    if not is_admin(message.chat.id):
        return
    newname = message.text.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('SELECT emoji FROM categories WHERE id=%s', (cid,))
        row = cur.fetchone()
        emoji = row[0] if row else ''
        cur.execute('UPDATE categories SET name=%s WHERE id=%s', (newname, cid))
    bot.send_message(message.chat.id, f"✅ تم التعديل إلى: {emoji} {newname}")
    _send_cats(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('remoji_'))
def remoji(call):
    if not is_admin(call.message.chat.id):
        return
    cid = int(call.data.split('_')[1])
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🎨 أرسل الإيموجي الجديد للقسم:")
    bot.register_next_step_handler(call.message, remoji_save, cid)


def remoji_save(message, cid):
    if not is_admin(message.chat.id):
        return
    emoji = message.text.strip()
    with get_conn() as conn:
        conn.cursor().execute('UPDATE categories SET emoji=%s WHERE id=%s', (emoji, cid))
    bot.send_message(message.chat.id, "✅ تم تحديث الإيموجي")
    _send_cats(message.chat.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith('delcat_'))
def delcat(call):
    if not is_admin(call.message.chat.id):
        return
    cid = int(call.data.split('_')[1])
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("⚠️ نعم، احذف", callback_data=f"dcy_{cid}"))
    m.add(types.InlineKeyboardButton("↩️ إلغاء", callback_data="adm_cats"))
    bot.edit_message_text("🗑 متأكد من حذف القسم؟ ستُحذف كل منتجاته أيضاً.", call.message.chat.id, call.message.message_id, reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('dcy_'))
def dcy(call):
    if not is_admin(call.message.chat.id):
        return
    cid = int(call.data.split('_')[1])
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute('DELETE FROM cart WHERE product_id IN (SELECT id FROM products WHERE category_id=%s)', (cid,))
        cur.execute('DELETE FROM products WHERE category_id=%s', (cid,))
        cur.execute('DELETE FROM categories WHERE id=%s', (cid,))
    bot.answer_callback_query(call.id, "🗑 تم الحذف")
    _send_cats(call.message.chat.id)
