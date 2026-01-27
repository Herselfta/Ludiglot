import os
import subprocess
import shutil
from pathlib import Path

class ToolManager:
    """
    Manages external tools like FModelCLI (Cloning, Building, and Updating)
    """
    def __init__(self):
        self.root_dir = Path(__file__).parents[3] # e:\Ludiglot
        self.tools_dir = self.root_dir / "tools"
        self.fmodel_cli_repo = "https://github.com/Herselfta/FModelCLI.git"
        self.fmodel_cli_exe = self.tools_dir / "FModelCLI.exe"
        
        # Dev path (sibling directory)
        self.dev_fmodel_cli_path = self.root_dir.parent / "FModelCLI"

    def ensure_fmodel_cli(self, force_build=False):
        """
        Ensures FModelCLI.exe is available. 
        If not, tries to clone and build it.
        """
        if self.fmodel_cli_exe.exists() and not force_build:
            return True

        print("[ToolManager] FModelCLI.exe not found. Attempting setup...")

        # Case 1: If we are in the dev environment and the sibling project exists
        if self.dev_fmodel_cli_path.exists():
            print(f"[ToolManager] Found local FModelCLI project at {self.dev_fmodel_cli_path}")
            return self._build_from_source(self.dev_fmodel_cli_path)

        # Case 2: Clone and build in tools directory
        target_src_dir = self.tools_dir / "FModelCLI_src"
        if not target_src_dir.exists():
            print(f"[ToolManager] Cloning FModelCLI from {self.fmodel_cli_repo}...")
            if not self._clone_repo(target_src_dir):
                return False
        
        return self._build_from_source(target_src_dir)

    def _clone_repo(self, target_dir):
        try:
            subprocess.run(["git", "clone", "--recursive", self.fmodel_cli_repo, str(target_dir)], check=True)
            return True
        except Exception as e:
            print(f"[ToolManager] Clone failed: {e}")
            return False

    def _build_from_source(self, source_dir):
        print(f"[ToolManager] Building FModelCLI from {source_dir}...")
        try:
            # Call our powershell script
            script_path = source_dir / "sync_upstream.ps1"
            if not script_path.exists():
                print(f"[ToolManager] sync_upstream.ps1 not found in {source_dir}")
                return False

            subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)], cwd=str(source_dir), check=True)
            
            # Copy result to tools/
            exe_source = source_dir / "dist" / "FModelCLI.exe"
            if exe_source.exists():
                self.tools_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(exe_source, self.fmodel_cli_exe)
                print(f"[ToolManager] Successfully deployed FModelCLI.exe to {self.fmodel_cli_exe}")
                return True
            else:
                print(f"[ToolManager] Build failed: Output exe not found at {exe_source}")
                return False
        except Exception as e:
            print(f"[ToolManager] Build failed: {e}")
            return False

if __name__ == "__main__":
    # Test script
    tm = ToolManager()
    tm.ensure_fmodel_cli()
