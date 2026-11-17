import sqlite3
import glob
import os

# Find the database file
db_files = glob.glob("C:/Projects Openhands/Active/Creator Desk/data/*.db") + glob.glob("C:/Projects Openhands/Active/Creator Desk/data/*.sqlite")

if not db_files:
    print("❌ Could not find a database file in the data folder.")
    exit()

DB_PATH = db_files[0]
print(f"Found database: {DB_PATH}")

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    old_path = "C:\\Sachit\\Creator Desk"
    new_path = "C:\\Projects Openhands\\Active\\Creator Desk"

    print(f"Replacing '{old_path}' with '{new_path}'...")

    # 1. Update the videos table
    cursor.execute("UPDATE videos SET path = REPLACE(path, ?, ?)", (old_path, new_path))
    print(f"Updated {cursor.rowcount} video paths.")

    # 2. Update the clips table (output paths only)
    cursor.execute("UPDATE clips SET output_path = REPLACE(output_path, ?, ?)", (old_path, new_path))
    print(f"Updated {cursor.rowcount} clip paths.")

    conn.commit()
    conn.close()
    print("✅ Database paths successfully updated!")
    
except Exception as e:
    print(f"❌ Error updating database: {e}")