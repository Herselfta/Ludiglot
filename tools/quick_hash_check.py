
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1] / "src"))
from ludiglot.core.wwise_hash import WwiseHash

def check(h_val, label):
    h = WwiseHash()
    print(f"--- {label}: {h_val} ---")
    # Try common patterns
    for p in ["", "vo_", "play_vo_"]:
        for s in ["", "_f", "_m"]:
            name = f"{p}main_lahairoi_3_2_8_6{s}"
            if h.hash_int(name) == h_val:
                print(f"MATCH: {name}")
                return
    print("No simple match found.")

if __name__ == "__main__":
    check(3774913325, "Main_LahaiRoi_3_2_8_6")
    check(756064232, "Problematic Hash")
    check(2499622111, "Latest Hash 1")
    check(3230553469, "Latest Hash 2")
