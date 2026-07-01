import sqlite3

conn = sqlite3.connect("store.db")
cursor = conn.cursor()

try:
    cursor.execute("""
        ALTER TABLE products
        ADD COLUMN description TEXT
    """)
    print("Description column added!")
except:
    print("Description column already exists.")

conn.commit()
conn.close()