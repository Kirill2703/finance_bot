import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- Загружаем токен и DB URL ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL").strip()

# --- Подключение к БД ---


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# --- Категории ---
income_categories = ["Зарплата", "Подарки", "Другое"]
expense_categories = ["Питание", "Транспорт",
                      "Развлечения", "Коммунальные", "Другое"]

# --- Главное меню ---
keyboard_main = [["💳 Карта", "💵 Наличные"],
                 ["📊 Баланс", "⚙️ Установить баланс"],
                 ["📜 История"]]

# --- Команды ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я бот для учёта доходов и расходов 💰\nВыбери действие:",
        reply_markup=reply_markup
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(balance) FROM finance WHERE type='balance'")
    total = cursor.fetchone()[0] or 0.0
    cursor.execute(
        "SELECT balance FROM finance WHERE account='card' AND type='balance' ORDER BY id DESC LIMIT 1")
    card = cursor.fetchone()[0] if cursor.rowcount else 0.0
    cursor.execute(
        "SELECT balance FROM finance WHERE account='cash' AND type='balance' ORDER BY id DESC LIMIT 1")
    cash = cursor.fetchone()[0] if cursor.rowcount else 0.0
    cursor.close()
    conn.close()
    await update.message.reply_text(
        f"💳 Карта: {card:.2f} zł\n"
        f"💵 Наличные: {cash:.2f} zł\n"
        f"💰 Общий: {total:.2f} zł"
    )


async def setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Используй: /setbalance card 5000.50")
        return
    acc = context.args[0].lower()
    try:
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом!")
        return
    if acc in ["card", "cash"]:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO finance (account, balance, type, category, amount, description, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (acc, amount, "balance", None, 0.0, "Установлен баланс", datetime.now()))
        conn.commit()
        cursor.close()
        conn.close()
        await update.message.reply_text(f"Баланс {acc} установлен на {amount:.2f} zł")
    else:
        await update.message.reply_text("Доступные счета: card, cash")

# --- Обработка сообщений ---


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # --- Главное меню ---
    if text == "📊 Баланс":
        await balance(update, context)
        return
    elif text == "⚙️ Установить баланс":
        keyboard = [["💳 Карта", "💵 Наличные"], ["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        context.user_data["setbalance_mode"] = True
        await update.message.reply_text("Выберите счёт для установки баланса:", reply_markup=reply_markup)
        return
    elif text in ["💳 Карта", "💵 Наличные"]:
        context.user_data["account"] = "card" if text == "💳 Карта" else "cash"
        keyboard = [["➕ Доход", "➖ Расход"], ["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"Выбран счёт: {text}. Что сделать?", reply_markup=reply_markup)
        return
    elif text == "🔙 Назад":
        context.user_data.clear()
        reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
        return
    elif text == "📜 История":
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT account, type, category, amount, description, date
            FROM finance
            WHERE type IN ('income','expense')
            ORDER BY id DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        if not rows:
            await update.message.reply_text("История пуста.")
        else:
            msg = ""
            for row in rows:
                acc, op_type, cat, amt, desc, date = row
                msg += f"{date.strftime('%Y-%m-%d %H:%M')} | {op_type} | {acc} | {cat} | {amt:.2f} zł | {desc}\n"
            await update.message.reply_text(msg)
        return

    # --- Доход/Расход ---
    if context.user_data.get("action") in ["income", "expense"] and "category" not in context.user_data:
        if text == "🔙 Назад":
            context.user_data.pop("action", None)
            keyboard = [["➕ Доход", "➖ Расход"], ["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Выбери действие:", reply_markup=reply_markup)
            return
        context.user_data["category"] = text
        keyboard = [["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Введите сумму:", reply_markup=reply_markup)
        return

    if context.user_data.get("action") in ["income", "expense"] and "category" in context.user_data and "amount" not in context.user_data:
        if text == "🔙 Назад":
            context.user_data.pop("category", None)
            categories = income_categories if context.user_data.get(
                "action") == "income" else expense_categories
            keyboard = [categories[i:i+2]
                        for i in range(0, len(categories), 2)] + [["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Выбери категорию:", reply_markup=reply_markup)
            return
        try:
            amount = float(text.replace(",", "."))
            context.user_data["amount"] = amount
            keyboard = [["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Введите описание:", reply_markup=reply_markup)
        except ValueError:
            await update.message.reply_text("Введите число!")
        return

    if context.user_data.get("action") in ["income", "expense"] and "category" in context.user_data and "amount" in context.user_data:
        if text == "🔙 Назад":
            context.user_data.pop("amount", None)
            keyboard = [["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Введите сумму:", reply_markup=reply_markup)
            return

        # --- Сохраняем операцию в БД ---
        acc = context.user_data["account"]
        op_type = context.user_data["action"]
        category = context.user_data["category"]
        amount = context.user_data["amount"]
        description = text
        date = datetime.now()
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO finance (account, balance, type, category, amount, description, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (acc, None, op_type, category, amount, description, date))
        # --- Обновляем баланс ---
        cursor.execute(f"""
            SELECT balance FROM finance WHERE account=%s AND type='balance' ORDER BY id DESC LIMIT 1
        """, (acc,))
        last_balance = cursor.fetchone()[0] or 0.0
        new_balance = last_balance + amount if op_type == "income" else last_balance - amount
        cursor.execute("""
            INSERT INTO finance (account, balance, type, category, amount, description, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (acc, new_balance, "balance", None, 0.0, "Обновлен баланс", date))
        conn.commit()
        cursor.close()
        conn.close()

        await update.message.reply_text(f"{op_type.title()} {amount:.2f} zł добавлен в {acc}")
        context.user_data.clear()
        reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
        return

    # --- Выбор действия ---
    if text == "➕ Доход":
        if "account" not in context.user_data:
            await update.message.reply_text("Сначала выбери счёт: 💳 Карта или 💵 Наличные")
            return
        context.user_data["action"] = "income"
        keyboard = [income_categories[i:i+2]
                    for i in range(0, len(income_categories), 2)] + [["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выбери категорию дохода:", reply_markup=reply_markup)
        return
    if text == "➖ Расход":
        if "account" not in context.user_data:
            await update.message.reply_text("Сначала выбери счёт: 💳 Карта или 💵 Наличные")
            return
        context.user_data["action"] = "expense"
        keyboard = [expense_categories[i:i+2]
                    for i in range(0, len(expense_categories), 2)] + [["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выбери категорию расхода:", reply_markup=reply_markup)
        return

# --- Запуск ---


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setbalance", setbalance))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url="https://finance-bot-m5g4.onrender.com"
    )


if __name__ == "__main__":
    main()
