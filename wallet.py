from telebot import types
from config import (bot, get_setting, fmt_price, is_admin,
                     get_balance, add_balance,
                     create_topup, get_topup, set_topup_status, list_topups,
                     get_admin_ids, PENDING)

METHOD_LABELS = {
    'binance': '🟡 Binance Pay',
    'usdt': '💵 USDT',
    'ccp': '🏤 بريدي موب (CCP)',
}

@bot.message_handler(func=lambda m: m.text == '💰 رصيدي')
def show_balance(message):
    uid = message.chat.id
    bal = get_balance(uid)
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("➕ شحن الرصيد", callback_data="topup_menu"))
    bot.send_message(uid, f"💰 رصيدك الحالي: {fmt_price(bal)}$", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'topup_menu')
def topup_menu(call):
    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=1)
    for key, label in METHOD_LABELS.items():
        m.add(types.InlineKeyboardButton(label, callback_data=f"topup_method_{key}"))
    bot.send_message(call.message.chat.id, "اختر طريقة الشحن:", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data.startswith('topup_method_'))
def topup_method(call):
    method = call.data.split('_', 2)[2]
    bot.answer_callback_query(call.id)
    min_amt = get_setting('min_topup', '0.1')
    bot.send_message(call.message.chat.id,
                      f"💵 أرسل المبلغ الذي تريد شحنه بالدولار (لا يقل عن {min_amt}$):")
    bot.register_next_step_handler(call.message, topup_amount, method)


def topup_amount(message, method):
    try:
        amount = float(message.text.strip())
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ أرسل رقمًا صحيحًا.")
        return bot.register_next_step_handler(message, topup_amount, method)
    min_amt = float(get_setting('min_topup', '0.1'))
    if amount < min_amt:
        bot.send_message(message.chat.id, f"⚠️ الحد الأدنى للشحن هو {min_amt}$. أرسل مبلغًا أكبر:")
        return bot.register_next_step_handler(message, topup_amount, method)

    PENDING[f"topup_{message.chat.id}"] = {'method': method, 'amount': amount}

    if method == 'binance':
        info = get_setting('binance_info', '(لم يضبط الأدمن بيانات Binance Pay بعد)')
        instructions = f"🟡 أرسل {fmt_price(amount)}$ عبر Binance Pay إلى:\n{info}"
    elif method == 'usdt':
        info = get_setting('usdt_info', '(لم يضبط الأدمن عنوان USDT بعد)')
        instructions = f"💵 أرسل {fmt_price(amount)}$ USDT إلى:\n{info}"
    else:
        info = get_setting('ccp_info', '(لم يضبط الأدمن معلومات CCP بعد)')
        instructions = f"🏤 حوّل {fmt_price(amount)}$ (بما يعادلها بالدينار) عبر بريدي موب إلى:\n{info}"

    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("✅ أرسلت المبلغ", callback_data="topup_sent"))
    bot.send_message(message.chat.id, instructions + "\n\nبعد الإرسال اضغط الزر بالأسفل:", reply_markup=m)


@bot.callback_query_handler(func=lambda c: c.data == 'topup_sent')
def topup_sent(call):
    data = PENDING.get(f"topup_{call.message.chat.id}")
    if not data:
        return bot.answer_callback_query(call.id, "انتهت الجلسة، أعد المحاولة من 💰 رصيدي")
    bot.answer_callback_query(call.id)
    if data['method'] == 'ccp':
        prompt = "🖼 أرسل لقطة شاشة لوصل التحويل:"
    elif data['method'] == 'binance':
        prompt = "🔢 أرسل رقم العملية (Order ID) الخاص بعملية الدفع:"
    else:
        prompt = "🔗 أرسل رقم/هاش العملية (TxID) أو لقطة شاشة:"
    bot.send_message(call.message.chat.id, prompt)
    bot.register_next_step_handler(call.message, topup_proof)


