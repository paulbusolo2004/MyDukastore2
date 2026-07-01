"""
One-time migration script.
Run this ONCE from your project folder: python migrate_orders.py

It adds a 'checkout_request_id' column to your existing orders table,
used to match M-Pesa payment callbacks back to the correct order.
"""

import sqlite3

conn = sqlite3.connect("store.db")
cur = conn.cursor()

cur.execute("PRAGMA table_info(orders)")
columns = [col[1] for col in cur.fetchall()]

if "checkout_request_id" not in columns:
    cur.execute("ALTER TABLE orders ADD COLUMN checkout_request_id TEXT")
    conn.commit()
    print("Done: added 'checkout_request_id' column to orders table.")
else:
    print("'checkout_request_id' column already exists - nothing to do.")

conn.close()
