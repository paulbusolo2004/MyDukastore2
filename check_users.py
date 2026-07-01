import sqlite3

conn = sqlite3.connect("store.db")

cursor = conn.cursor()

cursor.execute("PRAGMA table_info(users)")

columns = cursor.fetchall()

print("USERS TABLE COLUMNS:")
for col in columns:
    print(col)

conn.close()