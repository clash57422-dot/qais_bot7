import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import threading
import time
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --- 1. سيرفر وهمي لتشغيل Render 24/7 ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"QAIS STORE Bot is Live and Running Perfectly 24/7!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# --- 2. الإعدادات والبيانات الأساسية ---
BOT_TOKEN = "8466390738:AAHMVZhjGaUuYZq0J-4RBFKZvJp9aVF-9R0"
ADMIN_CHAT_ID = 8556501768  # ID قيس فقط

REQUIRED_CHANNEL = "qais_storeee"
SUPPORT_USERNAME = "qais_storee"

BINANCE_PAY_ID = "1006208970"
USDT_WALLET = "0x409239a2a633f0627366f701c4ee3c2d5a9dac2a"
BINANCE_API_KEY = "Al7fywuuad77sluatuiq60kwv6k9p2rf4nuh7vgxiuboilntmwnlzt2nbfmlgprh"
BINANCE_SECRET_KEY = "wahitoge75wxgfss40o7p2hapkgwupelca65n3snr4qdou4rnep4xlaprlhzb8ab"

# قاعدة بيانات المنتجات الهيكلية (دعم الأيام والأسعار)
products_db = {
    "DRIP": {
        "name": "Drip Client",
        "options": {
            "1d": {"label": "يوم واحد (1 Day)", "price": 2.0, "seller_price": 1.5},
            "7d": {"label": "7 أيام (1 Week)", "price": 8.0, "seller_price": 6.0},
            "30d": {"label": "30 يوم (1 Month)", "price": 20.0, "seller_price": 15.0}
        }
    },
    "IOS": {
        "name": "تطبيقات IOS",
        "options": {
            "30d": {"label": "اشتراك شهر", "price": 10.0, "seller_price": 8.0}
        }
    }
}

user_balances = {}
ref_balances = {}
user_referrals = {}
sellers_list = set()
banned_users = set()
gift_codes = {}
user_orders = {}
user_data = {}
all_users = set()
used_txids = set()

bot_texts = {
    "welcome_ar": "👋 **أهلاً بك في QAIS STORE!**\n⭐ متجر الخدمات والتطبيقات المعدلة الممتازة\n⚡ تحقق وإيداع آلي 24/7",
    "welcome_en": "👋 **Welcome to QAIS STORE!**\n⭐ Premium Game Keys & Mod Tools\n⚡ Instant Verification 24/7",
    "support": f"💬 للتواصل مع الدعم الفني المباشر: @{SUPPORT_USERNAME}",
    "how_to": "📖 **طريقة الاستخدام:**\n1. اشحن محفظتك بـ USDT عبر بايننس.\n2. اختر الخدمة والمدة المناسبة.\n3. أدخل بريدك واستلم طلبك فوراً."
}

