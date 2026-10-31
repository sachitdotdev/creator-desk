import sqlite3
import os

db_path = os.path.abspath("backend/data/creatordesk.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Query for videos with 'error' status
    cursor.execute("SELECT id, filename, path, status FROM videos WHERE status = 'error'")
    rows = cursor.fetchall()
    
    if not rows:
        print("No videos with 'error' status found.")
    else:
        print(f"Found {len(rows)} videos with 'error' status:")
        for row in rows:
            print(f"ID: {row[0]}, Filename: {row[1]}, Path: {row[2]}, Status: {row[3]}")

    # Query for videos with 'transcribing' status
    cursor.execute("SELECT id, filename, path, status FROM videos WHERE status = 'transcribing'")
    rows = cursor.fetchall()
    if rows:
        print(f"\nFound {len(rows)} videos with 'transcribing' status:")
        for row in rows:
            print(f"ID: {row[0]}, Filename: {row[1]}, Path: {row[2]}, Status: {row[3]}")

    # Query for clips with 'error' status
    cursor.execute("SELECT video_id, title, error_message FROM clips WHERE status = 'error'")
    rows = cursor.fetchall()
    if rows:
        print(f"\nFound {len(rows)} clips with 'error' status:")
        for row in rows:
            print(f"VideoID: {row[0]}, Title: {row[1]}, Error: {row[2]}")

except Exception as e:
    print(f"An error occurred: {e}")
finally:
    conn.close()
