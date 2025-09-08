import os
import psycopg2
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

DATA_FILE = "data.json"

# --- Загрузка старых данных ---
try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    data = {"card": 0.0, "cash": 0.0, "history": []}

# --- Подключение к PostgreSQL ---
load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

# Создаем таблицу, если еще нет
cursor.execute("""
CREATE TABLE IF NOT EXISTS finance (
    id SERIAL PRIMARY KEY,
    account TEXT,
    type TEXT,
    category TEXT,
    amount NUMERIC,
    description TEXT,
    date TIMESTAMP
);
""")
conn.commit()

# --- Мигрируем старые данные из data.json в БД ---
if data.get("history"):
    for op in data["history"]:
        cursor.execute("""
        INSERT INTO finance (account, type, category, amount, description, date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING;
        """, (op["account"], op["type"], op["category"], op["amount"], op["description"], op["date"]))
    conn.commit()

# --- Загружаем текущие балансы ---
cursor.execute("SELECT account, SUM(amount) FROM finance GROUP BY account;")
rows = cursor.fetchall()
balances = {"card": 0.0, "cash": 0.0}
for row in rows:
    balances[row[0]] = float(row[1])

TOKEN = os.getenv("BOT_TOKEN")

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


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("DELETE FROM finance;")
    conn.commit()
    balances["card"] = 0.0
    balances["cash"] = 0.0
    await update.message.reply_text("История очищена ✅")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = balances["card"] + balances["cash"]
    await update.message.reply_text(
        f"💳 Карта: {balances['card']:.2f} zł\n"
        f"💵 Наличные: {balances['cash']:.2f} zł\n"
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
    if acc in balances:
        cursor.execute("DELETE FROM finance WHERE account=%s;", (acc,))
        cursor.execute(
            "INSERT INTO finance (account, type, category, amount, description, date) VALUES (%s, %s, %s, %s, %s, %s);",
            (acc, "setbalance", "init", amount,
             "Установлен баланс", datetime.now())
        )
        conn.commit()
        balances[acc] = amount
        await update.message.reply_text(f"Баланс {acc} установлен на {amount:.2f} zł")
    else:
        await update.message.reply_text("Доступные счета: card, cash")

# --- Обработка сообщений ---


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # --- Установка баланса через кнопки ---
    if context.user_data.get("setbalance_mode"):
        if text in ["💳 Карта", "💵 Наличные"]:
            context.user_data["account"] = "card" if text == "💳 Карта" else "cash"
            context.user_data["action"] = "setbalance_input"
            keyboard = [["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(f"Введите ваш текущий баланс для {text}:", reply_markup=reply_markup)
            return
        elif context.user_data.get("action") == "setbalance_input":
            if text == "🔙 Назад":
                context.user_data.clear()
                reply_markup = ReplyKeyboardMarkup(
                    keyboard_main, resize_keyboard=True)
                await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
                return
            try:
                amount = float(text.replace(",", "."))
                acc = context.user_data["account"]
                cursor.execute("DELETE FROM finance WHERE account=%s;", (acc,))
                cursor.execute(
                    "INSERT INTO finance (account, type, category, amount, description, date) VALUES (%s, %s, %s, %s, %s, %s);",
                    (acc, "setbalance", "init", amount,
                     "Установлен баланс", datetime.now())
                )
                conn.commit()
                balances[acc] = amount
                await update.message.reply_text(f"Баланс {acc} установлен на {amount:.2f} zł")
                context.user_data.clear()
                reply_markup = ReplyKeyboardMarkup(
                    keyboard_main, resize_keyboard=True)
                await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
            except ValueError:
                await update.message.reply_text("Введите число!")
            return

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

    elif text == "➕ Доход":
        if "account" not in context.user_data:
            await update.message.reply_text("Сначала выбери счёт: 💳 Карта или 💵 Наличные")
            return
        context.user_data["action"] = "income"
        keyboard = [income_categories[i:i+2]
                    for i in range(0, len(income_categories), 2)] + [["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выбери категорию дохода:", reply_markup=reply_markup)
        return

    elif text == "➖ Расход":
        if "account" not in context.user_data:
            await update.message.reply_text("Сначала выбери счёт: 💳 Карта или 💵 Наличные")
            return
        context.user_data["action"] = "expense"
        keyboard = [expense_categories[i:i+2]
                    for i in range(0, len(expense_categories), 2)] + [["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выбери категорию расхода:", reply_markup=reply_markup)
        return

    elif text == "🔙 Назад":
        context.user_data.clear()
        reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)
        return

    elif text == "📜 История":
        cursor.execute(
            "SELECT date, type, account, category, amount, description FROM finance ORDER BY id DESC LIMIT 10;")
        last_operations = cursor.fetchall()
        if not last_operations:
            await update.message.reply_text("История пуста.")
        else:
            msg = ""
            for op in reversed(last_operations):
                msg += f"{op[0]} | {op[1]} | {op[2]} | {op[3]} | {op[4]:.2f} zł | {op[5]}\n"
            await update.message.reply_text(msg)
        return

    # --- Выбор категории ---
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

    # --- Ввод суммы ---
    if context.user_data.get("action") in ["income", "expense"] and "category" in context.user_data and "amount" not in context.user_data:
        if text == "🔙 Назад":
            context.user_data.pop("category", None)
            keyboard = [income_categories[i:i+2] for i in range(0, len(income_categories), 2)] if context.user_data.get(
                "action") == "income" else [expense_categories[i:i+2] for i in range(0, len(expense_categories), 2)]
            keyboard += [["🔙 Назад"]]
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

    # --- Ввод описания и сохранение ---
    if context.user_data.get("action") in ["income", "expense"] and "category" in context.user_data and "amount" in context.user_data:
        if text == "🔙 Назад":
            context.user_data.pop("amount", None)
            keyboard = [["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Введите сумму:", reply_markup=reply_markup)
            return
        description = text
        acc = context.user_data["account"]
        amount = context.user_data["amount"]
        op_type = context.user_data["action"]
        category = context.user_data["category"]
        date = datetime.now()
        cursor.execute("INSERT INTO finance (account, type, category, amount, description, date) VALUES (%s, %s, %s, %s, %s, %s);",
                       (acc, op_type, category, amount if op_type == "income" else -amount, description, date))
        conn.commit()
        balances[acc] += amount if op_type == "income" else -amount
        await update.message.reply_text(f"{op_type.title()} {amount:.2f} zł добавлен в {acc}")
        context.user_data.clear()
        reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

# --- Запуск бота ---


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setbalance", setbalance))
    app.add_handler(CommandHandler("clearhistory", clear_history))
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
