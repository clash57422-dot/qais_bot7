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

# --- 1. سيرفر وهمي لتشغيل Render مجاناً 24/7 ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"QAIS STORE Bot is Live and Running Perfectly!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# --- 2. البيانات الأساسية والإعدادات ---
BOT_TOKEN = "8466390738:AAFLuzHub_ijth8G8DeKzV3moQ4afafIiZo"
ADMIN_CHAT_ID = 8556501768  # ID قيس فقط

REQUIRED_CHANNEL = "qais_storeee"  # قناة الاشتراك الإجباري بدون @
SUPPORT_USERNAME = "qais_storee"    # حساب الدعم الفني

BINANCE_PAY_ID = "1006208970"
USDT_WALLET = "0x409239a2a633f0627366f701c4ee3c2d5a9dac2a"

BINANCE_API_KEY = "Al7fywuuad77sluatuiq60kwv6k9p2rf4nuh7vgxiuboilntmwnlzt2nbfmlgprh"
BINANCE_SECRET_KEY = "wahitoge75wxgfss40o7p2hapkgwupelca65n3snr4qdou4rnep4xlaprlhzb8ab"

# قاعدة بيانات المنتجات (سعر عادي وسعر البائعين)
products_db = {
    "APKMOD": {"name": "تطبيقات APKMOD", "price": 5.0, "seller_price": 4.0},
    "IOS": {"name": "تطبيقات IOS", "price": 10.0, "seller_price": 8.0},
    "ROOT": {"name": "خدمات ROOT", "price": 15.0, "seller_price": 12.0}
}

# قواعد البيانات في الذاكرة
user_balances = {}       # الرصيد الرئيسي
ref_balances = {}        # رصيد الإحالة
user_referrals = {}      # من أحال من (New_ID: Ref_ID)
sellers_list = set()     # قائمة الـ IDs المعتمدة كبائعين
banned_users = set()     # قائمة الحظر
gift_codes = {}          # أكواد الشحن {"CODE": Amount}
user_orders = {}         # سجل الطلبات لكل مستخدم
user_data = {}
all_users = set()
used_txids = set()

# النصوص
bot_texts = {
    "welcome_ar": "👋 **أهلاً بك في QAIS STORE!**\n⭐ متجر الخدمات والتطبيقات المعدلة الممتازة\n⚡ تحقق وإيداع آلي 24/7",
    "welcome_en": "👋 **Welcome to QAIS STORE!**\n⭐ Premium Game Keys & Mod Tools\n⚡ Instant Verification 24/7",
    "support": f"💬 للتواصل مع الدعم الفني المباشر: @{SUPPORT_USERNAME}",
    "how_to": "📖 **طريقة الاستخدام:**\n1. اشحن محفظتك بـ USDT عبر بايننس.\n2. اختر الخدمة من المتجر.\n3. أدخل بريدك واستلم طلبك فوراً."
}

