
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1] / "src"))
from ludiglot.core.audio_extract import find_bnk_for_event

def check_event(event_name):
    bnk_root = Path("e:/Ludiglot/data/WwiseAudio_Generated/Event/zh")
    bnk_path = find_bnk_for_event(bnk_root, event_name)
    print(f"Event '{event_name}' in BNK: {bnk_path}")

if __name__ == "__main__":
    check_event("vo_Main_LahaiRoi_3_2_5_20")
    check_event("vo_Main_LahaiRoi_3_2_8_6")
    check_event("vo_Main_LahaiRoi_3_2_5_22")
