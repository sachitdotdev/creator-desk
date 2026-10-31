import sqlite3
import os

db_path = os.path.abspath("backend/data/creatordesk.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Query for clips with 'error' status
    cursor.execute("SELECT video_id, title, error_message FROM clips WHERE status = 'error'")
    rows = cursor.fetchall()
    
    if not rows:
        print("No clips with 'error' status found.")
    else:
        print(f"Found {len(rows)} clips with 'error' status:")
        for row in rows:
            print(f"VideoID: {row[0]}, Title: {row[1]}, Error: {row[2]}")

except Exception as e:
    print(f"An error occurred: {e}")
finally:
    conn.close()
