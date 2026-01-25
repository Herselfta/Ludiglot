"""数据库更新模块：从WutheringData更新game_text_db.json"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class DatabaseUpdateThread(QThread):
    """后台线程：拉取WutheringData并重建数据库"""
    
    progress = pyqtSignal(str)  # 进度消息
    finished = pyqtSignal(bool, str)  # (成功?, 消息)
    
    def __init__(self, data_root: Path, output_path: Path, parent=None):
        super().__init__(parent)
        self.data_root = data_root
        self.output_path = output_path
    
    def run(self):
        try:
            from ludiglot.core.git_manager import GitManager
            
            # 步骤1 & 2: 检查、克隆或更新 WutheringData
            if not self.data_root.exists():
                self.progress.emit(f"克隆 WutheringData (精简版)...")
                success = GitManager.fast_clone_wuthering_data(
                    self.data_root, 
                    progress_callback=self.progress.emit
                )
                if not success:
                    self.finished.emit(False, "克隆失败，请检查网络或代理设置")
                    return
            else:
                self.progress.emit(f"正在检查更新...")
                result = GitManager.pull(self.data_root)
                if result.returncode != 0:
                    # 如果 pull 失败（可能是因为远程分支变动），尝试提示用户
                    self.finished.emit(False, f"更新失败: {result.stderr or '未知 Git 错误'}")
                    return
            
            # 步骤3: 重建数据库
            self.progress.emit("重建数据库...")
            from ludiglot.core.text_builder import build_text_db_from_root_all, save_text_db
            
            try:
                db = build_text_db_from_root_all(self.data_root)
                save_text_db(db, self.output_path)
                self.progress.emit(f"数据库已保存到 {self.output_path}")
                self.finished.emit(True, f"成功！数据库包含 {len(db)} 个条目")
            except Exception as e:
                self.finished.emit(False, f"构建数据库失败: {e}")
                return
                
        except Exception as e:
            self.finished.emit(False, f"更新失败: {e}")
