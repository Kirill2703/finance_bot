import os
import psycopg2
from dotenv import load_dotenv
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

DATA_FILE = "data.json"

# Загружаем данные или создаём новый файл
try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    data = {"card": 0.0, "cash": 0.0, "history": []}


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Загружаем токен из .env
load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

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
    data["history"] = []
    save_data()
    await update.message.reply_text("История очищена ✅")



async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = data["card"] + data["cash"]
    await update.message.reply_text(
        f"💳 Карта: {data['card']:.2f} zł\n"
        f"💵 Наличные: {data['cash']:.2f} zł\n"
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
    if acc in data:
        data[acc] = amount
        save_data()
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
                data[acc] = amount
                save_data()
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
        total = data["card"] + data["cash"]
        await update.message.reply_text(
            f"💳 Карта: {data['card']:.2f} zł\n"
            f"💵 Наличные: {data['cash']:.2f} zł\n"
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
        last_operations = data.get("history", [])[-10:]
        if not last_operations:
            await update.message.reply_text("История пуста.")
        else:
            msg = ""
            for op in last_operations:
                if isinstance(op, dict):
                    msg += f"{op['date']} | {op['type']} | {op['account']} | {op['category']} | {op['amount']:.2f} zł | {op['description']}\n"
                else:
                    msg += str(op) + "\n"
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
        date = datetime.now().strftime("%Y-%m-%d %H:%M")
        data[acc] += amount if op_type == "income" else -amount
        data["history"].append({
            "type": op_type,
            "account": acc,
            "amount": amount,
            "category": category,
            "description": description,
            "date": date
        })
        save_data()
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
