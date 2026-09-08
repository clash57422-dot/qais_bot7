import os
import time
import json
import uuid
import hmac
import hashlib
import logging
import asyncio
import aiosqlite
import aiohttp
from datetime import datetime
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# ---------------------------------------------------------
# 1. Configuration & Personal Setup
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8466390738:AAF_N1sYQp8fUZY0X6gnwUP8ixf7Rw2sO2g")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8556501768"))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@qais_storee")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "https://t.me/qais_storeee")
BINANCE_PAY_KEY = os.getenv("BINANCE_PAY_KEY", "ZlE5htIUI0DIKD6IZgcO95THLlEsolsWiGiAHEwHIR15E7h51cZnXm8jquHtkgvt")
BINANCE_PAY_SECRET = os.getenv("BINANCE_PAY_SECRET", "nV95yafCNM80hohP8gLj6Y7zBzyV5JDeHH1iFE9NSiYOsLdW6Y1OMB7tu6k5H7O2")
PORT = int(os.getenv("PORT", 8080))

DB_FILE = "qais_store.db"

# Conversation states
ADD_CAT_NAME, ADD_PROD_CAT, ADD_PROD_NAME, ADD_OPT_DAYS, ADD_OPT_PRICE, USER_ACTION_INPUT, EDIT_MSG_INPUT = range(7)

# Default Fallback Texts
DEFAULT_TEXTS = {
    "ar": {
        "welcome": "أهلاً بك في متجر QAIS STORE 🛍️\nرصيدك الحالي: `{balance}` USDT",
        "btn_products": "🛒 الألعاب والمنتجات",
        "btn_profile": "👤 الملف الشخصي",
        "btn_orders": "📜 سجل الطلبات",
        "btn_support": "🛠️ الدعم الفني",
        "btn_lang": "🌐 Change Language / تغيير اللغة",
        "sub_required": "⚠️ يجب عليك الاشتراك بالقناة أولاً لاستخدام البوت:",
        "btn_sub": "📢 اشترك بالقناة",
        "btn_verify_sub": "✅ تحقق من الاشتراك",
        "sub_success": "✅ تم التأكد من الاشتراك بنجاح!",
        "sub_failed": "❌ لم تشترك بالقناة بعد!",
        "banned": "❌ حسابك محظور من استخدام البوت.",
        "profile_title": "👤 **الملف الشخصي للعميل**\n\n🆔 **الآيدي:** `{user_id}`\n💰 **الرصيد المتاح:** `{balance}` USDT\n📦 **إجمالي الطلبات:** `{order_count}` طلبات\n📅 **تاريخ الانضمام:** `{joined_at}`",
        "no_orders": "📜 **سجل الشراء:**\n\nلا يوجد لديك أي طلبات سابقة.",
        "orders_title": "📜 **أحدث طلباتك:**\n\n",
        "back": "🔙 العودة",
        "select_cat": "اختر القسم المطلوب:",
        "select_prod": "اختر المنتج المطلوب:",
        "select_opt": "اختر المدة والسعر المناسب:",
        "select_pay": "المنتج: {name}\nالمدة: {days} يوم\nالسعر: {price} USDT\n\nاختر طريقة الدفع المناسبة:",
        "pay_wallet": "💳 دفع من المحفظة ({balance} USDT)",
        "pay_binance": "⚡ دفع مباشر Binance Pay",
        "pay_success": "✅ تم الشراء بنجاح!\nالمنتج: {name}\nالمدة: {days} يوم\nتم خصم {price} USDT من رصيدك.",
        "insufficient_balance": "❌ رصيدك غير كافٍ للشراء!",
        "cancel": "❌ إلغاء",
        "lang_changed": "🌐 تم تغيير اللغة إلى العربية بنجاح!"
    },
    "en": {
        "welcome": "Welcome to QAIS STORE 🛍️\nYour Balance: `{balance}` USDT",
        "btn_products": "🛒 Games & Products",
        "btn_profile": "👤 Profile",
        "btn_orders": "📜 Order History",
        "btn_support": "🛠️ Technical Support",
        "btn_lang": "🌐 Change Language / تغيير اللغة",
        "sub_required": "⚠️ You must subscribe to our channel to use the bot:",
        "btn_sub": "📢 Join Channel",
        "btn_verify_sub": "✅ Verify Subscription",
        "sub_success": "✅ Subscription verified successfully!",
        "sub_failed": "❌ You haven't joined the channel yet!",
        "banned": "❌ Your account has been banned.",
        "profile_title": "👤 **User Profile**\n\n🆔 **ID:** `{user_id}`\n💰 **Balance:** `{balance}` USDT\n📦 **Total Orders:** `{order_count}`\n📅 **Joined:** `{joined_at}`",
        "no_orders": "📜 **Order History:**\n\nNo previous orders found.",
        "orders_title": "📜 **Your Recent Orders:**\n\n",
        "back": "🔙 Back",
        "select_cat": "Select a category:",
        "select_prod": "Select a product:",
        "select_opt": "Select duration and price:",
        "select_pay": "Product: {name}\nDuration: {days} Days\nPrice: {price} USDT\n\nChoose payment method:",
        "pay_wallet": "💳 Pay via Wallet ({balance} USDT)",
        "pay_binance": "⚡ Pay via Binance Pay",
        "pay_success": "✅ Purchase Successful!\nProduct: {name}\nDuration: {days} Days\nDeducted: {price} USDT",
        "insufficient_balance": "❌ Insufficient wallet balance!",
        "cancel": "❌ Cancel",
        "lang_changed": "🌐 Language changed to English successfully!"
    }
}

