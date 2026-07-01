import sqlite3

conn = sqlite3.connect("store.db")

cursor = conn.cursor()

cursor.execute("""
INSERT INTO products(name, price)
VALUES
('Hoodie', 2500)           
""")

conn.commit()

print("Products added!")

conn.close()