from telebot import types
from config import (bot, is_admin, ADMIN_ID, get_order, set_order_status, list_orders,
                     count_users, revenue_total, get_all_user_ids, get_admin_ids,
                     get_extra_admin_ids, add_extra_admin, remove_extra_admin, fmt_price)

# ---------- أزرار تأكيد/رفض الطلب السريعة ----------

@bot.callback_query_handler(func=lambda c: c.data.startswith('ord_ok_'))
def ord_ok(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    order_id = int(call.data.split('_')[2])
    order = get_order(order_id)
    if not order:
        return bot.answer_callback_query(call.id, "الطلب غير موجود")
    if order[5] != 'pending':
        return bot.answer_callback_query(call.id, f"تمت معالجته مسبقاً ({order[5]})")
    set_order_status(order_id, 'paid')
    bot.answer_callback_query(call.id, "✅ تم تأكيد الطلب")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(call.message.chat.id, f"✅ تم تأكيد الطلب #{order_id}")
    except Exception:
        pass
    try:
        bot.send_message(order[1], f"✅ تم تأكيد دفعك لطلبك #{order_id}. شكراً لثقتك!")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('ord_no_'))
def ord_no(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    order_id = int(call.data.split('_')[2])
    order = get_order(order_id)
    if not order:
        return bot.answer_callback_query(call.id, "الطلب غير موجود")
    if order[5] != 'pending':
        return bot.answer_callback_query(call.id, f"تمت معالجته مسبقاً ({order[5]})")
    set_order_status(order_id, 'cancelled')
    bot.answer_callback_query(call.id, "❌ تم رفض الطلب")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(call.message.chat.id, f"❌ تم رفض الطلب #{order_id}")
    except Exception:
        pass
    try:
        bot.send_message(order[1], f"❌ تم رفض طلبك #{order_id}. تواصل مع الدعم لمزيد من التفاصيل.")
    except Exception:
        pass


# ---------- قائمة الطلبات المعلقة من لوحة التحكم ----------
@bot.callback_query_handler(func=lambda c: c.data == 'adm_orders')
def adm_orders(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    orders = list_orders(status='pending', limit=15)
    if not orders:
        bot.answer_callback_query(call.id, "لا توجد طلبات معلقة")
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
        return bot.edit_message_text("🧾 لا توجد طلبات معلقة حالياً.", call.message.chat.id, call.message.message_id, reply_markup=m)
    bot.answer_callback_query(call.id)
    for oid, uid, uname, items_text, total, status in orders:
        text = f"🔔 طلب #{oid}\n👤 @{uname or uid}\n📦:\n{items_text}\n💰 {fmt_price(total)}$"
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("✅ تأكيد", callback_data=f"ord_ok_{oid}"),
               types.InlineKeyboardButton("❌ رفض", callback_data=f"ord_no_{oid}"))
        bot.send_message(call.message.chat.id, text, reply_markup=kb)


# ---------- الإحصائيات ----------
@bot.callback_query_handler(func=lambda c: c.data == 'adm_stats')
def adm_stats(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    users_n = count_users()
    all_orders = list_orders(limit=1000)
    pending_n = sum(1 for o in all_orders if o[5] == 'pending')
    paid_n = sum(1 for o in all_orders if o[5] == 'paid')
    cancelled_n = sum(1 for o in all_orders if o[5] == 'cancelled')
    revenue = revenue_total()
    text = (f"📊 إحصائيات المتجر\n\n"
            f"👥 المستخدمون: {users_n}\n"
            f"🧾 إجمالي الطلبات: {len(all_orders)}\n"
            f"⏳ معلقة: {pending_n}\n"
            f"✅ مؤكدة: {paid_n}\n"
            f"❌ ملغاة: {cancelled_n}\n"
            f"💵 إجمالي المبيعات المؤكدة: {fmt_price(revenue)}$")
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
    bot.answer_callback_query(call.id)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=m)


# ---------- بث رسالة لكل المستخدمين ----------
@bot.callback_query_handler(func=lambda c: c.data == 'adm_broadcast')
def adm_broadcast(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "📢 أرسل الرسالة التي تريد بثها لكل المستخدمين:")
    bot.register_next_step_handler(call.message, do_broadcast)

def do_broadcast(message):
    if not is_admin(message.chat.id):
        return
    text = message.text
    ids = get_all_user_ids()
    sent = 0
    for uid in ids:
        try:
            bot.send_message(uid, f"📢 {text}")
            sent += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"✅ تم الإرسال إلى {sent} من أصل {len(ids)} مستخدم.")


# ---------- إدارة المشرفين ----------
@bot.callback_query_handler(func=lambda c: c.data == 'adm_admins')
def adm_admins(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    extra = get_extra_admin_ids()
    lines = [f"👑 المشرف الرئيسي: {ADMIN_ID}"]
    lines += [f"👤 {i}" for i in extra] if extra else ["(لا يوجد مشرفون إضافيون)"]
    text = "\n".join(["🛠 المشرفون:"] + lines)
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("➕ إضافة مشرف", callback_data="admadd"))
    if extra:
        m.add(types.InlineKeyboardButton("➖ إزالة مشرف", callback_data="admrem"))
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
    bot.answer_callback_query(call.id)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data == 'admadd')
def admadd(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "أرسل رقم آيدي المستخدم (يمكنه معرفته عبر @userinfobot):")
    bot.register_next_step_handler(call.message, save_admadd)

def save_admadd(message):
    if not is_admin(message.chat.id):
        return
    txt = message.text.strip()
    if not txt.isdigit():
        bot.send_message(message.chat.id, "⚠️ أرسل رقماً صحيحاً.")
        return
    add_extra_admin(txt)
    bot.send_message(message.chat.id, f"✅ تمت إضافة {txt} كمشرف.")

@bot.callback_query_handler(func=lambda c: c.data == 'admrem')
def admrem(call):
    if not is_admin(call.message.chat.id):
        return
    extra = get_extra_admin_ids()
    m = types.InlineKeyboardMarkup(row_width=1)
    for i in extra:
        m.add(types.InlineKeyboardButton(f"🗑 {i}", callback_data=f"admrm_{i}"))
    m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_admins"))
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "اختر المشرف لإزالته:", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith('admrm_'))
def admrm(call):
    if not is_admin(call.message.chat.id):
        return
    uid = call.data.split('_')[1]
    remove_extra_admin(uid)
    bot.answer_callback_query(call.id, "✅ تمت الإزالة")
    bot.send_message(call.message.chat.id, f"✅ تمت إزالة {uid} من المشرفين.")
