import sqlite3
import os

db_path = "backend/data/creatordesk.db"

def main():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(videos)")
        columns = cursor.fetchall()
        for col in columns:
            print(col)
        
        cursor.execute("SELECT id, filename, status FROM videos")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error querying database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
