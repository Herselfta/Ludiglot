
import sqlite3
from pathlib import Path
import re
import sys

def dump_plotaudio_blobs(target):
    db_path = Path("e:/Ludiglot/data/ConfigDB/db_plot_audio.db")
    if not db_path.exists():
        print("DB not found")
        return
        
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
    
    print(f"--- Searching and Dumping Blob for {target} ---")
    
    cursor.execute("SELECT Id, BinData FROM plotaudio WHERE Id = ?", (target,))
    row = cursor.fetchone()
    if row:
        id_val, blob = row
        print(f"ID: {id_val}")
        print(f"Blob Length: {len(blob)}")
        
        # Simple string extractor
        import string
        printable = set(string.printable.encode('ascii'))
        strings = []
        curr = bytearray()
        for b in blob:
            if b in printable and b > 31:
                curr.append(b)
            else:
                if len(curr) >= 4:
                    strings.append(curr.decode('ascii', errors='ignore'))
                curr = bytearray()
        
        print(f"Strings: {strings}")
        
    else:
        print("Target ID not found.")
    conn.close()

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "Main_LahaiRoi_3_2_5_20"
    dump_plotaudio_blobs(t)
