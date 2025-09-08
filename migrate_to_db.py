import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL").strip()

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# Удалим старую таблицу, если она есть
cursor.execute("DROP TABLE IF EXISTS finance;")

# Создаём заново с балансом
cursor.execute("""
CREATE TABLE finance (
    id SERIAL PRIMARY KEY,
    account TEXT,
    balance NUMERIC,
    type TEXT,
    category TEXT,
    amount NUMERIC,
    description TEXT,
    date TIMESTAMP
)
""")

conn.commit()
cursor.close()
conn.close()

print("✅ Таблица finance создана с balance")
