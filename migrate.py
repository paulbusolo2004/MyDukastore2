"""
One-time migration script.
Run this ONCE from your project folder: python migrate.py

It adds a 'category' column to your existing products table
without touching any existing data.
"""

import sqlite3

conn = sqlite3.connect("store.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(products)")
columns = [col[1] for col in cur.fetchall()]

if "category" not in columns:
    cur.execute("ALTER TABLE products ADD COLUMN category TEXT DEFAULT 'Uncategorized'")
    conn.commit()
    print("Done: added 'category' column to products table.")
    print("Existing products were set to 'Uncategorized' - edit them in /admin to assign real categories.")
else:
    print("'category' column already exists - nothing to do.")

conn.close()
