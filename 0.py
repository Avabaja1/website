from flask import Flask, request, redirect, url_for, render_template_string
import sqlite3
import threading
import asyncio
import uuid
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --- Настройки ---
TOKEN = '7813966617:AAEm3NDzUgbocfvRdfzJrP3PveOlurTYoIY'
ADMIN_PASSWORD = 'k123'
ADMIN_CHAT_ID = 6226314827
CLOUDTIPS_SECRET = 'your-cloudtips-secret'
PAYMENT_URL_BASE = 'https://example.com/pay?user_id='

app = Flask(__name__)
bot = Bot(token=TOKEN)

conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    fullname TEXT,
    uid TEXT UNIQUE,
    paid INTEGER DEFAULT 0,
    payment_pending INTEGER DEFAULT 0,
    key TEXT DEFAULT NULL,
    hwid TEXT DEFAULT NULL,
    banned INTEGER DEFAULT 0
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY,
    bot_enabled INTEGER DEFAULT 1
)
''')
conn.commit()

cursor.execute('SELECT COUNT(*) FROM settings')
if cursor.fetchone()[0] == 0:
    cursor.execute('INSERT INTO settings(id, bot_enabled) VALUES (1, 1)')
    conn.commit()

def register_user(telegram_id, username, fullname):
    uid = str(uuid.uuid4())[:8]
    cursor.execute("SELECT uid FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (telegram_id, username, fullname, uid) VALUES (?, ?, ?, ?)",
                       (telegram_id, username, fullname, uid))
        conn.commit()
        return uid
    return row[0]

def update_user(telegram_id, **kwargs):
    for key, value in kwargs.items():
        cursor.execute(f"UPDATE users SET {key} = ? WHERE telegram_id = ?", (value, telegram_id))
    conn.commit()

def get_bot_enabled():
    cursor.execute('SELECT bot_enabled FROM settings WHERE id=1')
    return cursor.fetchone()[0]

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        action = request.form.get('action')
        telegram_id = int(request.form.get('telegram_id'))
        if action == 'set_pending':
            update_user(telegram_id, payment_pending=1)
        elif action == 'clear_pending':
            update_user(telegram_id, payment_pending=0)
        elif action == 'confirm_payment':
            update_user(telegram_id, paid=1, payment_pending=0)
        elif action == 'remove_payment':
            update_user(telegram_id, paid=0, payment_pending=0)
        elif action == 'ban':
            update_user(telegram_id, banned=1)
        elif action == 'unban':
            update_user(telegram_id, banned=0)
        elif action == 'update_key':
            new_key = str(uuid.uuid4())
            update_user(telegram_id, key=new_key)
        elif action == 'notify_banned':
            asyncio.run(bot.send_message(chat_id=telegram_id, text="Вы были забанены администратором."))

    cursor.execute("SELECT telegram_id, username, fullname, uid, paid, payment_pending, key, hwid, banned FROM users")
    users = cursor.fetchall()
    return render_template_string('''
    <html>
    <head>
    <title>Панель администратора</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f4f6f8; padding: 20px; }
        h2 { color: #333; }
        table { border-collapse: collapse; width: 100%; background: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.05); }
        th, td { padding: 10px; border: 1px solid #ccc; text-align: center; }
        th { background-color: #fafafa; color: #222; }
        form { margin: 0; display: inline-block; }
        button { margin: 1px; padding: 5px 8px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
    </style>
    </head>
    <body>
    <h2>Панель администратора</h2>
    <table>
        <tr><th>ID</th><th>Имя</th><th>Username</th><th>UID</th><th>Оплата</th><th>На проверке</th><th>Ключ</th><th>HWID</th><th>Бан</th><th>Действия</th></tr>
        {% for u in users %}
        <tr>
            <td>{{ u[0] }}</td>
            <td>{{ u[2] }}</td>
            <td>@{{ u[1] }}</td>
            <td>{{ u[3] }}</td>
            <td>{{ '✅' if u[4] else '❌' }}</td>
            <td>{{ '⏳' if u[5] else '-' }}</td>
            <td>{{ u[6] or '-' }}</td>
            <td>{{ u[7] or '-' }}</td>
            <td>{{ '🚫' if u[8] else '✔️' }}</td>
            <td>
                <form method="post">
                    <input type="hidden" name="telegram_id" value="{{ u[0] }}">
                    <button name="action" value="set_pending">Проверка</button>
                    <button name="action" value="clear_pending">Снять проверку</button>
                    <button name="action" value="confirm_payment">Подтвердить</button>
                    <button name="action" value="remove_payment">Снять оплату</button>
                    <button name="action" value="update_key">Обновить ключ</button>
                    <button name="action" value="ban">Забанить</button>
                    <button name="action" value="unban">Разбанить</button>
                    <button name="action" value="notify_banned">Уведомить о бане</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    </body>
    </html>
    ''', users=users)

# остальная часть кода остается без изменений


# === Telegram Бот ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    uid = register_user(user.id, user.username or '', user.full_name or '')
    if get_bot_enabled() == 0:
        await update.message.reply_text("Бот временно отключен.")
        return
    cursor.execute("SELECT banned FROM users WHERE telegram_id=?", (user.id,))
    banned = cursor.fetchone()[0]
    if banned:
        await update.message.reply_text("Вы забанены.")
        return

    keyboard = [
        [InlineKeyboardButton("Отправить HWID", callback_data='send_hwid')],
        [InlineKeyboardButton("Статус оплаты", callback_data='status_payment')],
        [InlineKeyboardButton("Профиль", callback_data='profile')],
        [InlineKeyboardButton("Получить ключ", callback_data='get_key')],
        [InlineKeyboardButton("💳 Оплатить", url=PAYMENT_URL_BASE + uid)]
    ]
    await update.message.reply_text(
        f"Привет, {user.full_name}!\nТвой UID: {uid}\nВыбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    cursor.execute("SELECT banned FROM users WHERE telegram_id=?", (user.id,))
    if cursor.fetchone()[0]:
        await query.message.reply_text("Вы забанены.")
        return

    if query.data == 'send_hwid':
        await query.message.reply_text("Отправьте HWID.")
        context.user_data['awaiting_hwid'] = True

    elif query.data == 'status_payment':
        cursor.execute("SELECT paid, payment_pending FROM users WHERE telegram_id=?", (user.id,))
        paid, pending = cursor.fetchone()
        msg = "✅ Оплата подтверждена" if paid else "⏳ На проверке" if pending else "❌ Оплата не найдена"
        await query.message.reply_text(msg)

    elif query.data == 'profile':
        cursor.execute("SELECT username, fullname, uid, paid FROM users WHERE telegram_id=?", (user.id,))
        username, fullname, uid, paid = cursor.fetchone()
        await query.message.reply_text(
            f"👤 Профиль:\nИмя: {fullname}\nUsername: @{username}\nUID: {uid}\nОплата: {'✅' if paid else '❌'}"
        )

    elif query.data == 'get_key':
        cursor.execute("SELECT paid, key FROM users WHERE telegram_id=?", (user.id,))
        paid, key = cursor.fetchone()
        if paid:
            await query.message.reply_text(f"🔑 Ключ: {key or 'Ожидает назначения'}")
        else:
            await query.message.reply_text("❌ Оплата не подтверждена")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if context.user_data.get('awaiting_hwid'):
        hwid = update.message.text.strip()
        update_user(user.id, hwid=hwid)
        context.user_data['awaiting_hwid'] = False
        await update.message.reply_text("HWID сохранён.")
    else:
        await update.message.reply_text("Используй кнопки меню.")

# === Запуск ===
def run_bot():
    asyncio.set_event_loop(asyncio.new_event_loop())
    app_builder = ApplicationBuilder().token(TOKEN).build()
    app_builder.add_handler(CallbackQueryHandler(button_handler))
    app_builder.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app_builder.add_handler(MessageHandler(filters.COMMAND & filters.Regex("^/start$"), start))
    app_builder.run_polling()

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
