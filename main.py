import psycopg2
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ==== Настройки подключения ====
DB_NAME = "finance_db_n1r6"
DB_USER = "finance_db_n1r6_user"
DB_PASSWORD = "UMwaOgl9g8OtSsnqRcTst8qaMEYrVePs"
DB_HOST = "dpg-d2va4th5pdvs73b7397g-a"
DB_PORT = "5432"

TOKEN = "8355466631:AAFcU12xq0wsMosK1AjoYXK5tpS2y4y-Ji0"

# ==== Категории ====
income_categories = ["Зарплата", "Подарки", "Другое"]
expense_categories = ["Питание", "Транспорт",
                      "Развлечения", "Коммунальные", "Другое"]

# ==== Главное меню ====
keyboard_main = [["💳 Карта", "💵 Наличные"],
                 ["📊 Баланс", "⚙️ Установить баланс"],
                 ["📜 История"]]

# ==== Подключение к базе ====


def get_connection():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )

# ==== Хелперы ====


def get_balances():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT account, SUM(amount) FROM finance GROUP BY account")
    rows = cursor.fetchall()
    balances = {"card": 0.0, "cash": 0.0}
    for account, total in rows:
        if account in balances:
            balances[account] = float(total)
    cursor.close()
    conn.close()
    return balances


def add_operation(op_type, account, category, amount, description):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO finance (type, account, category, amount, description, date) VALUES (%s,%s,%s,%s,%s,%s)",
        (op_type, account, category, amount, description, datetime.now())
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_history(limit=10):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT type, account, category, amount, description, date FROM finance ORDER BY id DESC LIMIT %s", (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows[::-1]  # Сначала старые

# ==== Команды ====


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
    await update.message.reply_text("Привет! Я бот для учёта доходов и расходов 💰\nВыбери действие:", reply_markup=reply_markup)


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    balances = get_balances()
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
    if acc in ["card", "cash"]:
        add_operation("balance", acc, "Установка баланса",
                      amount, "Установлен баланс через команду")
        await update.message.reply_text(f"Баланс {acc} установлен на {amount:.2f} zł")
    else:
        await update.message.reply_text("Доступные счета: card, cash")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_operations = get_history(10)
    if not last_operations:
        await update.message.reply_text("История пуста.")
    else:
        msg = ""
        for op_type, account, category, amount, description, date in last_operations:
            msg += f"{date.strftime('%Y-%m-%d %H:%M')} | {op_type} | {account} | {category} | {amount:.2f} zł | {description}\n"
        await update.message.reply_text(msg)

# ==== Обработка сообщений через кнопки ====


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # Главное меню
    if text == "📊 Баланс":
        await balance(update, context)
        return
    elif text == "📜 История":
        await history(update, context)
        return

    # Выбор счета
    if text in ["💳 Карта", "💵 Наличные"]:
        context.user_data["account"] = "card" if text == "💳 Карта" else "cash"
        keyboard = [["➕ Доход", "➖ Расход"], ["🔙 Назад"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"Выбран счёт: {text}. Что сделать?", reply_markup=reply_markup)
        return

    # Выбор действия
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

    # Категория
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

    # Сумма
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

    # Описание
    if context.user_data.get("action") in ["income", "expense"] and "category" in context.user_data and "amount" in context.user_data:
        if text == "🔙 Назад":
            context.user_data.pop("amount", None)
            keyboard = [["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Введите сумму:", reply_markup=reply_markup)
            return
        # сохраняем операцию
        account = context.user_data["account"]
        amount = context.user_data["amount"]
        category = context.user_data["category"]
        op_type = context.user_data["action"]
        description = text
        add_operation(op_type, account, category,
                      amount if op_type == "income" else -amount, description)
        await update.message.reply_text(f"{op_type.title()} {amount:.2f} zł добавлен в {account}")
        context.user_data.clear()
        reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

# ==== Запуск бота ====


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("setbalance", setbalance))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
