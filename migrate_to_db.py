import psycopg2
import json
from datetime import datetime

# ==== Настройки подключения напрямую ====
DB_NAME = "finance_db_n1r6"
DB_USER = "finance_db_n1r6_user"
DB_PASSWORD = "UMwaOgl9g8OtSsnqRcTst8qaMEYrVePs"
DB_HOST = "dpg-d2va4th5pdvs73b7397g-a"
DB_PORT = "5432"

conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)
cursor = conn.cursor()

# ==== Создаем таблицу, если нет ====
cursor.execute("""
CREATE TABLE IF NOT EXISTS finance (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20),
    account VARCHAR(20),
    category VARCHAR(50),
    amount NUMERIC(12,2),
    description TEXT,
    date TIMESTAMP
)
""")
conn.commit()

# ==== Загружаем старые данные ====
DATA_FILE = "data.json"
try:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    data = {"card": 0.0, "cash": 0.0, "history": []}

# ==== Миграция истории ====
for op in data.get("history", []):
    cursor.execute(
        "INSERT INTO finance (type, account, category, amount, description, date) VALUES (%s,%s,%s,%s,%s,%s)",
        (op["type"], op["account"], op["category"],
         op["amount"], op["description"], op["date"])
    )

# ==== Миграция текущих балансов ====
if data.get("card", 0) != 0:
    cursor.execute(
        "INSERT INTO finance (type, account, category, amount, description, date) VALUES (%s,%s,%s,%s,%s,%s)",
        ("balance", "card", "Баланс на миграцию",
         data["card"], "Изначальный баланс", datetime.now())
    )
if data.get("cash", 0) != 0:
    cursor.execute(
        "INSERT INTO finance (type, account, category, amount, description, date) VALUES (%s,%s,%s,%s,%s,%s)",
        ("balance", "cash", "Баланс на миграцию",
         data["cash"], "Изначальный баланс", datetime.now())
    )

conn.commit()
cursor.close()
conn.close()
print("✅ Миграция завершена!")
