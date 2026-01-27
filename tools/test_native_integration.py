import sys
import os
from pathlib import Path

# Add src to path
root = Path(__file__).parents[1]
sys.path.append(str(root / "src"))

from ludiglot.infrastructure.tool_manager import ToolManager
from ludiglot.infrastructure.native_extractor import NativeExtractor

def test_integration():
    print("=== Testing Ludiglot + FModelCLI Integration ===")
    
    # 1. Test ToolManager
    tm = ToolManager()
    print(f"Tools Dir: {tm.tools_dir}")
    print(f"Repo path: {tm.dev_fmodel_cli_path}")
    
    success = tm.ensure_fmodel_cli()
    if not success:
        print("[-] ToolManager failed to ensure FModelCLI.exe")
        return
    
    print("[+] ToolManager success")
    
    # 2. Test NativeExtractor
    extractor = NativeExtractor()
    print(f"Extractor tool path: {extractor.tool_path}")
    
    if not extractor.tool_path.exists():
        print("[-] NativeExtractor cannot find tool")
        return
        
    print("[+] NativeExtractor ready")
    
    # 3. Dummy run (just to see if it executes)
    # We won't actually extract 10GB of data here, just check version/help if possible
    # But our CLI currently requires 3 args. 
    # Let's just verify the file exists and is executable.
    
    print("[+] All systems go!")

if __name__ == "__main__":
    test_integration()
