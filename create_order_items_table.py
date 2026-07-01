# create_order_items_table.py

import sqlite3

conn = sqlite3.connect("store.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    product_id INTEGER,
    price REAL
)
""")

conn.commit()
conn.close()

print("Order items table created.")