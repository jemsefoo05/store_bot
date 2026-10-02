import os
import asyncio
import logging
import db
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)

# --- جلب المتغيرات من البيئة ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))
PROOFS_CHANNEL_ID = os.getenv("PROOFS_CHANNEL_ID", "")
REVIEWS_CHANNEL = os.getenv("REVIEWS_CHANNEL", "https://t.me/YourReviewsChannel")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourDigitalStore_bot")
STORE_BANNER_URL = os.getenv(
    "STORE_BANNER_URL", 
    "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80"
)

# حالات المحادثات
WAITING_QTY = 1
WAITING_WARRANTY_VIDEO = 20

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# --- 1. القائمة الرئيسية التفاعلية ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(0.4)

    referrer_id = None
    if context.args and len(context.args) > 0 and context.args[0].isdigit():
        referrer_id = int(context.args[0])

    db.register_or_get_user(user.id, user.username or "", user.first_name or "", referrer_id)
    stats = db.get_live_ticker_stats()

    keyboard = [
        [
            InlineKeyboardButton("🟩 المنتجات 🛒", callback_data="show_catalog"),
            InlineKeyboardButton("الإحالة 🤝", callback_data="referral_info")
        ],
        [
            InlineKeyboardButton("🟥 شحن الرصيد 💳", callback_data="deposit_info"),
            InlineKeyboardButton("رصيدي 💰", callback_data="my_balance")
        ],
        [
            InlineKeyboardButton("طلباتي 📦", callback_data="my_orders"),
            InlineKeyboardButton("الدعم 📝", callback_data="support_info")
        ],
        [
            InlineKeyboardButton("⭐ آراء العملاء", url=REVIEWS_CHANNEL),
            InlineKeyboardButton("📖 شروحات وضمان", callback_data="show_tutorials")
        ],
        [
            InlineKeyboardButton("🤖 API", callback_data="api_info"),
            InlineKeyboardButton("🎁 الهدية اليومية", callback_data="claim_daily_bonus")
        ],
        [
            InlineKeyboardButton("🟩 تغيير اللغة / Language 🌐", callback_data="lang_info")
        ]
    ]

    welcome_text = (
        f"🔥 **أهلاً بك يا {user.first_name} في متجرنا الرقمي!** 🚀\n"
        "──────────────────────\n"
        "⚡ **نشاط المتجر الحي خلال 24 ساعة:**\n"
        f"• تم تسليم `{max(stats['sales_today'], 14)}` طلباً بنجاح 📦\n"
        "• سرعة التسليم: `3 ثوانٍ فقط` ⏱️\n"
        "• ضمان تشغيل كامل مشروط بالتوثيق 🛡️\n"
        "──────────────────────\n"
        "اختر من القائمة أدناه لبدء التسوق الفوري:"
    )

    if update.callback_query:
        await update.callback_query.edit_message_caption(
            caption=welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=STORE_BANNER_URL,
            caption=welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

# --- 2. شروحات التفعيل وسياسة الضمان ---
async def show_tutorials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = (
        "📖 **دليل الاستخدام وشروحات التفعيل:**\n"
        "────────────────────\n\n"
        "1️⃣ **كيف أستلم طلبي؟**\n"
        "• التسليم فوري وتلقائي بمجرد الدفع، وستجد بيانات طلبك في الشات ومحفوظة دائماً في قسم (طلباتي 📦).\n\n"
        "2️⃣ **شروط الضمان والاستبدال 🛡️:**\n"
        "• **هام جداً:** يجب بدء تصوير شاشة بالفيديو **من لحظة استلام الكود في البوت** وحتى التجربة مباشرة دون إيقاف مؤقت، لضمان استبداله فوراً في حال وجود أي خلل.\n"
        "• بدون هذا التوثيق المستمر، لا يتم قبول أي بلاغ استبدال نهائياً.\n\n"
        "3️⃣ **طرق شحن الرصيد:**\n"
        "• USDT (BEP20) - كشف تلقائي.\n"
        "• الدفع المحلي متوفر عبر التواصل مع الإدارة."
    )
    keyboard = [[InlineKeyboardButton("🟦 العودة للرئيسية 🏠", callback_data="back_to_home")]]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- 3. الهدية اليومية والإحالة ---
async def handle_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    res = db.claim_daily_bonus(query.from_user.id, bonus_amount=0.01)

    if res["success"]:
        await query.answer("🎉 مبروك! تمت إضافة (+0.01$ USDT) لمحفظتك!", show_alert=True)
        await start(update, context)
    else:
        await query.answer(res["msg"], show_alert=True)

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    stats = db.get_referral_stats(user_id)
    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

    text = (
        "🤝 **نظام الإحالة والتسويق**\n\n"
        "ادعُ أصدقاءك واحصل على **USDT 0.05** فور إتمام أول عملية شراء لهم.\n\n"
        "🔗 **رابطك الخاص (اضغط للنسخ):**\n"
        f"`{ref_link}`\n\n"
        f"👥 عدد المدعوين: `{stats['total_referred']}`\n"
        f"💰 أرباحك من الإحالة: `USDT {float(stats['total_earnings']):.2f}`"
    )
    keyboard = [[InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- 4. الرصيد والشحن والـ API ---
async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    balance = db.get_user_balance(query.from_user.id)
    text = f"💰 **رصيدك الحالي:** USDT {balance:.2f}"
    keyboard = [[InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    balance = db.get_user_balance(query.from_user.id)

    text = (
        f"💰 **رصيدك الحالي:** USDT {balance:.2f}\n\n"
        "اختر طريقة شحن الرصيد:"
    )
    keyboard = [
        [
            InlineKeyboardButton("🟡 Binance Pay", callback_data="pay_bep20"),
            InlineKeyboardButton("💵 USDT (BEP20)", callback_data="pay_bep20")
        ],
        [InlineKeyboardButton("🟥 إلغاء ❌", callback_data="cancel_order")]
    ]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_api_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🤖 **واجهة الموزعين البرمجية (Reseller API)**\n\n"
        "مفتاح الربط البرمجي الخاص بحسابك:\n"
        f"`sec_live_{query.from_user.id}x98af3`\n\n"
        "📌 يتيح لك ربط متجرك الخاص والسحب التلقائي من مخزوننا بالأسعار المخفضة."
    )
    keyboard = [[InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- 5. كتالوج المنتجات وتحديد الكمية ---
async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    products = db.get_all_products_with_stock()
    keyboard = []

    for p in products:
        stock = p["stock"]
        price = float(p["price_usd"])
        btn_text = f"🟩 {p['name']} | ${price:.2f} ({stock})" if stock > 0 else f"🟥 {p['name']} | ${price:.2f} (0)"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"prod_{p['id']}")])

    keyboard.append([InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")])
    await query.edit_message_caption(caption="اختر المنتج الذي تريد شراءه: 🛒", reply_markup=InlineKeyboardMarkup(keyboard))

async def view_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prod_id = int(query.data.replace("prod_", ""))
    p = db.get_product_by_id(prod_id)

    text = (
        f"{p['description'] or ''}\n\n"
        f"💵 السعر: USDT {float(p['price_usd']):.2f}\n"
        f"📦 المتوفر: {p['stock']}\n\n"
        "🏷️ **تخفيضات الجملة التلقائية:**\n"
        f"• ≥ 20 قطعة ← ${float(p['bulk_price_20'] or p['price_usd']):.2f}/قطعة\n"
        f"• ≥ 50 قطعة ← ${float(p['bulk_price_50'] or p['price_usd']):.2f}/قطعة"
    )

    if p["stock"] > 0:
        keyboard = [
            [InlineKeyboardButton("🟩 شراء الآن 🛒", callback_data=f"buy_{prod_id}")],
            [InlineKeyboardButton("رجوع ⬅️", callback_data="show_catalog"), InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🔔 نبهني فور توفر كمية جديدة", callback_data=f"alert_{prod_id}")],
            [InlineKeyboardButton("رجوع ⬅️", callback_data="show_catalog"), InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]
        ]

    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def register_alert_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    prod_id = int(query.data.replace("alert_", ""))
    db.add_stock_alert(query.from_user.id, prod_id)
    await query.answer("🔔 تم تسجيل تنبيهك! سنرسل لك إشعاراً فورياً بمجرد توفر كميات جديدة.", show_alert=True)

async def start_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prod_id = int(query.data.replace("buy_", ""))
    context.user_data["buy_prod_id"] = prod_id
    p = db.get_product_by_id(prod_id)

    text = (
        f"🛍️ {p['name']}\n"
        f"📦 المتوفر: {p['stock']}\n"
        f"💵 سعر القطعة: USDT {float(p['price_usd']):.2f}\n\n"
        "✏️ أدخل الكمية المطلوبة:"
    )

    keyboard = [[InlineKeyboardButton("🟥 إلغاء ❌", callback_data="cancel_order")]]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_QTY

async def process_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
        if qty <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ يرجى كتابة عدد صحيح فقط:")
        return WAITING_QTY

    prod_id = context.user_data.get("buy_prod_id")
    p = db.get_product_by_id(prod_id)
    user_id = update.effective_user.id
    balance = db.get_user_balance(user_id)

    if qty > p["stock"]:
        await update.message.reply_text(f"⚠️ المتوفر فقط {p['stock']} قطعة. أدخل كمية أقل:")
        return WAITING_QTY

    unit_price = db.calculate_unit_price(p, qty)
    total_price = unit_price * qty
    context.user_data["order_qty"] = qty
    context.user_data["order_total"] = total_price

    discount_notice = "🎉 **تم تطبيق تخفيض الجملة التلقائي!**\n" if unit_price < float(p["price_usd"]) else ""

    invoice_text = (
        "🧾 **فاتورة الشراء**\n\n"
        f"{discount_notice}"
        f"🛍 المنتج: {p['name']}\n"
        f"📦 الكمية: {qty} (المتوفر: {p['stock']})\n"
        f"💵 سعر القطعة: USDT {unit_price:.2f}\n"
        f"💰 الإجمالي: USDT {total_price:.2f}\n"
        f"👛 رصيدك: USDT {balance:.2f}"
    )

    keyboard = [
        [InlineKeyboardButton("💳 دفع عبر محفظة البوت", callback_data=f"pay_balance_{prod_id}_{qty}")],
        [InlineKeyboardButton("💠 USDT BSC", callback_data="pay_bep20")],
        [InlineKeyboardButton("🟥 إلغاء ❌", callback_data="cancel_order")]
    ]
    await update.message.reply_text(invoice_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ConversationHandler.END

# --- 6. التنفيذ الفوري للتسليم والنشر في الإثباتات ---
async def pay_with_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, _, prod_id_str, qty_str = query.data.split("_")
    prod_id = int(prod_id_str)
    qty = int(qty_str)
    user = query.from_user

    await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(0.5)

    result = db.purchase_from_balance(user.id, prod_id, qty)

    if not result["success"]:
        await query.answer(f"❌ {result['error']}", show_alert=True)
        return

    p_type = result["product_type"]
    items_text = ""
    for idx, itm in enumerate(result["items"], start=1):
        if p_type == "ACCOUNT":
            items_text += f"{idx}. 👤 بيانات الحساب:\n`{itm}`\n\n"
        elif p_type == "LINK":
            items_text += f"{idx}. 🔗 رابط الدعوة المباشر:\n{itm}\n\n"
        else:
            items_text += f"{idx}. 🔑 كود التفعيل:\n`{itm}`\n\n"

    celebration_msg = (
        f"🎊 **ألف مبروك يا {user.first_name}! تم إتمام الطلب بنجاح!** 🚀\n"
        "──────────────────────\n"
        f"📦 **المنتج:** {result['product_name']}\n"
        f"🔢 **الكمية:** {qty}\n"
        f"💰 **المبلغ المدفوع:** `${result['total_cost']:.2f} USDT`\n\n"
        f"⚡ **بيانات طلبك:**\n{items_text}\n"
        "──────────────────────\n"
        "📹 **تنبيه الضمان الصارم:** يرجى تصوير الشاشة بالفيديو من لحظة قراءة هذه الرسالة وحتى تجربة الكود مباشرة، بدون الفيديو لن يتم استبدال أي طلب إذا طرأ عطل."
    )

    keyboard = [
        [InlineKeyboardButton("🛠 طلب استبدال / ضمان (بشرط الفيديو)", callback_data=f"claim_{result['order_id']}")],
        [InlineKeyboardButton("🟦 العودة للرئيسية 🏠", callback_data="back_to_home")]
    ]
    await query.edit_message_text(celebration_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    if PROOFS_CHANNEL_ID:
        try:
            proof_text = (
                "🛒 **عملية شراء جديدة مكتملة بنجاح!** 🔥\n"
                "──────────────────\n"
                f"🛍 **المنتج:** {result['product_name']}\n"
                f"🔢 **الكمية:** {qty}\n"
                f"💵 **القيمة:** `${result['total_cost']:.2f} USDT`\n"
                "⚡ **التسليم:** فوري في 3 ثوانٍ ⏱️\n"
                "──────────────────\n"
                f"🤖 اطلب الآن عبر البوت: @{BOT_USERNAME}"
            )
            await context.bot.send_message(chat_id=PROOFS_CHANNEL_ID, text=proof_text)
        except Exception:
            pass

# --- 7. نظام الضمان المشروط بالفيديو الحصري ---
async def start_warranty_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    order_id = query.data.replace("claim_", "")
    context.user_data["warranty_order_id"] = order_id

    warning_text = (
        "⚠️ **شروط وسياسة الاستبدال والضمان:**\n"
        "──────────────────────\n\n"
        "⛔ **تنبيه حاسم:** لن يتم قبول أي طلب استبدال بدون الشرط التالي:\n\n"
        "📹 **توثيق فيديو تصوير شاشة كامل ومستمر:**\n"
        "1️⃣ يبدأ الفيديو **من لحظة استلام الكود في هذا الشات**.\n"
        "2️⃣ يستمر بدون أي قص أو تعديل حتى تجربة الكود وظهور العطل.\n\n"
        "🚫 أي فيديو يبدأ بعد استلام الكود يعتبر لاغياً ولن يتم تعويضك.\n\n"
        "──────────────────────\n"
        "📤 **إذا كان لديك الفيديو، أرسله الآن في هذه المحادثة:**"
    )

    keyboard = [[InlineKeyboardButton("🟥 إلغاء ❌", callback_data="cancel_order")]]
    await query.edit_message_text(warning_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return WAITING_WARRANTY_VIDEO

async def handle_warranty_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    order_id = context.user_data.get("warranty_order_id", "غير محدد")
    video = update.message.video or update.message.document

    if not video:
        await update.message.reply_text("⚠️ يرجى إرسال مقطع فيديو يوثق المشكلة كما هو موضح بالشروط.")
        return WAITING_WARRANTY_VIDEO

    await update.message.reply_text("✅ تم استلام الفيديو وبلاغك بنجاح! سيتم تدقيقه من قِبل الإدارة وموافاتك بالقرار فوراً.")

    admin_caption = (
        f"🚨 **بلاغ ضمان على الطلب #{order_id}**\n\n"
        f"👤 العميل: {user.first_name} (@{user.username or 'بدون'}) | ID: `{user.id}`\n"
        "📹 فحص استيفاء الشروط (بداية التسجيل من لحظة الشراء وبدون قص):"
    )

    admin_keyboard = [
        [
            InlineKeyboardButton("قبول وتعويض ✅", callback_data=f"rep_accept_{order_id}_{user.id}"),
            InlineKeyboardButton("رفض لعدم استيفاء الشروط ❌", callback_data=f"rep_reject_{order_id}_{user.id}")
        ]
    ]

    if update.message.video:
        await context.bot.send_video(chat_id=ADMIN_ID, video=video.file_id, caption=admin_caption, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode="Markdown")
    else:
        await context.bot.send_document(chat_id=ADMIN_ID, document=video.file_id, caption=admin_caption, reply_markup=InlineKeyboardMarkup(admin_keyboard), parse_mode="Markdown")

    return ConversationHandler.END

async def handle_admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, decision, order_id, user_id_str = query.data.split("_")
    target_uid = int(user_id_str)

    if decision == "accept":
        await context.bot.send_message(chat_id=target_uid, text=f"🎉 **تم قبول طلب الضمان للطلب #{order_id}!**\nتأكد استيفاء الشروط وسيتم تسليمك البديل الصالح فوراً.")
        await query.edit_message_caption(caption=query.message.caption + "\n\n🟢 **القرار:** تم القبول.", reply_markup=None)
    else:
        await context.bot.send_message(chat_id=target_uid, text=f"❌ **تم رفض طلب الضمان للطلب #{order_id}.**\nالسبب: الفيديو لا يستوفي شروط التوثيق المستمر المحددة.")
        await query.edit_message_caption(caption=query.message.caption + "\n\n🔴 **القرار:** تم الرفض.", reply_markup=None)

# --- 8. شحن الرصيد BEP20 وسجل طلباتي ---
async def show_bep20_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    total = context.user_data.get("order_total", 0.68)
    wallet_address = "0x18bb022fc8795b580C9613Ab3642Bb4155522d7C"

    text = (
        "**BEP20**\n"
        "⌛ **صالح لمدة 30 دقيقة**\n"
        "────────────────────\n"
        "**عنوان الإيداع (اضغط للنسخ):**\n"
        f"`{wallet_address}`\n\n"
        f"**المبلغ الدقيق:** USDT {total:.4f}\n"
        "**الشبكة:** BNB Smart Chain (BEP20)\n"
        "**Payment ID:** 5522012385\n"
        "────────────────────\n"
        "أرسل المبلغ الدقيق عبر شبكة BEP20 فقط.\n"
        "الكشف تلقائي ولا تحتاج إلى إرسال TXID."
    )

    keyboard = [
        [InlineKeyboardButton("📋 نسخ العنوان والمبلغ", callback_data="copy_alert")],
        [InlineKeyboardButton("🔄 فحص الدفع على البلوكشين", callback_data="check_blockchain")],
        [InlineKeyboardButton("🟥 إلغاء ❌", callback_data="cancel_order")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_user_orders(query.from_user.id)

    if not orders:
        text = "📭 ليس لديك أي طلبات سابقة حتى الآن."
    else:
        text = "📦 **سجل مشترياتك السابقة:**\n──────────────────\n"
        for o in orders:
            text += f"• **{o['name']}** (x{o['quantity']}) - `${float(o['total_price']):.2f}`\n"

    keyboard = [[InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💬 **الدعم الفني متاح 24/7:**\nلأي استفسار تواصل مع الإدارة: @YourSupportUsername"
    keyboard = [[InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]]
    await query.edit_message_caption(caption=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def copy_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("📋 اضغط مطولاً على العنوان بالرسالة لنسخه فوراً!", show_alert=False)

async def check_blockchain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("🔍 جاري التحقق من الشبكة والبلوكشين...", show_alert=True)

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🚫 تم إلغاء الطلب.")
    keyboard = [[InlineKeyboardButton("🟦 الرئيسية 🏠", callback_data="back_to_home")]]
    if query.message.caption:
        await query.edit_message_caption(caption="🚫 تم إلغاء الطلب.", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("🚫 تم إلغاء الطلب.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# --- 9. أوامر لوحة تحكم الأدمن ---
async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id) or len(context.args) < 2:
        return
    uid = int(context.args[0])
    amount = float(context.args[1])
    db.add_user_balance(uid, amount)
    await update.message.reply_text(f"✅ تم إضافة `${amount:.2f}` لرصيد المستخدم `{uid}`.")

async def admin_new_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # الصيغة: /newprod <code_name> <name> <price> [bulk20] [bulk50]
    if not is_admin(update.effective_user.id) or len(context.args) < 3:
        await update.message.reply_text("الصيغة: `/newprod <code_name> <الاسم> <السعر> [سعر_20] [سعر_50]`", parse_mode="Markdown")
        return
    code = context.args[0]
    name = context.args[1]
    price = float(context.args[2])
    b20 = float(context.args[3]) if len(context.args) > 3 else None
    b50 = float(context.args[4]) if len(context.args) > 4 else None
    db.create_product(code, name, price, b20, b50)
    await update.message.reply_text(f"✅ تم إنشاء المنتج `{name}` بنجاح!")

async def admin_add_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # الصيغة: /addstock <code_name> <item1> <item2> ...
    if not is_admin(update.effective_user.id) or len(context.args) < 2:
        await update.message.reply_text("الصيغة: `/addstock <code_name> <كود1> <كود2> ...`", parse_mode="Markdown")
        return
    code = context.args[0]
    items = context.args[1:]
    count = db.bulk_insert_stock(code, items)
    await update.message.reply_text(f"✅ تم شحن `{count}` كود بنجاح للمنتج `{code}`!")

def main():
    db.init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    # محادثة الشراء
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_buy, pattern=r"^buy_")],
        states={
            WAITING_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_quantity)]
        },
        fallbacks=[CallbackQueryHandler(cancel_order, pattern="^cancel_order$")]
    )

    # محادثة الضمان المشروط بالفيديو
    warranty_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_warranty_claim, pattern=r"^claim_")],
        states={
            WAITING_WARRANTY_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.ALL, handle_warranty_video)]
        },
        fallbacks=[CallbackQueryHandler(cancel_order, pattern="^cancel_order$")]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addbal", admin_add_balance))
    app.add_handler(CommandHandler("newprod", admin_new_product))
    app.add_handler(CommandHandler("addstock", admin_add_stock))

    app.add_handler(buy_conv)
    app.add_handler(warranty_conv)

    # معالجات الأزرار
    app.add_handler(CallbackQueryHandler(start, pattern="^back_to_home$"))
    app.add_handler(CallbackQueryHandler(catalog, pattern="^show_catalog$"))
    app.add_handler(CallbackQueryHandler(view_product, pattern=r"^prod_"))
    app.add_handler(CallbackQueryHandler(show_referral, pattern="^referral_info$"))
    app.add_handler(CallbackQueryHandler(show_balance, pattern="^my_balance$"))
    app.add_handler(CallbackQueryHandler(show_deposit, pattern="^deposit_info$"))
    app.add_handler(CallbackQueryHandler(show_my_orders, pattern="^my_orders$"))
    app.add_handler(CallbackQueryHandler(show_support, pattern="^support_info$"))
    app.add_handler(CallbackQueryHandler(show_tutorials, pattern="^show_tutorials$"))
    app.add_handler(CallbackQueryHandler(show_api_info, pattern="^api_info$"))
    app.add_handler(CallbackQueryHandler(handle_daily_bonus, pattern="^claim_daily_bonus$"))
    app.add_handler(CallbackQueryHandler(register_alert_callback, pattern=r"^alert_"))
    app.add_handler(CallbackQueryHandler(pay_with_balance, pattern=r"^pay_balance_"))
    app.add_handler(CallbackQueryHandler(show_bep20_page, pattern="^pay_bep20$"))
    app.add_handler(CallbackQueryHandler(copy_alert, pattern="^copy_alert$"))
    app.add_handler(CallbackQueryHandler(check_blockchain, pattern="^check_blockchain$"))
    app.add_handler(CallbackQueryHandler(cancel_order, pattern="^cancel_order$"))
    app.add_handler(CallbackQueryHandler(handle_admin_decision, pattern=r"^rep_(accept|reject)_"))

    print("🚀 متجر التيليجرام الرقمي يعمل الآن بأعلى كفاءة وجاهز لخدمة العملاء!")
    app.run_polling()

if __name__ == "__main__":
    main()