# ---------------------------------------------------------
# 2. Database Initialization & Settings Control
# ---------------------------------------------------------
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                is_banned INTEGER DEFAULT 0,
                lang TEXT DEFAULT 'ar',
                joined_at TEXT,
                last_msg_id INTEGER DEFAULT 0
            )
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT NOT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS product_options (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, days INTEGER NOT NULL, price REAL NOT NULL)")
        await db.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_name TEXT, days INTEGER, price REAL, created_at TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS pending_payments (merchant_trade_no TEXT PRIMARY KEY, user_id INTEGER, amount REAL, option_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        
        # Populate default custom messages if missing
        for key in ["welcome_msg", "select_cat_msg", "select_prod_msg", "select_opt_msg"]:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as c:
                if not await c.fetchone():
                    default_val = {
                        "welcome_msg": DEFAULT_TEXTS["ar"]["welcome"],
                        "select_cat_msg": DEFAULT_TEXTS["ar"]["select_cat"],
                        "select_prod_msg": DEFAULT_TEXTS["ar"]["select_prod"],
                        "select_opt_msg": DEFAULT_TEXTS["ar"]["select_opt"]
                    }[key]
                    await db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, default_val))
        await db.commit()

async def get_setting(key: str, default: str) -> str:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as c:
            row = await c.fetchone()
            return row[0] if row else default

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                await db.execute("INSERT INTO users (user_id, lang, joined_at) VALUES (?, 'ar', ?)", (user_id, now))
                await db.commit()
                return {"user_id": user_id, "balance": 0.0, "is_banned": 0, "lang": "ar", "joined_at": now, "last_msg_id": 0}
            return dict(user)

async def set_user_last_msg(user_id: int, msg_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET last_msg_id = ? WHERE user_id = ?", (msg_id, user_id))
        await db.commit()

async def set_user_lang(user_id: int, lang: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()

async def update_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def record_order(user_id: int, product_name: str, days: int, price: float):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO orders (user_id, product_name, days, price, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, product_name, days, price, now))
        await db.commit()

async def set_ban_status(user_id: int, status: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, user_id))
        await db.commit()

# ---------------------------------------------------------
# 3. Binance Pay Integration
# ---------------------------------------------------------
def generate_binance_signature(timestamp: str, nonce: str, body: str) -> str:
    payload = f"{timestamp}\n{nonce}\n{body}\n"
    return hmac.new(BINANCE_PAY_SECRET.encode('utf-8'), payload.encode('utf-8'), hashlib.sha512).hexdigest().upper()

async def create_binance_order(amount: float, product_name: str):
    url = "https://bpay.binanceapi.com/binancepay/openapi/v2/order"
    nonce = str(uuid.uuid4()).replace("-", "")[:32]
    timestamp = str(int(time.time() * 1000))
    merchant_trade_no = f"TRD_{int(time.time())}_{uuid.uuid4().hex[:4]}"

    body_data = {
        "env": {"terminalType": "MINI_PROGRAM"},
        "merchantTradeNo": merchant_trade_no,
        "orderAmount": amount,
        "currency": "USDT",
        "goods": {"goodsType": "02", "goodsCategory": "Z000", "referenceGoodsId": "item_01", "goodsName": product_name}
    }
    json_body = json.dumps(body_data)
    sig = generate_binance_signature(timestamp, nonce, json_body)

    headers = {
        "Content-Type": "application/json",
        "BinancePay-Timestamp": timestamp,
        "BinancePay-Nonce": nonce,
        "BinancePay-Certificate-SN": BINANCE_PAY_KEY,
        "BinancePay-Signature": sig
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=json_body) as resp:
            res = await resp.json()
            if res.get("status") == "SUCCESS":
                return {"success": True, "url": res["data"]["universalUrl"], "trade_no": merchant_trade_no}
            return {"success": False}

