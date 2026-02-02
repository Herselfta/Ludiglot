
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1] / "src"))
from ludiglot.core.wwise_hash import WwiseHash

def check():
    h = WwiseHash()
    name = "vo_Main_LahaiRoi_3_2_5_22"
    print(f"Name: {name}")
    print(f"Hash: {h.hash_int(name)}")
    
    # Also check without prefix just in case
    print(f"Main_: {h.hash_int('Main_LahaiRoi_3_2_5_22')}")

if __name__ == "__main__":
    check()
