
import sqlite3
from pathlib import Path

def list_ids():
    db = Path("e:/Ludiglot/data/ConfigDB/db_plot_audio.db")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cursor = conn.cursor()
    cursor.execute("SELECT Id FROM plotaudio WHERE Id LIKE 'Main_LahaiRoi_3_2_5_%' ORDER BY Id")
    ids = [r[0] for r in cursor.fetchall()]
    for i in ids:
        print(i)
    conn.close()

if __name__ == "__main__":
    list_ids()
