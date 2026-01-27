import subprocess
import os
from pathlib import Path

class NativeExtractor:
    def __init__(self, tool_path="./tools/FModelCLI.exe"):
        # Resolve absolute path relative to CWD (usually project root)
        # If tool_path is relative, make it absolute
        self.tool_path = Path(tool_path).resolve()
        
        # If not found, try to look relative to this file? 
        # But usually running from root is standard.
        if not self.tool_path.exists():
            # Fallback: check if we are in src/ludiglot/infrastructure and tools is up 3 levels
            # rooted at e:\Ludiglot
            fallback = Path(__file__).parents[3] / "tools" / "FModelCLI.exe"
            if fallback.exists():
                self.tool_path = fallback

    def run_extraction(self, game_dir, aes_key, output_dir, filter_keyword):
        """
        Calls the C# core for precise extraction
        """
        if not self.tool_path.exists():
            print(f"[!] Critical: FModelCLI.exe not found at {self.tool_path}")
            return False

        # Ensure output directory exists
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.tool_path),
            str(game_dir),
            aes_key,
            str(output_dir),
            filter_keyword  # e.g. "ConfigDB" or "Audio"
        ]

        print(f"[Native] Calling FModelCLI with filter: {filter_keyword}...")
        
        try:
            # Live log output
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True, 
                encoding='utf-8',
                errors='replace' # Prevent crashes on Chinese paths
            )

            for line in process.stdout:
                line = line.strip()
                if line:
                    print(f"    | {line}")

            process.wait()
            
            if process.returncode == 0:
                print(f"[Native] Extraction success for {filter_keyword}")
                return True
            else:
                print(f"[Native] Extraction failed with code {process.returncode}")
                return False
                
        except Exception as e:
            print(f"[Native] Exception during execution: {e}")
            return False
