import os
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)

# 1. Configurations & Constants
BOT_TOKEN = os.environ.get("BOT_TOKEN=8466390738:AAHMVzhGalyuZQqU4AR8FKZvJp9navF-9R0")
BINANCE_PAY_ID = "100528970"
USDT_BEP20_ADDRESS = "0x409293a253f6627366f7014ee3c2d5a9dac2a"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "855650178"))

# Conversation States for Admin Panel
ADD_CAT_NAME, ADD_PROD_CAT, ADD_PROD_NAME, ADD_OPT_NAME, ADD_OPT_PRICES = range(5)

logging.basicConfig(level=logging.INFO)
DB_FILE = "qais_store.db"

# 2. Database Layer
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            product_name TEXT NOT NULL,
            FOREIGN KEY(category_id) REFERENCES categories(category_id) ON DELETE CASCADE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_options (
            option_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            opt_name TEXT NOT NULL,
            opt_code TEXT,
            price_user REAL,
            price_reseller REAL,
            FOREIGN KEY(product_id) REFERENCES products(product_id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect(DB_FILE)

def get_or_create_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, balance, ref_balance, is_reseller, lang FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        row = (user_id, 0.0, 0.0, 0, 'ar')
    conn.close()
    return {
        "user_id": row[0],
        "balance": row[1],
        "ref_balance": row[2],
        "is_reseller": bool(row[3]),
        "lang": row[4]
    }

# 3. Keyboards
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🛒 الشراء الآن", callback_data="btn_shop")],
        [InlineKeyboardButton("👤 الحساب الشخصي", callback_data="btn_profile"), InlineKeyboardButton("🎁 نظام الإحالة", callback_data="btn_ref")],
        [InlineKeyboardButton("إيداع رصيد 💳", callback_data="btn_deposit")],
        [InlineKeyboardButton("تغيير اللغة / Change Language 🌐", callback_data="toggle_language")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ إضافة قسم/لعبة جديدة", callback_data="admin_add_cat")],
        [InlineKeyboardButton("➕ إضافة منتج جديد", callback_data="admin_add_prod")],
        [InlineKeyboardButton("🗑️ إدارة/حذف الأقسام", callback_data="admin_manage_cats")],
        [InlineKeyboardButton("👤 شحن رصيد لمستخدم", callback_data="admin_charge_user")],
        [InlineKeyboardButton("⭐ ترقية باج", callback_data="admin_promote_reseller")],
        [InlineKeyboardButton("🔙 العودة للمتجر", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# 4. Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_or_create_user(user_id)
    msg = f"أهلاً بك في **QAIS STORE**\nمتجر الخدمات والتطبيقات المعتمدة الممتازة\nتحقق وإيداع الـ 24/7."
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=main_menu_keyboard())

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

    admin_msg = f"لوحة تحكم الأدمن المقطورة (قيس) 👑\n\n👤 المستخدمين: {total_users}\n📦 المنتجات: {total_prods}\n\nاختر الخيار المناسب أداة للتحكم:"
    await update.message.reply_text(admin_msg, parse_mode='Markdown', reply_markup=admin_panel_keyboard())

# 5. Admin Dynamic Category & Product Conversation
async def start_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END
    await query.message.reply_text("أدخل اسم القسم/اللعبة الجديد (مثال: Free Fire, Call of Duty):")
    return ADD_CAT_NAME

async def save_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_name = update.message.text.strip()
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO categories (category_name) VALUES (?)", (cat_name,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ تم إضافة القسم '{cat_name}' بنجاح!", reply_markup=admin_panel_keyboard())
    return ConversationHandler.END

async def start_add_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT category_id, category_name FROM categories")
    cats = c.fetchall()
    conn.close()

    if not cats:
        await query.message.reply_text("❌ لا توجد أقسام مضافة بعد! يرجى إضافة قسم/لعبة أولاً.", reply_markup=admin_panel_keyboard())
        return ConversationHandler.END

    kb = [[InlineKeyboardButton(cat[1], callback_data=f"sel_cat_{cat[0]}")] for cat in cats]
    await query.message.reply_text("اختر القسم الذي تريد إضافة المنتج إليه:", reply_markup=InlineKeyboardMarkup(kb))
    return ADD_PROD_CAT

async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.replace("sel_cat_", ""))
    context.user_data['new_prod_cat_id'] = cat_id
    await query.message.reply_text("أدخل اسم المنتج الرئيسي (مثال: AimHack Non Root):")
    return ADD_PROD_NAME

async def product_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prod_name = update.message.text.strip()
    context.user_data['new_prod_name'] = prod_name
    await update.message.reply_text("أدخل اسم الخيار/المدة (مثال: 1Day / 24 Hours):")
    return ADD_OPT_NAME

async def option_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opt_name = update.message.text.strip()
    context.user_data['new_opt_name'] = opt_name
    await update.message.reply_text("أدخل السعر بـ USDT بالنسق التالي:\n`سعر_العميل سعر_الموزع الكود_أو_الرابط`\nمثال:\n`0.75 0.50 CODE12345`", parse_mode='Markdown')
    return ADD_OPT_PRICES

async def option_prices_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.strip().split()
    if len(parts) < 2:
        await update.message.reply_text("❌ صيغة خاطئة! أعد الإدخال بالشكل: `سعر_العميل سعر_الموزع الكود`", parse_mode='Markdown')
        return ADD_OPT_PRICES

    try:
        p_user = float(parts[0])
        p_reseller = float(parts[1])
        code = parts[2] if len(parts) > 2 else ""
    except ValueError:
        await update.message.reply_text("❌ أرقام الأسعار غير صحيحة. حاول مجدداً:")
        return ADD_OPT_PRICES

    cat_id = context.user_data['new_prod_cat_id']
    prod_name = context.user_data['new_prod_name']
    opt_name = context.user_data['new_opt_name']

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO products (category_id, product_name) VALUES (?, ?)", (cat_id, prod_name))
    prod_id = c.lastrowid
    c.execute("INSERT INTO product_options (product_id, opt_name, opt_code, price_user, price_reseller) VALUES (?, ?, ?, ?, ?)",
              (prod_id, opt_name, code, p_user, p_reseller))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ تم إضافة المنتج والخيار بنجاح!", reply_markup=admin_panel_keyboard())
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END

# 6. General Callback Handler
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    user = get_or_create_user(user_id)

    if data == "main_menu":
        await query.edit_message_text("أهلاً بك في QAIS STORE", reply_markup=main_menu_keyboard())

    elif data == "btn_profile":
        role = "موزع معتمد 🌟" if user["is_reseller"] else "مستخدم عادي 👤"
        msg = f"🆔 **معرف الحساب:** `{user_id}`\n💰 **الرصيد:** ${user['balance']:.2f}\n🏷️ **نوع الحساب:** {role}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("إيداع رصيد 💳", callback_data="btn_deposit")], [InlineKeyboardButton("العودة", callback_data="main_menu")]])
        await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=kb)

    elif data == "btn_shop":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT category_id, category_name FROM categories")
        cats = c.fetchall()
        conn.close()

        if not cats:
            await query.edit_message_text("⚠️ لا توجد منتجات أو ألعاب متوفرة حالياً في المتجر.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة", callback_data="main_menu")]]))
            return

        kb = [[InlineKeyboardButton(f"🎮 {cat[1]}", callback_data=f"shop_cat_{cat[0]}")] for cat in cats]
        kb.append([InlineKeyboardButton("العودة للملف الرئيسي", callback_data="main_menu")])
        await query.edit_message_text("اختر اللعبة/القسم لعرض المنتجات المتاحة:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("shop_cat_"):
        cat_id = int(data.replace("shop_cat_", ""))
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT product_id, product_name FROM products WHERE category_id = ?", (cat_id,))
        prods = c.fetchall()
        conn.close()

        if not prods:
            await query.edit_message_text("❌ لا توجد منتجات داخل هذا القسم حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة للأقسام", callback_data="btn_shop")]]))
            return

        kb = [[InlineKeyboardButton(p[1], callback_data=f"view_prod_{p[0]}")] for p in prods]
        kb.append([InlineKeyboardButton("🔙 رجوع للأقسام", callback_data="btn_shop")])
        await query.edit_message_text("اختر المنتج المطلوب:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("view_prod_"):
        prod_id = int(data.replace("view_prod_", ""))
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT option_id, opt_name, price_user, price_reseller FROM product_options WHERE product_id = ?", (prod_id,))
        opts = c.fetchall()
        conn.close()

        kb = []
        for opt in opts:
            price = opt[3] if user["is_reseller"] else opt[2]
            kb.append([InlineKeyboardButton(f"{opt[1]} - ${price:.2f}", callback_data=f"buy_opt_{opt[0]}")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="btn_shop")])
        await query.edit_message_text("اختر الخيار والمدة المناسبة:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("buy_opt_"):
        opt_id = int(data.replace("buy_opt_", ""))
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT o.opt_name, o.price_user, o.price_reseller, p.product_name FROM product_options o JOIN products p ON o.product_id = p.product_id WHERE o.option_id = ?", (opt_id,))
        row = c.fetchone()
        conn.close()

        if row:
            price = row[2] if user["is_reseller"] else row[1]
            msg = f"📦 **المنتج:** {row[3]} ({row[0]})\n💵 **السعر الإجمالي:** ${price:.2f}\n💳 **رصيدك الحالي:** ${user['balance']:.2f}\n\nاختر طريقة الدفع المناسبة:"
            kb = [
                [InlineKeyboardButton(f"الدفع من المحفظة (${user['balance']:.2f})", callback_data=f"pay_wallet_{opt_id}")],
                [InlineKeyboardButton("الدفع المباشر عبر Binance Pay", callback_data=f"pay_binance_{opt_id}")],
                [InlineKeyboardButton("إلغاء", callback_data="btn_shop")]
            ]
            await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("pay_wallet_"):
        opt_id = int(data.replace("pay_wallet_", ""))
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT price_user, price_reseller, opt_code FROM product_options WHERE option_id = ?", (opt_id,))
        row = c.fetchone()

        if row:
            price = row[1] if user["is_reseller"] else row[0]
            if user["balance"] >= price:
                new_bal = user["balance"] - price
                c.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_bal, user_id))
                conn.commit()
                conn.close()
                code_txt = row[2] if row[2] else "تواصل مع الدعم لاستلام المنتج"
                await query.edit_message_text(f"✅ **تم الشراء بنجاح!**\n\n🔑 **الكود/المنتج الخاص بك:**\n`{code_txt}`", parse_mode='Markdown')
            else:
                conn.close()
                await query.edit_message_text("❌ رصيدك غير كافٍ للتمام عملية الشراء. يرجى الشحن أولاً أو اختيار طريقة دفع أخرى.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("إيداع رصيد", callback_data="btn_deposit")]]))

    elif data.startswith("pay_binance_"):
        opt_id = int(data.replace("pay_binance_", ""))
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT price_user, price_reseller FROM product_options WHERE option_id = ?", (opt_id,))
        row = c.fetchone()
        conn.close()

        if row:
            price = row[1] if user["is_reseller"] else row[0]
            msg = f"💎 **إتمام الدفع عبر Binance Pay**\n\nقم بتحويل **${price:.2f} USDT** بالبيانات التالية:\n🔸 **Binance Pay ID:** `{BINANCE_PAY_ID}`\n🔸 **Network (BEP20):** `{USDT_BEP20_ADDRESS}`\n\nأرسل رقم العملية (TxID) للآدمن للتحقق تلقائياً."
            await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("العودة للمتجر", callback_data="main_menu")]]))

# 7. Main Application
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Admin Add Conversation Handler
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_category, pattern="^admin_add_cat$"),
            CallbackQueryHandler(start_add_product, pattern="^admin_add_prod$")
        ],
        states={
            ADD_CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_category)],
            ADD_PROD_CAT: [CallbackQueryHandler(category_selected, pattern="^sel_cat_")],
            ADD_PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, product_name_received)],
            ADD_OPT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, option_name_received)],
            ADD_OPT_PRICES: [MessageHandler(filters.TEXT & ~filters.COMMAND, option_prices_received)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(admin_conv)
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print("Qais Store Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
