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
            # 步骤1: 检查或克隆WutheringData
            if not self.data_root.exists():
                self.progress.emit(f"克隆 WutheringData 到 {self.data_root}...")
                # 配置Git使用系统代理
                env = os.environ.copy()
                result = subprocess.run(
                    ["git", "clone", "https://github.com/Dimbreath/WutheringData.git", str(self.data_root)],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=env  # 使用系统环境变量（包含代理设置）
                )
                if result.returncode != 0:
                    self.finished.emit(False, f"克隆失败: {result.stderr}")
                    return
            else:
                # 步骤2: 更新现有仓库
                self.progress.emit(f"更新 {self.data_root}...")
                env = os.environ.copy()
                result = subprocess.run(
                    ["git", "-C", str(self.data_root), "pull"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    env=env  # 使用系统环境变量（包含代理设置）
                )
                if result.returncode != 0:
                    self.finished.emit(False, f"更新失败: {result.stderr}")
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
