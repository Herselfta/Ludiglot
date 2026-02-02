
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1] / "src"))
from ludiglot.core.text_builder import load_plot_audio_map

def test_plot_map():
    data_root = Path("e:/Ludiglot/data")
    full_map = load_plot_audio_map(data_root)
    print(f"Total entries: {len(full_map)}")
    
    target = "Main_LahaiRoi_3_2_5_20"
    print(f"{target} -> {full_map.get(target)}")

if __name__ == "__main__":
    test_plot_map()
