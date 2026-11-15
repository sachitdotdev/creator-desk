import sqlite3, json, glob, sys
db_files = glob.glob("C:/Sachit/Creator Desk/data/*.db") + glob.glob("C:/Sachit/Creator Desk/backend/*.db")
if not db_files: sys.exit("DB not found")
conn = sqlite3.connect(db_files[0])
cursor = conn.cursor()
cursor.execute("SELECT id, name, config FROM templates")
for t_id, t_name, config_json in cursor.fetchall():
    config = json.loads(config_json)
    config["background_music"] = "C:/Sachit/Creator Desk/backend/assets/music/lofi.mp3"
    config["background_music_volume"] = 0.25
    config["background_music_duck"] = True
    cursor.execute("UPDATE templates SET config = ? WHERE id = ?", (json.dumps(config), t_id))
    print(f"Updated {t_name}")
conn.commit()
conn.close()
print("Done")