async def check_binance_payment(merchant_trade_no: str) -> bool:
    url = "https://bpay.binanceapi.com/binancepay/openapi/v2/order/query"
    nonce = str(uuid.uuid4()).replace("-", "")[:32]
    timestamp = str(int(time.time() * 1000))

    body_data = {"merchantTradeNo": merchant_trade_no}
    json_body = json.dumps(body_data)
    sig = generate_binance_signature(timestamp, nonce, json_body)

    headers = {
        "Content-Type": "application/json",
        "BinancePay-Timestamp": timestamp,
        "BinancePay-Nonce": nonce,
        "BinancePay-Certificate-SN": BINANCE_PAY_KEY,
        "BinancePay-Signature": sig
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, data=json_body) as resp:
            res = await resp.json()
            if res.get("status") == "SUCCESS" and res["data"].get("status") == "PAID":
                return True
            return False

# ---------------------------------------------------------
# 4. Mandatory Subscription
# ---------------------------------------------------------
async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not CHANNEL_USERNAME or CHANNEL_USERNAME == "@YourChannel":
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return False

# ---------------------------------------------------------
# 5. UI Helpers & Main Bot Handlers
# ---------------------------------------------------------
def get_main_keyboard(lang: str):
    t = DEFAULT_TEXTS[lang]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t["btn_products"], callback_data="user_cats")],
        [InlineKeyboardButton(t["btn_profile"], callback_data="user_profile"), InlineKeyboardButton(t["btn_orders"], callback_data="user_orders")],
        [InlineKeyboardButton(t["btn_support"], url=f"https://t.me/{SUPPORT_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(t["btn_lang"], callback_data="switch_language")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    lang = user["lang"]
    t = DEFAULT_TEXTS[lang]

    # Clear previous menu if exists
    if user.get("last_msg_id"):
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=user["last_msg_id"])
        except Exception:
            pass

    if user["is_banned"]:
        msg = await update.message.reply_text(t["banned"])
        await set_user_last_msg(user_id, msg.message_id)
        return

    if not await is_subscribed(user_id, context):
        kbd = [
            [InlineKeyboardButton(t["btn_sub"], url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
            [InlineKeyboardButton(t["btn_verify_sub"], callback_data="check_sub")]
        ]
        msg = await update.message.reply_text(t["sub_required"], reply_markup=InlineKeyboardMarkup(kbd))
        await set_user_last_msg(user_id, msg.message_id)
        return

    welcome_tpl = await get_setting("welcome_msg", t["welcome"])
    welcome_text = welcome_tpl.format(balance=user["balance"])

    msg = await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard(lang))
    await set_user_last_msg(user_id, msg.message_id)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    user = await get_user(user_id)
    lang = user["lang"]
    t = DEFAULT_TEXTS[lang]

    if user["is_banned"]:
        await query.edit_message_text(t["banned"])
        return

    if data == "check_sub":
        if await is_subscribed(user_id, context):
            await query.edit_message_text(t["sub_success"])
            await start(update, context)
        else:
            await query.answer(t["sub_failed"], show_alert=True)

    elif data == "switch_language":
        new_lang = "en" if lang == "ar" else "ar"
        await set_user_lang(user_id, new_lang)
        t_new = DEFAULT_TEXTS[new_lang]
        welcome_tpl = await get_setting("welcome_msg", t_new["welcome"])
        await query.edit_message_text(t_new["lang_changed"])
        msg = await query.message.reply_text(welcome_tpl.format(balance=user["balance"]), parse_mode="Markdown", reply_markup=get_main_keyboard(new_lang))
        await set_user_last_msg(user_id, msg.message_id)

    elif data == "main_menu":
        welcome_tpl = await get_setting("welcome_msg", t["welcome"])
        await query.edit_message_text(welcome_tpl.format(balance=user["balance"]), parse_mode="Markdown", reply_markup=get_main_keyboard(lang))

    elif data == "user_profile":
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,)) as cursor:
                order_count = (await cursor.fetchone())[0]

        profile_text = t["profile_title"].format(user_id=user_id, balance=user["balance"], order_count=order_count, joined_at=user.get("joined_at", "N/A"))
        kbd = [
            [InlineKeyboardButton(t["btn_orders"], callback_data="user_orders")],
            [InlineKeyboardButton(t["back"], callback_data="main_menu")]
        ]
        await query.edit_message_text(profile_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "user_orders":
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user_id,)) as cursor:
                orders = await cursor.fetchall()

        if not orders:
            msg = t["no_orders"]
        else:
            msg = t["orders_title"]
            for idx, o in enumerate(orders, 1):
                msg += f"{idx}. **{o['product_name']}**\n   ⏳ المدة: {o['days']} أيام | 💵 السعر: {o['price']} USDT\n   📅 التاريـخ: `{o['created_at']}`\n---------------------\n"

        kbd = [[InlineKeyboardButton(t["back"], callback_data="main_menu")]]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kbd))

    elif data == "user_cats":
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM categories") as cursor:
                cats = await cursor.fetchall()
        
        kbd = [[InlineKeyboardButton(c['name'], callback_data=f"show_prods_{c['id']}")] for c in cats]
        kbd.append([InlineKeyboardButton(t["back"], callback_data="main_menu")])
        header = await get_setting("select_cat_msg", t["select_cat"])
        await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(kbd))

    elif data.startswith("show_prods_"):
        cat_id = int(data.split("_")[2])
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM products WHERE category_id = ?", (cat_id,)) as cursor:
                prods = await cursor.fetchall()
        
        kbd = [[InlineKeyboardButton(p['name'], callback_data=f"show_opts_{p['id']}")] for p in prods]
        kbd.append([InlineKeyboardButton(t["back"], callback_data="user_cats")])
        header = await get_setting("select_prod_msg", t["select_prod"])
        await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(kbd))

    elif data.startswith("show_opts_"):
        prod_id = int(data.split("_")[2])
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM product_options WHERE product_id = ?", (prod_id,)) as cursor:
                opts = await cursor.fetchall()

        kbd = [[InlineKeyboardButton(f"⏳ {o['days']} Days - 💵 {o['price']} USDT", callback_data=f"buy_opt_{o['id']}")] for o in opts]
        kbd.append([InlineKeyboardButton(t["back"], callback_data="user_cats")])
        header = await get_setting("select_opt_msg", t["select_opt"])
        await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(kbd))

    elif data.startswith("buy_opt_"):
        opt_id = int(data.split("_")[2])
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT o.*, p.name FROM product_options o JOIN products p ON o.product_id = p.id WHERE o.id = ?", (opt_id,)) as cursor:
                opt = await cursor.fetchone()

        kbd = [
            [InlineKeyboardButton(t["pay_wallet"].format(balance=user['balance']), callback_data=f"pay_wallet_{opt_id}")],
            [InlineKeyboardButton(t["pay_binance"], callback_data=f"pay_binance_{opt_id}")],
            [InlineKeyboardButton(t["cancel"], callback_data="main_menu")]
        ]
        await query.edit_message_text(t["select_pay"].format(name=opt['name'], days=opt['days'], price=opt['price']), reply_markup=InlineKeyboardMarkup(kbd))

    elif data.startswith("pay_wallet_"):
        opt_id = int(data.split("_")[2])
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT o.*, p.name FROM product_options o JOIN products p ON o.product_id = p.id WHERE o.id = ?", (opt_id,)) as cursor:
                opt = await cursor.fetchone()

        if user['balance'] < opt['price']:
            await query.answer(t["insufficient_balance"], show_alert=True)
            return

        await update_balance(user_id, -opt['price'])
        await record_order(user_id, opt['name'], opt['days'], opt['price'])
        await query.edit_message_text(t["pay_success"].format(name=opt['name'], days=opt['days'], price=opt['price']))

    elif data.startswith("pay_binance_"):
        opt_id = int(data.split("_")[2])
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT o.*, p.name FROM product_options o JOIN products p ON o.product_id = p.id WHERE o.id = ?", (opt_id,)) as cursor:
                opt = await cursor.fetchone()

        res = await create_binance_order(opt['price'], f"{opt['name']} - {opt['days']} Days")
        if res.get("success"):
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("INSERT INTO pending_payments VALUES (?, ?, ?, ?)", (res['trade_no'], user_id, opt['price'], opt_id))
                await db.commit()

            kbd = [
                [InlineKeyboardButton("🔗 Pay on Binance", url=res['url'])],
                [InlineKeyboardButton("✅ Confirm Payment", callback_data=f"verify_bpay_{res['trade_no']}")],
                [InlineKeyboardButton(t["cancel"], callback_data="main_menu")]
            ]
            await query.edit_message_text("اضغط للدفـع عبر Binance Pay ثم اضغط 'تأكيد الدفع':", reply_markup=InlineKeyboardMarkup(kbd))
        else:
            await query.answer("❌ تعذر الاتصال بـ Binance Pay.", show_alert=True)

    elif data.startswith("verify_bpay_"):
        trade_no = data.split("_")[2]
        if await check_binance_payment(trade_no):
            async with aiosqlite.connect(DB_FILE) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM pending_payments WHERE merchant_trade_no = ?", (trade_no,)) as cursor:
                    pay = await cursor.fetchone()
                await db.execute("DELETE FROM pending_payments WHERE merchant_trade_no = ?", (trade_no,))
                await db.commit()

            if pay:
                async with aiosqlite.connect(DB_FILE) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT o.*, p.name FROM product_options o JOIN products p ON o.product_id = p.id WHERE o.id = ?", (pay['option_id'],)) as cursor:
                        opt = await cursor.fetchone()

                await record_order(user_id, opt['name'], opt['days'], opt['price'])
                await query.edit_message_text("✅ تم الدفع وتسليم الطلب بنجاح!")
        else:
            await query.answer("❌ لم يتم العثور على الدفع بعد، يرجى المحاولة بعد إتمام التحويل.", show_alert=True)

