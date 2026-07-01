import sqlite3

conn = sqlite3.connect("store.db")
cursor = conn.cursor()

try:
    cursor.execute("""
        ALTER TABLE orders
        ADD COLUMN payment_status TEXT DEFAULT 'Pending'
    """)
    conn.commit()
    print("Column added successfully")
except Exception as e:
    print(e)

conn.close()