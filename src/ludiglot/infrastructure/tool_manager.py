import os
import shutil
from pathlib import Path

class ToolManager:
    """
    Manages external tools like FModelCLI.
    Decoupled from the source code, focuses on binary distribution.
    """
    def __init__(self):
        self.root_dir = Path(__file__).resolve().parents[3] # e:\Ludiglot
        self.tools_dir = self.root_dir / "tools"
        self.fmodel_cli_exe = self.tools_dir / "FModelCLI.exe"
        
        # GitHub Release Info (for manual download instructions)
        self.repo_owner = "Herselfta"
        self.repo_name = "FModelCLI"

    def ensure_fmodel_cli(self, force_update=False):
        """
        Ensures FModelCLI.exe is available by checking local paths or prompting for manual download.
        For security reasons, automatic download is disabled.
        """
        if self.fmodel_cli_exe.exists() and not force_update:
            return True

        self.tools_dir.mkdir(parents=True, exist_ok=True)

        # 1. 优先检查本地开发路径 (解耦后的路径)
        dev_paths = [
            Path("E:/FModelCLI/dist/FModelCLI.exe"),
            Path("E:/FModelCLI/FModelCLI/bin/Release/net8.0/win-x64/publish/FModelCLI.exe")
        ]
        
        for dev_path in dev_paths:
            if dev_path.exists():
                print(f"[ToolManager] Found local dev build at {dev_path}, copying...")
                shutil.copy2(dev_path, self.fmodel_cli_exe)
                return True

        # 2. 如果本地没有，提示手动下载（安全考虑）
        print(f"[ToolManager] FModelCLI.exe not found.")
        print(f"[ToolManager] For security reasons, automatic download has been disabled.")
        print(f"[ToolManager] Please manually download FModelCLI.exe from:")
        print(f"[ToolManager]   https://github.com/{self.repo_owner}/{self.repo_name}/releases")
        print(f"[ToolManager] Verify the file checksum/signature, then place it at:")
        print(f"[ToolManager]   {self.fmodel_cli_exe}")
        return False

if __name__ == "__main__":
    tm = ToolManager()
    tm.ensure_fmodel_cli(force_update=True)