# ---------------------------------------------------------
# 6. Admin Panel Implementation
# ---------------------------------------------------------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    kbd = [
        [InlineKeyboardButton("➕ إضافة قسم", callback_data="adm_add_cat"), InlineKeyboardButton("➕ إضافة منتج وخيارات", callback_data="adm_add_prod")],
        [InlineKeyboardButton("✏️ تعديل نصوص ورسائل القوائم", callback_data="adm_edit_msgs")],
        [InlineKeyboardButton("💰 تعديل رصيد", callback_data="adm_mod_bal"), InlineKeyboardButton("🚫 حظر / فك حظر", callback_data="adm_ban_user")],
        [InlineKeyboardButton("📊 إحصائيات المتجر", callback_data="adm_stats")]
    ]
    await update.message.reply_text("⚙️ **لوحة التحكم الشاملة للأدمن (QAIS STORE)**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kbd))

async def admin_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        return
    await query.answer()
    data = query.data

    if data == "adm_add_cat":
        await query.edit_message_text("أرسل الآن اسم القسم الجديد (مثلاً: فري فاير):")
        return ADD_CAT_NAME

    elif data == "adm_add_prod":
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM categories") as cursor:
                cats = await cursor.fetchall()

        if not cats:
            await query.edit_message_text("❌ يجب إضافة قسم أولاً!")
            return ConversationHandler.END

        kbd = [[InlineKeyboardButton(c['name'], callback_data=f"selcat_{c['id']}")] for c in cats]
        await query.edit_message_text("اختر القسم المراد إضافة المنتج له:", reply_markup=InlineKeyboardMarkup(kbd))
        return ADD_PROD_CAT

    elif data == "adm_edit_msgs":
        kbd = [
            [InlineKeyboardButton("تعديل رسالة الترحيب /start", callback_data="setmsg_welcome_msg")],
            [InlineKeyboardButton("تعديل نص اختيار الأقسام", callback_data="setmsg_select_cat_msg")],
            [InlineKeyboardButton("تعديل نص اختيار المنتجات", callback_data="setmsg_select_prod_msg")],
            [InlineKeyboardButton("تعديل نص اختيار الخيارات والمدد", callback_data="setmsg_select_opt_msg")]
        ]
        await query.edit_message_text("اختر النص المراد تعديله:", reply_markup=InlineKeyboardMarkup(kbd))
        return EDIT_MSG_INPUT

    elif data == "adm_mod_bal":
        context.user_data["admin_action"] = "bal"
        await query.edit_message_text("أرسل ID المستخدم والمبلغ بالشكل التالي:\n`USER_ID AMOUNT`\nمثال:\n`12345678 10` أو `12345678 -10`", parse_mode="Markdown")
        return USER_ACTION_INPUT

    elif data == "adm_ban_user":
        context.user_data["admin_action"] = "ban"
        await query.edit_message_text("أرسل ID المستخدم والحالة بالشكل التالي:\n`USER_ID 1` (حظر) أو `USER_ID 0` (فك الحظر)", parse_mode="Markdown")
        return USER_ACTION_INPUT

    elif data == "adm_stats":
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c1:
                u_count = (await c1.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1") as c2:
                b_count = (await c2.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM orders") as c3:
                o_count = (await c3.fetchone())[0]
        await query.edit_message_text(f"📊 **إحصائيات المتجر:**\n\n👥 عدد المستخدمين: {u_count}\n🚫 المحظورين: {b_count}\n📦 إجمالي الطلبات: {o_count}")

async def handle_edit_msg_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg_key = query.data.replace("setmsg_", "")
    context.user_data["target_msg_key"] = msg_key
    await query.edit_message_text("أرسل النص الجديد الآن (يمكنك استخدام `{balance}` في رسالة الترحيب):")
    return EDIT_MSG_INPUT

async def save_custom_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get("target_msg_key")
    new_text = update.message.text
    if key:
        await set_setting(key, new_text)
        await update.message.reply_text("✅ تم تحديث النص بنجاح!")
    return ConversationHandler.END

async def save_cat_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO categories (name) VALUES (?)", (name,))
        await db.commit()
    await update.message.reply_text(f"✅ تم إضافة القسم '{name}' بنجاح!")
    return ConversationHandler.END

async def sel_prod_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[1])
    context.user_data["new_prod_cat"] = cat_id
    await query.edit_message_text("أرسل الآن اسم المنتج:")
    return ADD_PROD_NAME

async def save_prod_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prod_name"] = update.message.text
    await update.message.reply_text("أرسل مدة الخيار بالـ أيام (مثال: 7):")
    return ADD_OPT_DAYS

async def save_opt_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_opt_days"] = int(update.message.text)
    await update.message.reply_text("أرسل سعر هذا الخيار بالـ USDT (مثال: 5.5):")
    return ADD_OPT_PRICE

async def save_opt_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = float(update.message.text)
    days = context.user_data["new_opt_days"]
    name = context.user_data["new_prod_name"]
    cat_id = context.user_data["new_prod_cat"]

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("INSERT INTO products (category_id, name) VALUES (?, ?)", (cat_id, name))
        prod_id = cursor.lastrowid
        await db.execute("INSERT INTO product_options (product_id, days, price) VALUES (?, ?, ?)", (prod_id, days, price))
        await db.commit()

    await update.message.reply_text("✅ تم حفظ المنتج والخيارات بنجاح!")
    return ConversationHandler.END

async def process_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("admin_action")
    text = update.message.text.split()

    if action == "bal" and len(text) == 2:
        uid, amt = int(text[0]), float(text[1])
        await update_balance(uid, amt)
        await update.message.reply_text(f"✅ تم تعديل رصيد المستخدم {uid} بمقدار {amt} USDT.")
    elif action == "ban" and len(text) == 2:
        uid, st = int(text[0]), int(text[1])
        await set_ban_status(uid, st)
        await update.message.reply_text(f"✅ تم تعديل حالة حظر {uid} إلى {st}.")
    else:
        await update.message.reply_text("❌ إدخال خاطئ!")

    return ConversationHandler.END

# ---------------------------------------------------------
# 7. Web Server for Render & Main Async Execution
# ---------------------------------------------------------
async def handle_ping(request):
    return web.Response(text="QAIS STORE Bot is up and running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/health', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Web server bound to port {PORT}")

async def main():
    await init_db()
    
    # Start Dummy Health Check Server for Render
    await start_web_server()

    app = Application.builder().token(BOT_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callbacks, pattern="^adm_")],
        states={
            ADD_CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_cat_name)],
            ADD_PROD_CAT: [CallbackQueryHandler(sel_prod_cat, pattern="^selcat_")],
            ADD_PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_prod_name)],
            ADD_OPT_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_opt_days)],
            ADD_OPT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_opt_price)],
            USER_ACTION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_action)],
            EDIT_MSG_INPUT: [
                CallbackQueryHandler(handle_edit_msg_select, pattern="^setmsg_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_custom_msg)
            ],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(handle_callbacks))

    logger.info("Bot execution started...")
    async with app:
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot execution stopped.")
