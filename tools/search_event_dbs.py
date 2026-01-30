
import sqlite3
from pathlib import Path
import re

def search_event_in_all_dbs(target_event):
    root = Path("e:/Ludiglot/data/ConfigDB")
    target_hash = 4258170280 # vo_Main_LahaiRoi_3_2_5_22
    
    print(f"Searching for {target_event} / {target_hash} in DBs...")
    
    for db_file in root.glob("*.db"):
        try:
            conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            for tbl in tables:
                cursor.execute(f"PRAGMA table_info({tbl})")
                cols = [r[1] for r in cursor.fetchall()]
                
                # Check IDs
                cursor.execute(f"SELECT * FROM {tbl} LIMIT 0")
                # We can't easily search everything, but let's try some common columns
                search_cols = [c for c in cols if c.lower() in ("id", "key", "event", "name", "audio", "voice")]
                if search_cols:
                    for col in search_cols:
                        cursor.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col} LIKE ?", (f"%{target_event}%",))
                        if cursor.fetchone()[0] > 0:
                            print(f"FOUND string match in {db_file.name} -> {tbl}.{col}")
                
                # Check for hash in integer columns
                int_cols = [c for c in cols if "id" in c.lower() or "hash" in c.lower()]
                for col in int_cols:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {tbl} WHERE {col} = ?", (target_hash,))
                        if cursor.fetchone()[0] > 0:
                            print(f"FOUND hash match in {db_file.name} -> {tbl}.{col}")
                    except: pass
            conn.close()
        except: pass

if __name__ == "__main__":
    search_event_in_all_dbs("Main_LahaiRoi_3_2_5_22")