# --- 3. التحقق من الاشتراك وبايننس ---
async def check_subscription(user_id, context):
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await context.bot.get_chat_member(f"@{REQUIRED_CHANNEL}", user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return True  # تجنب التعليق في حال عدم وجود البوت كأدمن بالقناة

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

# --- 4. بناء القوائم الرئيسية ---
def build_main_menu(lang, balance, user_id):
    is_seller = "👑 (حساب بائع)" if user_id in sellers_list else ""
    welcome_txt = bot_texts["welcome_en"] if lang == "en" else bot_texts["welcome_ar"]
    
    if lang == "en":
        text = (
            f"🤖 **─── QAIS Gaming Store ───** {is_seller}\n\n"
            f"{welcome_txt}\n\n"
            f"🆔 Your ID: `{user_id}`\n"
            f"💰 Balance: **${balance:.2f}**\n"
            f"🎁 Ref Balance: **${ref_balances.get(user_id, 0.0):.2f}**"
        )
        keyboard = [
            [InlineKeyboardButton("💎 Shop Now", callback_data="store")],
            [InlineKeyboardButton("📜 My Orders", callback_data="my_orders"), InlineKeyboardButton("👑 Profile", callback_data="profile")],
            [InlineKeyboardButton("💳 Add Balance", callback_data="deposit"), InlineKeyboardButton("🤝 Referral System", callback_data="referral")],
            [InlineKeyboardButton("🎁 Redeem Gift Code", callback_data="use_code")],
            [InlineKeyboardButton("📖 How to Use", callback_data="how_to"), InlineKeyboardButton("💬 Support", callback_data="support")],
            [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
        ]
    else:
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
            [InlineKeyboardButton("📖 طريقة الاستخدام", callback_data="how_to"), InlineKeyboardButton("💬 الدعم الفني", callback_data="support")],
            [InlineKeyboardButton("🇸🇦 العربية", callback_data="lang_ar"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")]
        ]
        
    return text, InlineKeyboardMarkup(keyboard)

# --- 5. بداية التعامل مع المستخدم والاشتراك الإجباري ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if user_id in banned_users:
        return

    all_users.add(user_id)
    user_balances.setdefault(user_id, 0.0)
    ref_balances.setdefault(user_id, 0.0)

    # التسجيل عبر رابط الإحالة
    if context.args and user_id not in user_referrals:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id and referrer_id in all_users:
                user_referrals[user_id] = referrer_id
                await context.bot.send_message(
                    referrer_id, 
                    f"🎉 **انضم مستخدم جديد عبر رابط إحالتك!**\n🆔 المستخدم: `{user_id}`\nستحصل على 10% من كافة مشترياته المستقبليّة.",
                    parse_mode="Markdown"
                )
        except Exception:
            pass

    # فحص الاشتراك الإجباري
    if not await check_subscription(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📢 انضم للقناة الآن", url=f"https://t.me/{REQUIRED_CHANNEL}")],
            [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "⚠️ **عذراً يا الغالي! لازم تشترك بقناة المتجر أولاً عشان تقدر تستخدم البوت:**\n\nاضغط على الزر بالأسفل وبعد الانضمام اضغط تحقق:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if user_id not in user_data or "lang" not in user_data[user_id]:
        keyboard = [[
            InlineKeyboardButton("🇸🇦 العربية", callback_data="init_lang_ar"),
            InlineKeyboardButton("🇬🇧 English", callback_data="init_lang_en")
        ]]
        await update.message.reply_text(
            "👋 **مرحباً بك! اختر اللّغة للبدء / Welcome! Select language:**",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    lang = user_data[user_id].get("lang", "ar")
    text, reply_markup = build_main_menu(lang, user_balances[user_id], user_id)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# --- 6. لوحة تحكّم الأدمن الشاملة والسرية ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return  # يتجاهل أي شخص آخر حماية مطلقاً

    msg = (
        "👑 **── لوحة تحكم الآدمن الشاملة (قيس) ──**\n\n"
        f"👥 المستخدمين: **{len(all_users)}** | ⛔ المحظورين: **{len(banned_users)}**\n"
        f"🏷️ البائعين المعتمدين: **{len(sellers_list)}**\n"
        f"📢 القناة الإجبارية: **@{REQUIRED_CHANNEL}**\n\n"
        "🛠️ **الأوامر المتاحة:**\n"
        "• `/addproduct [رمز] [اسم_بدون_مسافات] [سعر_عادي] [سعر_بائع]` - إضافة/تحديث منتج\n"
        "• `/delproduct [رمز]` - حذف منتج\n"
        "• `/addbalance [User_ID] [المبلغ]` - شحن رصيد\n"
        "• `/setseller [User_ID]` - تحويل إلى حساب بائع\n"
        "• `/delseller [User_ID]` - إزالة رتبة بائع\n"
        "• `/ban [User_ID]` | `/unban [User_ID]` - حظر/فك حظر\n"
        "• `/makecode [الرمز] [المبلغ]` - إنشاء كود شحن\n"
        "• `/broadcast [الرسالة]` - إذاعة عامة للكل\n\n"
        "📦 **المنتجات الحالية:**\n"
    )
    for code, item in products_db.items():
        msg += f"• `{code}` | {item['name']} - عادي: **${item['price']}** | بائع: **${item.get('seller_price', item['price'])}**\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        code = context.args[0].upper()
        name = context.args[1].replace("_", " ")
        price = float(context.args[2])
        seller_price = float(context.args[3]) if len(context.args) > 3 else price
        products_db[code] = {"name": name, "price": price, "seller_price": seller_price}
        await update.message.reply_text(f"🎉 تم إضافة/تحديث المنتج `{code}` ({name})\nعادي: **${price}** | بائع: **${seller_price}**")
    except Exception:
        await update.message.reply_text("⚠️ استخدام خاطئ!\nمثال: `/addproduct PROXY DRIP_Proxy 5.0 4.0`", parse_mode="Markdown")

async def del_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        code = context.args[0].upper()
        if code in products_db:
            del products_db[code]
            await update.message.reply_text(f"🗑️ تم حذف المنتج `{code}` بنجاح!")
        else:
            await update.message.reply_text("❌ المنتج غير موجود!")
    except Exception:
        await update.message.reply_text("⚠️ استخدام خاطئ!\nمثال: `/delproduct APKMOD`", parse_mode="Markdown")

async def add_balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
        user_balances[target_id] = user_balances.get(target_id, 0.0) + amount
        await update.message.reply_text(f"💰 تم إضافة **${amount}** لـ `{target_id}`!")
        await context.bot.send_message(target_id, f"🎉 **تم إضافة رصيد إلى حسابك!**\nالمبلغ المضاف: **${amount:.2f}**\nرصيدك الحالي: **${user_balances[target_id]:.2f}**", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("⚠️ استخدام خاطئ!\nمثال: `/addbalance 12345678 10`", parse_mode="Markdown")

async def set_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        target_id = int(context.args[0])
        sellers_list.add(target_id)
        await update.message.reply_text(f"👑 تم إعطاء رتبة **بائع** للمستخدم `{target_id}` بنجاح!")
        await context.bot.send_message(target_id, "🎉 **مبارك! تم ترقية حسابك إلى رتبة بائع.**\nستحصل الآن على أسعار الموزعين المنخفضة داخل المتجر تلقائياً!")
    except Exception:
        await update.message.reply_text("⚠️ استخدام خاطئ!\nمثال: `/setseller 12345678`", parse_mode="Markdown")

async def del_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        target_id = int(context.args[0])
        sellers_list.discard(target_id)
        await update.message.reply_text(f"تم سحب رتبة البائع من `{target_id}`.")
    except Exception:
        await update.message.reply_text("⚠️ استخدام خاطئ!\nمثال: `/delseller 12345678`", parse_mode="Markdown")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        target_id = int(context.args[0])
        banned_users.add(target_id)
        await update.message.reply_text(f"⛔ تم حظر المستخدم `{target_id}`.")
    except Exception:
        await update.message.reply_text("⚠️ اكتب الـ ID بعد الأمر.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        target_id = int(context.args[0])
        banned_users.discard(target_id)
        await update.message.reply_text(f"✅ تم فك الحظر عن `{target_id}`.")
    except Exception:
        await update.message.reply_text("⚠️ اكتب الـ ID بعد الأمر.")

async def make_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    try:
        code = context.args[0]
        amount = float(context.args[1])
        gift_codes[code] = amount
        await update.message.reply_text(f"🎁 تم إنشاء كود شحن: `{code}` بقيمة **${amount:.2f}**", parse_mode="Markdown")
    except Exception:
        await update.message.reply_text("⚠️ مثال: `/makecode GIFT10 10`", parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID: return
    msg_text = " ".join(context.args)
    if not msg_text: return
    count = 0
    for uid in all_users:
        try:
            await context.bot.send_message(uid, f"📢 **تنويه إداري:**\n\n{msg_text}", parse_mode="Markdown")
            count += 1
        except Exception: pass
    await update.message.reply_text(f"✅ تم إرسال الإذاعة إلى **{count}** مستخدم!")

# --- 7. معالجة الأزرار والتفاعلات ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id

    if user_id in banned_users: return

    user_balances.setdefault(user_id, 0.0)
    ref_balances.setdefault(user_id, 0.0)
    user_data.setdefault(user_id, {})

    if query.data == "check_sub":
        if await check_subscription(user_id, context):
            await query.edit_message_text("✅ **تم التحقق بنجاح! مرحباً بك بمتجر قيس.**\nأرسل /start لفتح القائمة.")
        else:
            await query.answer("❌ لم تنضم للقناة بعد! يرجى الانضمام أولاً.", show_alert=True)
        return

    if query.data.startswith("init_lang_"):
        lang = query.data.split("_")[2]
        user_data[user_id]["lang"] = lang
        text, reply_markup = build_main_menu(lang, user_balances[user_id], user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        return

    lang = user_data[user_id].get("lang", "ar")

    if query.data.startswith("lang_"):
        lang = query.data.split("_")[1]
        user_data[user_id]["lang"] = lang
        text, reply_markup = build_main_menu(lang, user_balances[user_id], user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    elif query.data == "store":
        keyboard = []
        is_seller = user_id in sellers_list
        for code, item in products_db.items():
            price = item['seller_price'] if is_seller else item['price']
            tag = " 🏷️ (سعر بائع)" if is_seller else ""
            btn_text = f"📱 {item['name']} - ${price:.2f}{tag}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"prod_{code}")])
        keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")])
        
        txt = "🛍️ **اختر الخدمة المطلوبة:**"
        if is_seller: txt += "\n✨ (تم تطبيق أسعار الموزعين والبائعين المنخفضة)"
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("prod_"):
        code = query.data.split("_")[1]
        item = products_db.get(code)
        if not item:
            await query.edit_message_text("❌ هاد المنتج غير متوفر حالياً.")
            return

        is_seller = user_id in sellers_list
        price = item['seller_price'] if is_seller else item['price']
        current_balance = user_balances[user_id]

        if current_balance < price:
            await query.edit_message_text(
                f"❌ رصيدك غير كافٍ!\nرصيدك الحالي: **${current_balance:.2f}**\nسعر الخدمة: **${price:.2f}**",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 إيداع رصيد الآن", callback_data="deposit")]])
            )
        else:
            user_data[user_id]["buying_product"] = code
            user_data[user_id]["state"] = "WAITING_EMAIL"
            await query.edit_message_text(f"🛒 اخترت: **{item['name']}** بسعر **${price:.2f}**\n\n📧 أرسل بريدك الإلكتروني الآن لتسليم الطلب:")

    elif query.data == "deposit":
        user_data[user_id]["state"] = "WAITING_TXID"
        msg = (
            "💳 **── قسم إيداع الرصيد ──**\n\n"
            f"• **Binance Pay ID:** `{BINANCE_PAY_ID}`\n"
            f"• **USDT (BEP20):** `{USDT_WALLET}`\n\n"
            "أرسل **رمز الحوالة (TxID)** هنا للتحقق التلقائي:"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")]]))

    elif query.data == "referral":
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (
            "🤝 **── نظام الإحالة والأرباح (10%) ──**\n\n"
            f"🔗 رابط الإحالة الخاص بك:\n`{ref_link}`\n\n"
            "💡 شارك الرابط مع أصدقائك، وستحصل على **10% تلقائياً** من أي عملية شراء يقومون بها داخل البوت!\n\n"
            f"💰 أرباح الإحالة الحالية: **${ref_balances[user_id]:.2f}**"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 تحويل الأرباح للمحفظة الرئيسية", callback_data="claim_ref")],
            [InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")]
        ]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "claim_ref":
        amount = ref_balances[user_id]
        if amount <= 0:
            await query.answer("❌ لا يوجد لديك أرباح إحالة لتحويلها حالياً!", show_alert=True)
        else:
            ref_balances[user_id] = 0.0
            user_balances[user_id] += amount
            await query.answer(f"🎉 تم تحويل ${amount:.2f} إلى رصيدك الرئيسي بنجاح!", show_alert=True)
            text, reply_markup = build_main_menu(lang, user_balances[user_id], user_id)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    elif query.data == "use_code":
        user_data[user_id]["state"] = "WAITING_CODE"
        await query.edit_message_text("🎁 **أدخل كود الشحن / الهدية الآن:**", parse_mode="Markdown")

    elif query.data == "profile":
        is_seller_txt = "نعم 👑" if user_id in sellers_list else "لا"
        msg = (
            "👑 **── الحساب الشخصي ──**\n\n"
            f"👤 المستخدم: @{user.username or 'غير معرف'}\n"
            f"🆔 ID الخاص بك: `{user_id}`\n"
            f"🏷️ حساب بائع: **{is_seller_txt}**\n"
            f"💰 الرصيد الرئيسي: **${user_balances[user_id]:.2f}**\n"
            f"🎁 أرباح الإحالات: **${ref_balances[user_id]:.2f}**"
        )
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")]]))

    elif query.data == "my_orders":
        orders = user_orders.get(user_id, [])
        if not orders:
            msg = "📜 لا يوجد لديك طلبات سابقة."
        else:
            msg = "📜 **سجل طلباتك الأخيرة:**\n\n" + "\n".join(orders)
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")]]))

    elif query.data in ["how_to", "support"]:
        msg = bot_texts["how_to"] if query.data == "how_to" else bot_texts["support"]
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة للقائمة", callback_data="main_menu")]]))

    elif query.data == "main_menu":
        user_data[user_id]["state"] = None
        text, reply_markup = build_main_menu(lang, user_balances[user_id], user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# --- 8. معالجة الرسائل والطلبات والرموز ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id in banned_users: return

    text = update.message.text.strip()
    state = user_data.get(user_id, {}).get("state")

    if state == "WAITING_TXID":
        txid = text
        if txid in used_txids:
            await update.message.reply_text("⚠️ رمز الحوالة (TxID) مستخدم سابقاً!")
            return

        await update.message.reply_text("⏳ جاري الفحص والتحقق التلقائي مع بايننس...")
        amount = check_binance_deposit(txid)

        if amount is not None:
            if is_valid_amount(amount):
                used_txids.add(txid)
                user_balances[user_id] += amount
                user_data[user_id]["state"] = None

                await update.message.reply_text(f"🎉 **تم شحن الرصيد بنجاح!**\nتم إضافة: **${amount:.2f}**\nرصيدك الجديد: **${user_balances[user_id]:.2f}**", parse_mode="Markdown")

                admin_msg = f"✅ **إيداع آلي جديد!**\n👤 العميل: @{user.username or user_id}\n🆔 العميل: `{user_id}`\n💳 المبلغ: ${amount}\n🔗 TxID: `{txid}`"
                await context.bot.send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ المبلغ المحول غير مسموح به! يجب أن يكون إما 1$ أو من مضاعفات الـ 5.")
        else:
            await update.message.reply_text("❌ لم نتمكن من التأكد من العملية في بايننس. يرجى التأكد وإعادة المحاولة.")

    elif state == "WAITING_EMAIL":
        if "@" in text and "." in text:
            email = text
            code = user_data[user_id].get("buying_product")
            item = products_db.get(code, {})
            is_seller = user_id in sellers_list
            price = item.get("seller_price", item.get("price", 0)) if is_seller else item.get("price", 0)

            user_balances[user_id] -= price
            user_data[user_id]["state"] = None

            # تسجيل الطلب
            order_info = f"• {item.get('name')} | ${price:.2f} | الإيميل: `{email}`"
            user_orders.setdefault(user_id, []).append(order_info)

            # تطبيق نسبة الإحالة 10%
            if user_id in user_referrals:
                ref_id = user_referrals[user_id]
                commission = price * 0.10
                ref_balances[ref_id] = ref_balances.get(ref_id, 0.0) + commission
                try:
                    await context.bot.send_message(ref_id, f"🎉 **أرباح إحالة جديدة!**\nقام أستاذك المحال بطلب خدمة وحصلت على **${commission:.2f}** (10%) بمحفظة الإحالة.")
                except Exception: pass

            await update.message.reply_text(f"✅ تم خصم **${price:.2f}** من رصيدك بنجاح.\nالخدمة: {item.get('name')}\nالإيميل: `{email}`\nسيتم التسليم فوراً!")

            admin_msg = f"📦 **طلب جديد!**\n👤 العميل: @{user.username or user_id}\n🆔 العميل: `{user_id}`\n🛒 الخدمة: {item.get('name')}\n📧 الإيميل للنسخ: `{email}`"
            await context.bot.send_message(ADMIN_CHAT_ID, admin_msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ البريد الإلكتروني غير صحيح!")

    elif state == "WAITING_CODE":
        code_input = text.strip()
        if code_input in gift_codes:
            amount = gift_codes.pop(code_input)
            user_balances[user_id] += amount
            user_data[user_id]["state"] = None
            await update.message.reply_text(f"🎉 **مبروك! تم تفعيل الكود بنجاح.**\nتم إضافة **${amount:.2f}** لحسابك!", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ الكود خاطئ أو تم استخدامه سابقاً!")

# --- 9. تشغيل البوت ---
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # الأوامر الرئيسية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))

    # أوامر لوحة الأدمن
    app.add_handler(CommandHandler("addproduct", add_product))
    app.add_handler(CommandHandler("delproduct", del_product))
    app.add_handler(CommandHandler("addbalance", add_balance_cmd))
    app.add_handler(CommandHandler("setseller", set_seller))
    app.add_handler(CommandHandler("delseller", del_seller))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("makecode", make_code))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # التفاعلات والرسائل
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot is fully updated and running...")
    app.run_polling()
