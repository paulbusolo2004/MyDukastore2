import sqlite3

conn = sqlite3.connect("store.db")
cursor = conn.cursor()

try:
    cursor.execute("""
        ALTER TABLE products
        ADD COLUMN image TEXT
    """)
    print("Image column added!")
except:
    print("Image column already exists.")

conn.commit()
conn.close()