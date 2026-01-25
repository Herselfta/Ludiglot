"""下载思源宋体字体文件"""
import urllib.request
from pathlib import Path

FONT_URL = "https://github.com/notofonts/noto-cjk/releases/download/Serif2.002/NotoSerifCJKsc-Regular.otf"
LICENSE_URL = "https://github.com/notofonts/noto-cjk/raw/main/Serif/OFL.txt"

def download_font():
    """下载思源宋体和许可证"""
    assets_dir = Path(__file__).parent.parent / "assets" / "fonts"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    font_path = assets_dir / "NotoSerifCJKsc-Regular.otf"
    license_path = assets_dir / "OFL.txt"
    
    if font_path.exists():
        print(f"✓ 字体已存在: {font_path}")
    else:
        print(f"下载字体: {FONT_URL}")
        print("文件较大 (~8MB)，请稍候...")
        urllib.request.urlretrieve(FONT_URL, font_path)
        print(f"✓ 已下载: {font_path}")
    
    if license_path.exists():
        print(f"✓ 许可证已存在: {license_path}")
    else:
        print(f"下载许可证: {LICENSE_URL}")
        urllib.request.urlretrieve(LICENSE_URL, license_path)
        print(f"✓ 已下载: {license_path}")
    
    print("\n思源字体安装完成！")
    print(f"字体文件: {font_path} ({font_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"许可证: {license_path}")

if __name__ == "__main__":
    download_font()
