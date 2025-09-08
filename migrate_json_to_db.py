import os
import json
import psycopg2
from dotenv import load_dotenv
from datetime import datetime

DATA_FILE = "data.json"

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

with open(DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# Обновляем балансы
for acc in ["card", "cash"]:
    cursor.execute(
        "INSERT INTO accounts (name, balance) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET balance = EXCLUDED.balance",
        (acc, data.get(acc, 0.0))
    )

# Переносим историю операций
for op in data.get("history", []):
    cursor.execute(
        """
        INSERT INTO operations (type, account, amount, category, description, date)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            op["type"],
            op["account"],
            op["amount"],
            op["category"],
            op["description"],
            datetime.strptime(op["date"], "%Y-%m-%d %H:%M")
        )
    )

conn.commit()
cursor.close()
conn.close()
print("Данные успешно перенесены в базу данных!")