# --- 3. أدوات الفحص والدعم ---
async def check_subscription(user_id, context):
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await context.bot.get_chat_member(f"@{REQUIRED_CHANNEL}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return True

def check_binance_deposit(tx_id):
    url = "https://api.binance.com/sapi/v1/capital/deposit/hisrec"
    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"
    
    signature = hmac.new(
        BINANCE_SECRET_KEY.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    full_url = f"{url}?{query_string}&signature={signature}"
    
    try:
        response = requests.get(full_url, headers=headers, timeout=10)
        if response.status_code == 200:
            deposits = response.json()
            for deposit in deposits:
                if deposit.get('txId') == tx_id and deposit.get('status') == 1:
                    return float(deposit.get('amount', 0))
        return None
    except Exception as e:
        print(f"Binance Error: {e}")
        return None

def is_valid_amount(amount):
    return amount == 1.0 or (amount >= 5.0 and amount % 5.0 == 0)

def build_main_menu(lang, balance, user_id):
    is_seller = "👑 (حساب بائع)" if user_id in sellers_list else ""
    welcome_txt = bot_texts["welcome_en"] if lang == "en" else bot_texts["welcome_ar"]
    
    text = (
        f"🤖 **─── متجر قيس للخدمات ───** {is_seller}\n\n"
        f"{welcome_txt}\n\n"
        f"🆔 معرّفك الخاص: `{user_id}`\n"
        f"💰 رصيدك الحالي: **${balance:.2f}**\n"
        f"🎁 أرباح الإحالة: **${ref_balances.get(user_id, 0.0):.2f}**"
    )
    keyboard = [
        [InlineKeyboardButton("💎 الشراء الآن", callback_data="store")],
        [InlineKeyboardButton("📜 طلباتي", callback_data="my_orders"), InlineKeyboardButton("👑 الحساب الشخصي", callback_data="profile")],
        [InlineKeyboardButton("💳 إيداع رصيد", callback_data="deposit"), InlineKeyboardButton("🤝 نظام الإحالة", callback_data="referral")],
        [InlineKeyboardButton("🎁 استخدام كود شحن", callback_data="use_code")],
        [InlineKeyboardButton("📖 طريقة الاستخدام", callback_data="how_to"), InlineKeyboardButton("💬 الدعم الفني", callback_data="support")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# --- 4. بداية المحادثة ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id in banned_users: return

    all_users.add(user_id)
    user_balances.setdefault(user_id, 0.0)
    ref_balances.setdefault(user_id, 0.0)

    if context.args and user_id not in user_referrals:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and referrer_id in all_users:
                user_referrals[user_id] = referrer_id
        except Exception: pass

    if not await check_subscription(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📢 انضم للقناة الآن", url=f"https://t.me/{REQUIRED_CHANNEL}")],
            [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub")]
        ]
        await update.message.reply_text("⚠️ **اشترك بالقناة أولاً للاستخدام:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    lang = user_data.get(user_id, {}).get("lang", "ar")
    text, reply_markup = build_main_menu(lang, user_balances[user_id], user_id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# --- 5. لوحة التحكم المتطورة للأدمن (مع أزرار تفاعلية) ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return

    keyboard = [
        [InlineKeyboardButton("➕ إضافة منتج جديد", callback_data="admin_add_prod")],
        [InlineKeyboardButton("⚙️ إدارة المنتجات والأسعار", callback_data="admin_manage_prods")],
        [InlineKeyboardButton("💰 شحن رصيد لمستخدم", callback_data="admin_add_bal")],
        [InlineKeyboardButton("👑 ترقية بائع", callback_data="admin_set_seller"), InlineKeyboardButton("⛔ حظر مستخدم", callback_data="admin_ban")],
        [InlineKeyboardButton("🎁 إنشاء كود شحن", callback_data="admin_make_code")],
        [InlineKeyboardButton("📢 إذاعة عامة", callback_data="admin_broadcast")]
    ]
    
    msg = (
        "👑 **── لوحة تحكم الآدمن المتطورة (قيس) ──**\n\n"
        f"👥 المستخدمين: **{len(all_users)}** | ⛔ المحظورين: **{len(banned_users)}**\n"
        f"🏷️ البائعين: **{len(sellers_list)}** | 📦 المنتجات: **{len(products_db)}**\n\n"
        "اختر من القائمة أدناه للتحكم الشامل بكل سهولة:"
    )
    
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# --- 6. معالج الأزرار التفاعلية ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id in banned_users: return

    user_balances.setdefault(user_id, 0.0)
    ref_balances.setdefault(user_id, 0.0)
    user_data.setdefault(user_id, {})
    lang = user_data[user_id].get("lang", "ar")

    # --- أزرار الأدمن المتطورة ---
    if query.data == "admin_panel":
        await admin_panel(update, context)
        return

    elif query.data == "admin_add_prod":
        user_data[user_id]["state"] = "ADMIN_ADD_PROD_CODE"
        await query.edit_message_text("📝 **أدخل كود المنتج الجديد (مثال: FREEFIRE أو DRIP):**")
        return

    elif query.data == "admin_manage_prods":
        keyboard = []
        for code, item in products_db.items():
            keyboard.append([InlineKeyboardButton(f"📦 {item['name']} ({code})", callback_data=f"admin_view_prod_{code}")])
        keyboard.append([InlineKeyboardButton("🔙 العودة للوحة الأدمن", callback_data="admin_panel")])
        await query.edit_message_text("⚙️ **اختر المنتج لتعديله أو إضافة خيارات مدة/أسعار جديدة:**", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif query.data.startswith("admin_view_prod_"):
        code = query.data.split("_")[3]
        prod = products_db.get(code)
        if not prod: return
        
        msg = f"📦 **المنتج:** {prod['name']} (`{code}`)\n\n**الخيارات الحالية:**\n"
        keyboard = []
        for opt_key, opt_data in prod.get("options", {}).items():
            msg += f"• `{opt_key}`: {opt_data['label']} - عادي: ${opt_data['price']} | بائع: ${opt_data['seller_price']}\n"
            keyboard.append([InlineKeyboardButton(f"❌ حذف خيار {opt_key}", callback_data=f"admin_del_opt_{code}_{opt_key}")])
        
        keyboard.append([InlineKeyboardButton("➕ إضافة مدة/خيار سعر جديد", callback_data=f"admin_add_opt_{code}")])
        keyboard.append([InlineKeyboardButton("🗑️ حذف المنتج بالكامل", callback_data=f"admin_del_prod_{code}")])
        keyboard.append([InlineKeyboardButton("🔙 العودة للمنتجات", callback_data="admin_manage_prods")])
        
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif query.data.startswith("admin_add_opt_"):
        code = query.data.split("_")[3]
        user_data[user_id]["selected_prod"] = code
        user_data[user_id]["state"] = "ADMIN_ADD_OPT_KEY"
        await query.edit_message_text(f"➕ **إضافة خيار مدة لـ `{code}`**\n\nأرسل رمز الخيار (مثال: `1d` أو `7d` أو `30d`):", parse_mode="Markdown")
        return

    elif query.data.startswith("admin_del_opt_"):
        _, _, _, code, opt_key = query.data.split("_")
        if code in products_db and opt_key in products_db[code]["options"]:
            del products_db[code]["options"][opt_key]
            await query.answer("✅ تم حذف الخيار!")
            await button_handler(update, context) # إعادة تحميل
        return

    elif query.data.startswith("admin_del_prod_"):
        code = query.data.split("_")[3]
        if code in products_db:
            del products_db[code]
            await query.answer("🗑️ تم حذف المنتج بالكامل!")
        await admin_panel(update, context)
        return

    # --- متجر العميل وتصفح الخيارات ---
    elif query.data == "store":
        keyboard = []
        for code, item in products_db.items():
            keyboard.append([InlineKeyboardButton(f"📱 {item['name']}", callback_data=f"view_prod_{code}")])
        keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")])
        await query.edit_message_text("🛍️ **اختر الخدمة أو التطبيق المطلوب:**", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("view_prod_"):
        code = query.data.split("_")[2]
        item = products_db.get(code)
        if not item or not item.get("options"):
            await query.edit_message_text("❌ لا توجد خيارات متاحة لهذا المنتج حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data="store")]]))
            return

        is_seller = user_id in sellers_list
        keyboard = []
        for opt_key, opt_val in item["options"].items():
            price = opt_val['seller_price'] if is_seller else opt_val['price']
            tag = " 👑" if is_seller else ""
            btn_txt = f"⏱️ {opt_val['label']} - ${price:.2f}{tag}"
            keyboard.append([InlineKeyboardButton(btn_txt, callback_data=f"buy_{code}_{opt_key}")])

        keyboard.append([InlineKeyboardButton("🔙 العودة للمتجر", callback_data="store")])
        txt = f"🛍️ **خدمة {item['name']}**\nاختر المدة أو الخيار المناسب لك:"
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("buy_"):
        _, code, opt_key = query.data.split("_")
        item = products_db.get(code, {})
        opt = item.get("options", {}).get(opt_key)

        if not opt: return
        is_seller = user_id in sellers_list
        price = opt['seller_price'] if is_seller else opt['price']

        if user_balances[user_id] < price:
            await query.edit_message_text(
                f"❌ رصيدك غير كافٍ!\nالمطلوب: **${price:.2f}** | رصيدك: **${user_balances[user_id]:.2f}**",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 إيداع رصيد الآن", callback_data="deposit")]])
            )
        else:
            user_data[user_id]["buy_code"] = code
            user_data[user_id]["buy_opt"] = opt_key
            user_data[user_id]["state"] = "WAITING_EMAIL"
            await query.edit_message_text(f"🛒 اخترت: **{item['name']} ({opt['label']})**\n💰 السعر: **${price:.2f}**\n\n📧 أرسل البريد الإلكتروني لتسلم الطلب:")

    elif query.data == "deposit":
        user_data[user_id]["state"] = "WAITING_TXID"
        msg = f"💳 **قسم الشحن الآلي:**\n\n• **Binance Pay ID:** `{BINANCE_PAY_ID}`\n• **USDT (BEP20):** `{USDT_WALLET}`\n\nأرسل رمز الحوالة (TxID) هنا:"
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data="main_menu")]]))

    elif query.data == "main_menu":
        user_data[user_id]["state"] = None
        text, reply_markup = build_main_menu(lang, user_balances[user_id], user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# --- 7. معالجة إدخالات النصوص والمراحل ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users: return

    text = update.message.text.strip()
    state = user_data.get(user_id, {}).get("state")

    # إضافة منتج جديد - خطوة 1
    if state == "ADMIN_ADD_PROD_CODE":
        code = text.upper()
        user_data[user_id]["temp_code"] = code
        user_data[user_id]["state"] = "ADMIN_ADD_PROD_NAME"
        await update.message.reply_text(f"أدخل اسم المنتج بالكامل لـ `{code}`:")
        return

    # إضافة منتج جديد - خطوة 2
    elif state == "ADMIN_ADD_PROD_NAME":
        code = user_data[user_id]["temp_code"]
        products_db[code] = {"name": text, "options": {}}
        user_data[user_id]["state"] = None
        await update.message.reply_text(f"🎉 تم إنشاء المنتج `{code}` بنجاح! يمكنك الآن إضافة خيارات مدة وأسعار من لوحة التحكم.", parse_mode="Markdown")
        return

    # إضافة مدة وخيار للمنتج
    elif state == "ADMIN_ADD_OPT_KEY":
        user_data[user_id]["temp_opt_key"] = text
        user_data[user_id]["state"] = "ADMIN_ADD_OPT_LABEL"
        await update.message.reply_text("أدخل نص الخيار والمدة (مثال: `30 يوم (شهر)`):")
        return

    elif state == "ADMIN_ADD_OPT_LABEL":
        user_data[user_id]["temp_opt_label"] = text
        user_data[user_id]["state"] = "ADMIN_ADD_OPT_PRICES"
        await update.message.reply_text("أدخل السعر العادي ثم سعر البائع يفصل بينهما مسافة (مثال: `10 8`):")
        return

    elif state == "ADMIN_ADD_OPT_PRICES":
        try:
            p_norm, p_sell = map(float, text.split())
            code = user_data[user_id]["selected_prod"]
            opt_key = user_data[user_id]["temp_opt_key"]
            label = user_data[user_id]["temp_opt_label"]

            products_db[code]["options"][opt_key] = {
                "label": label, "price": p_norm, "seller_price": p_sell
            }
            user_data[user_id]["state"] = None
            await update.message.reply_text("✅ تم إضافة خيار السعر والمدة بنجاح!")
        except Exception:
            await update.message.reply_text("⚠️ خطأ في كتابة الأسعار! اكتب رقمين بينهما مسافة (مثال: 10 8).")
        return

    # الشراء واستلام الايميل
    elif state == "WAITING_EMAIL":
        if "@" in text and "." in text:
            code = user_data[user_id].get("buy_code")
            opt_key = user_data[user_id].get("buy_opt")
            item = products_db.get(code, {})
            opt = item.get("options", {}).get(opt_key, {})

            is_seller = user_id in sellers_list
            price = opt.get("seller_price", opt.get("price", 0)) if is_seller else opt.get("price", 0)

            user_balances[user_id] -= price
            user_data[user_id]["state"] = None

            order_info = f"• {item.get('name')} ({opt.get('label')}) | ${price:.2f} | الإيميل: `{text}`"
            user_orders.setdefault(user_id, []).append(order_info)

            await update.message.reply_text(f"✅ **تم تنفيذ الطلب بنجاح!**\nالخدمة: {item.get('name')} - {opt.get('label')}\nالإيميل: `{text}`", parse_mode="Markdown")
            await context.bot.send_message(ADMIN_CHAT_ID, f"📦 **طلب جديد!**\n👤 العميل: `{user_id}`\n🛒 الخدمة: {item.get('name')} ({opt.get('label')})\n📧 الإيميل: `{text}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ البريد الإلكتروني غير صحيح!")

# --- 8. التشغيل ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("Bot is fully live and updated...")
    app.run_polling()
