import os
import sqlite3
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ---------------------------------------------------------
# 1. Keep-Alive Web Server for Render Hosting
# ---------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"QAIS STORE Bot is Running Successfully!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# ---------------------------------------------------------
# 2. Configurations & Constants
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8466390738:AAHMVZhjGaUuYZq0J-4RBFKZvJp9aVF-9R0")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8556501768"))

BINANCE_PAY_ID = "1006208970"
USDT_BEP20_ADDRESS = "0x409239a2a633f0627366f701c4ee3c2d5a9dac2a"

# Conversation States for Admin Panel
ADD_PROD_NAME, ADD_PROD_CAT, ADD_OPT_NAME, ADD_OPT_PRICES = range(4)

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------
# 3. Database Layer (SQLite)
# ---------------------------------------------------------
DB_FILE = "qais_store.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0.0,
            ref_balance REAL DEFAULT 0.0,
            is_reseller INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            lang TEXT DEFAULT 'ar'
        )
    ''')
    # Products Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL
        )
    ''')
    # Product Options Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            opt_code TEXT,
            opt_name TEXT,
            price_user REAL,
            price_reseller REAL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    ''')
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_FILE)

def get_or_create_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, balance, ref_balance, is_reseller, referred_by, lang FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        c.execute("SELECT user_id, balance, ref_balance, is_reseller, referred_by, lang FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
    conn.close()
    return {
        "user_id": row[0],
        "balance": row[1],
        "ref_balance": row[2],
        "is_reseller": bool(row[3]),
        "referred_by": row[4],
        "lang": row[5]
    }

def update_user_lang(user_id, lang):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET lang = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# 4. Localization Texts
# ---------------------------------------------------------
TEXTS = {
    "ar": {
        "welcome": "أهلاً بك في **QAIS STORE** 🛒\nمتجر الخدمات والتطبيقات المعتمدة الممتازة.\nتحقق وإيداع آلي 24/7.",
        "profile": "🆔 **معرفك الخاص:** `{user_id}`\n💰 **رصيدك الحالي:** `${balance:.3f}`\n🎁 **أرباح الإحالة:** `${ref_balance:.3f}`\n🏷️ **نوع الحساب:** {role}",
        "referral": "🔗 **نظام الإحالة**\n\nقم بدعوة أصدقائك وستحصل على **10%** عوائد وأرباح مباشرة في محفظتك عن كل عملية شراء يقومون بها!\n\nرابطك المباشر:\n`https://t.me/YOUR_BOT_USERNAME?start=ref_{user_id}`",
        "deposit": "💳 **قسم الإيداع الآلي**\n\nاختر فئة الإيداع المطلوبة لإتمام الشحن عبر Binance:",
        "shop": "🛍️ **المنتجات والخدمات المتاحة:**",
        "btn_shop": "🛍️ الشراء الآن",
        "btn_profile": "👤 الحساب الشخصي",
        "btn_ref": "🔗 نظام الإحالة",
        "btn_deposit": "💳 إيداع رصيد",
        "btn_back": "🔙 العودة القائمة",
        "role_user": "عميل عادي",
        "role_reseller": "بائع معتمد 🎖️"
    },
    "en": {
        "welcome": "Welcome to **QAIS STORE** 🛒\nPremium Digital Services & Applications Store.\nAutomated Verification 24/7.",
        "profile": "🆔 **User ID:** `{user_id}`\n💰 **Balance:** `${balance:.3f}`\n🎁 **Referral Earnings:** `${ref_balance:.3f}`\n🏷️ **Account Type:** {role}",
        "referral": "🔗 **Referral System**\n\nInvite your friends and earn **10%** commission directly added to your balance on every purchase they make!\n\nYour Referral Link:\n`https://t.me/YOUR_BOT_USERNAME?start=ref_{user_id}`",
        "deposit": "💳 **Auto Deposit System**\n\nSelect the deposit amount to pay via Binance:",
        "shop": "🛍️ **Available Services & Products:**",
        "btn_shop": "🛍️ Shop Now",
        "btn_profile": "👤 Profile",
        "btn_ref": "🔗 Referral System",
        "btn_deposit": "💳 Add Balance",
        "btn_back": "🔙 Main Menu",
        "role_user": "Standard Customer",
        "role_reseller": "Authorized Reseller 🎖️"
    }
}

# ---------------------------------------------------------
# 5. UI Keyboards
# ---------------------------------------------------------
def main_menu_keyboard(lang="ar"):
    t = TEXTS[lang]
    keyboard = [
        [InlineKeyboardButton(t["btn_shop"], callback_data="btn_shop")],
        [InlineKeyboardButton(t["btn_profile"], callback_data="btn_profile"), InlineKeyboardButton(t["btn_ref"], callback_data="btn_ref")],
        [InlineKeyboardButton(t["btn_deposit"], callback_data="btn_deposit")],
        [InlineKeyboardButton("🌐 Change Language / تغيير اللغة", callback_data="toggle_language")]
    ]
    return InlineKeyboardMarkup(keyboard)

def deposit_options_keyboard(lang="ar"):
    t = TEXTS[lang]
    keyboard = [
        [InlineKeyboardButton("$1 USDT", callback_data="dep_1"), InlineKeyboardButton("$5 USDT", callback_data="dep_5"), InlineKeyboardButton("$10 USDT", callback_data="dep_10")],
        [InlineKeyboardButton("$20 USDT", callback_data="dep_20"), InlineKeyboardButton("$30 USDT", callback_data="dep_30"), InlineKeyboardButton("$50 USDT", callback_data="dep_50")],
        [InlineKeyboardButton(t["btn_back"], callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة منتج جديد", callback_data="admin_add_prod")],
        [InlineKeyboardButton("⚙️ إدارة المنتجات والأسعار", callback_data="admin_manage_prods")],
        [InlineKeyboardButton("👤 شحن رصيد لمستخدم", callback_data="admin_charge_user")],
        [InlineKeyboardButton("🎖️ ترقية بائع", callback_data="admin_promote_reseller")],
        [InlineKeyboardButton("🔙 العودة للمتجر", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------------------------------------------------------
# 6. Core Handlers
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_or_create_user(user_id)
    
    # Process referral links
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].split("_")[1])
            if referrer_id != user_id and user["referred_by"] is None:
                conn = get_db()
                c = conn.cursor()
                c.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                conn.commit()
                conn.close()
        except ValueError:
            pass

    lang = user["lang"]
    t = TEXTS[lang]
    await update.message.reply_text(t["welcome"], parse_mode="Markdown", reply_markup=main_menu_keyboard(lang))

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM products")
    total_prods = c.fetchone()[0]
    conn.close()

    admin_msg = (
        f"👑 **لوحة تحكم الأدمن المظورة (قيس)** ⚙️\n\n"
        f"👥 **المستخدمين:** {total_users}\n"
        f"📦 **المنتجات:** {total_prods}\n\n"
        f"اختر الخيار المناسب أدناه للتحكم:"
    )
    await update.message.reply_text(admin_msg, parse_mode="Markdown", reply_markup=admin_panel_keyboard())

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_or_create_user(user_id)
    lang = user["lang"]
    t = TEXTS[lang]
    data = query.data

    if data == "main_menu":
        await query.edit_message_text(t["welcome"], parse_mode="Markdown", reply_markup=main_menu_keyboard(lang))

    elif data == "toggle_language":
        new_lang = "en" if lang == "ar" else "ar"
        update_user_lang(user_id, new_lang)
        user["lang"] = new_lang
        t = TEXTS[new_lang]
        await query.edit_message_text(t["welcome"], parse_mode="Markdown", reply_markup=main_menu_keyboard(new_lang))

    elif data == "btn_profile":
        role_str = t["role_reseller"] if user["is_reseller"] else t["role_user"]
        msg = t["profile"].format(
            user_id=user_id, balance=user["balance"],
            ref_balance=user["ref_balance"], role=role_str
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t["btn_back"], callback_data="main_menu")]])
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)

    elif data == "btn_ref":
        msg = t["referral"].format(user_id=user_id)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t["btn_back"], callback_data="main_menu")]])
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)

    elif data == "btn_deposit":
        await query.edit_message_text(t["deposit"], parse_mode="Markdown", reply_markup=deposit_options_keyboard(lang))

    elif data.startswith("dep_"):
        amount = data.split("_")[1]
        dep_msg = (
            f"🔹 **قسم الإيداع الآلي - QAIS STORE**\n\n"
            f"المبلغ المطلوب: **${amount} USDT**\n\n"
            f"🔸 **Binance Pay ID:** `{BINANCE_PAY_ID}`\n"
            f"🔸 **USDT (BEP20):** `{USDT_BEP20_ADDRESS}`\n\n"
            f"أرسل رمز معرّف التحويل (TxID) هنا بعد الإتمام لتأكيد الشحن."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t["btn_back"], callback_data="btn_deposit")]])
        await query.edit_message_text(dep_msg, parse_mode="Markdown", reply_markup=kb)

    elif data == "btn_shop":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT p.name, o.opt_name, o.price_user, o.price_reseller FROM products p JOIN product_options o ON p.id = o.product_id")
        options = c.fetchall()
        conn.close()

        if not options:
            shop_text = "⚠️ لا توجد منتجات متوفرة حالياً في المتجر."
        else:
            shop_text = "🛍️ **قائمة الخدمات والأسعار المتوفرة:**\n\n"
            for item in options:
                prod_name, opt_name, p_user, p_reseller = item
                # Hide Reseller Price from Standard User
                if user["is_reseller"]:
                    price_display = f"${p_reseller:.2f} (سعر البائع)"
                else:
                    price_display = f"${p_user:.2f}"
                shop_text += f"▪️ **{prod_name}** - {opt_name}: {price_display}\n"

        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t["btn_back"], callback_data="main_menu")]])
        await query.edit_message_text(shop_text, parse_mode="Markdown", reply_markup=kb)

# ---------------------------------------------------------
# 7. Main Bot Startup
# ---------------------------------------------------------
if __name__ == "__main__":
    # Initialize SQLite Database
    init_db()
    
    # Start Keep-Alive Server Thread
    Thread(target=run_health_check_server, daemon=True).start()

    # Application Setup
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers Registration
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print("QAIS STORE Bot Launched Successfully!")
    app.run_polling()
