import os
import json
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

# --- Загружаем переменные окружения ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL").strip()

# --- Загружаем старые данные ---
DATA_FILE = "data.json"
with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# --- Подключение к БД ---
try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    print("Подключение к БД успешно!")
except Exception as e:
    print("Ошибка подключения к БД:", e)
    exit()

# --- Создание таблицы, если нет ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS finance (
    id SERIAL PRIMARY KEY,
    account VARCHAR(10),
    balance NUMERIC(15,2),
    type VARCHAR(10),
    category VARCHAR(50),
    amount NUMERIC(15,2),
    description TEXT,
    date TIMESTAMP
)
""")
conn.commit()
print("Таблица создана или уже существует.")

# --- Вставляем балансы ---
for account in ["card", "cash"]:
    cursor.execute("""
        INSERT INTO finance (account, balance, type, category, amount, description, date)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
                   (account, data.get(account, 0.0), "balance",
                    None, 0.0, "Изначальный баланс", datetime.now())
                   )

# --- Вставляем историю ---
for op in data.get("history", []):
    cursor.execute("""
        INSERT INTO finance (account, balance, type, category, amount, description, date)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        op["account"],
        None,
        op["type"],
        op.get("category"),
        op["amount"],
        op.get("description", ""),
        datetime.strptime(op["date"], "%Y-%m-%d %H:%M")
    ))

conn.commit()
print("Данные успешно перенесены!")

cursor.close()
conn.close()
