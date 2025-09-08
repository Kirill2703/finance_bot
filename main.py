import os
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# --- Категории ---
income_categories = ["Зарплата", "Подарки", "Другое"]
expense_categories = ["Питание", "Транспорт",
                      "Развлечения", "Коммунальные", "Другое"]

# --- Главное меню ---
keyboard_main = [["💳 Карта", "💵 Наличные"],
                 ["📊 Баланс", "⚙️ Установить баланс"],
                 ["📜 История"]]

# --- Подключение к БД ---
load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
TOKEN = os.getenv("BOT_TOKEN")


def get_balance():
    with conn.cursor() as cursor:
        cursor.execute("SELECT name, balance FROM accounts")
        rows = cursor.fetchall()
        balances = {row[0]: float(row[1]) for row in rows}
        return balances.get("card", 0.0), balances.get("cash", 0.0)


def set_balance(acc, amount):
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO accounts (name, balance) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET balance = EXCLUDED.balance",
            (acc, amount)
        )
        conn.commit()


def add_operation(op_type, acc, amount, category, description, date):
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO operations (type, account, amount, category, description, date) VALUES (%s, %s, %s, %s, %s, %s)",
            (op_type, acc, amount, category, description, date)
        )
        # Обновляем баланс
        sign = 1 if op_type == "income" else -1
        cursor.execute(
            "UPDATE accounts SET balance = balance + %s WHERE name = %s",
            (amount * sign, acc)
        )
        conn.commit()


def get_history(limit=10):
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT date, type, account, category, amount, description FROM operations ORDER BY date DESC LIMIT %s",
            (limit,)
        )
        return cursor.fetchall()


def clear_history_db():
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM operations")
        conn.commit()

# --- Команды ---


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я бот для учёта доходов и расходов 💰\nВыбери действие:",
        reply_markup=reply_markup
    )


async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history_db()
    await update.message.reply_text("История очищена ✅")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    card, cash = get_balance()
    total = card + cash
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
        set_balance(acc, amount)
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
                set_balance(acc, amount)
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
        card, cash = get_balance()
        total = card + cash
        await update.message.reply_text(
            f"💳 Карта: {card:.2f} zł\n"
            f"💵 Наличные: {cash:.2f} zł\n"
            f"💰 Общий: {total:.2f} zł"
        )
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
        history = get_history(10)
        if not history:
            await update.message.reply_text("История пуста.")
        else:
            msg = ""
            for op in history:
                date, op_type, acc, category, amount, description = op
                msg += f"{date.strftime('%Y-%m-%d %H:%M')} | {op_type} | {acc} | {category} | {amount:.2f} zł | {description}\n"
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

    # --- Ввод описания ---
    if context.user_data.get("action") in ["income", "expense"] and "category" in context.user_data and "amount" in context.user_data:
        if text == "🔙 Назад":
            context.user_data.pop("amount", None)
            keyboard = [["🔙 Назад"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Введите сумму:", reply_markup=reply_markup)
            return
        # сохраняем операцию
        description = text
        acc = context.user_data["account"]
        amount = context.user_data["amount"]
        op_type = context.user_data["action"]
        category = context.user_data["category"]
        date = datetime.now()
        add_operation(op_type, acc, amount, category, description, date)
        await update.message.reply_text(f"{op_type.title()} {amount:.2f} zł добавлен в {acc}")
        context.user_data.clear()
        reply_markup = ReplyKeyboardMarkup(keyboard_main, resize_keyboard=True)
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)

# --- Запуск бота ---


async def delete_webhook(application):
    await application.bot.delete_webhook(drop_pending_updates=True)


def main():
    app = Application.builder().token(TOKEN).build()
    app.post_init = delete_webhook
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
