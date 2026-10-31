import sqlite3
import os

db_path = os.path.abspath("backend/data/creatordesk.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables in database:")
    for table in tables:
        print(f"- {table[0]}")
        
    # Try to get columns of each table if it's not sqlite_sequence
    for table in tables:
        if table[0] != "sqlite_sequence":
            print(f"Columns in {table[0]}:")
            cursor.execute(f"PRAGMA table_info({table[0]})")
            for col in cursor.fetchall():
                print(f"  {col[1]} ({col[2]})")
            print("-" * 20)

except Exception as e:
    print(f"An error occurred: {e}")
finally:
    conn.close()