def topup_proof(message):
    key = f"topup_{message.chat.id}"
    data = PENDING.pop(key, None)
    if not data:
        return bot.send_message(message.chat.id, "⚠️ انتهت الجلسة، ابدأ من 💰 رصيدي مرة أخرى.")

    if message.content_type == 'photo':
        proof = message.photo[-1].file_id
        proof_display = "📷 صورة إثبات"
    elif message.text:
        proof = message.text.strip()
        proof_display = f"نص: {proof}"
    else:
        bot.send_message(message.chat.id, "⚠️ أرسل نصًا أو صورة كإثبات.")
        return bot.register_next_step_handler(message, topup_proof)

    topup_id = create_topup(message.chat.id, data['method'], data['amount'], proof)
    bot.send_message(message.chat.id,
                      f"✅ تم إرسال طلب الشحن #{topup_id} ({fmt_price(data['amount'])}$). بانتظار مراجعة الأدمن.")

    label = METHOD_LABELS.get(data['method'], data['method'])
    caption = (f"💰 طلب شحن رصيد #{topup_id}\n👤 {message.chat.first_name} (ID: {message.chat.id})\n"
               f"الطريقة: {label}\nالمبلغ: {fmt_price(data['amount'])}$\n{proof_display}")
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("✅ قبول", callback_data=f"topup_ok_{topup_id}"),
           types.InlineKeyboardButton("❌ رفض", callback_data=f"topup_no_{topup_id}"))
    for admin_id in get_admin_ids():
        try:
            if message.content_type == 'photo':
                bot.send_photo(admin_id, proof, caption=caption, reply_markup=kb)
            else:
                bot.send_message(admin_id, caption, reply_markup=kb)
        except Exception as e:
            print('topup admin notify err', e)


@bot.callback_query_handler(func=lambda c: c.data.startswith('topup_ok_'))
def topup_ok(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    tid = int(call.data.split('_')[2])
    t = get_topup(tid)
    if not t:
        return bot.answer_callback_query(call.id, "الطلب غير موجود")
    if t[5] != 'pending':
        return bot.answer_callback_query(call.id, f"تمت معالجته مسبقاً ({t[5]})")
    add_balance(t[1], t[3])
    set_topup_status(tid, 'approved')
    bot.answer_callback_query(call.id, "✅ تم القبول وشحن الرصيد")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    try:
        new_bal = get_balance(t[1])
        bot.send_message(t[1], f"✅ تم قبول طلب الشحن #{tid} وإضافة {fmt_price(t[3])}$ لرصيدك.\nرصيدك الحالي: {fmt_price(new_bal)}$")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data.startswith('topup_no_'))
def topup_no(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    tid = int(call.data.split('_')[2])
    t = get_topup(tid)
    if not t:
        return bot.answer_callback_query(call.id, "الطلب غير موجود")
    if t[5] != 'pending':
        return bot.answer_callback_query(call.id, f"تمت معالجته مسبقاً ({t[5]})")
    set_topup_status(tid, 'rejected')
    bot.answer_callback_query(call.id, "❌ تم الرفض")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass
    try:
        bot.send_message(t[1], f"❌ تم رفض طلب الشحن #{tid}. تواصل مع الدعم لمزيد من التفاصيل.")
    except Exception:
        pass


@bot.callback_query_handler(func=lambda c: c.data == 'adm_topups')
def adm_topups(call):
    if not is_admin(call.message.chat.id):
        return bot.answer_callback_query(call.id, "⛔️")
    pending = list_topups(status='pending', limit=15)
    bot.answer_callback_query(call.id)
    if not pending:
        m = types.InlineKeyboardMarkup()
        m.add(types.InlineKeyboardButton("↩️ رجوع", callback_data="adm_home"))
        return bot.edit_message_text("💰 لا توجد طلبات شحن معلقة.", call.message.chat.id, call.message.message_id, reply_markup=m)
    for tid, uid, method, amount, proof, status in pending:
        label = METHOD_LABELS.get(method, method)
        text = f"💰 طلب شحن #{tid}\n👤 {uid}\nالطريقة: {label}\nالمبلغ: {fmt_price(amount)}$\nإثبات: {proof}"
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(types.InlineKeyboardButton("✅ قبول", callback_data=f"topup_ok_{tid}"),
               types.InlineKeyboardButton("❌ رفض", callback_data=f"topup_no_{tid}"))
        bot.send_message(call.message.chat.id, text, reply_markup=kb)
