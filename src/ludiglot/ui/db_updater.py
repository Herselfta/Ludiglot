"""数据库更新模块：从WutheringData更新game_text_db.json"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


class DatabaseUpdateThread(QThread):
    """后台线程：更新数据源并重建数据库"""
    
    progress = pyqtSignal(str)  # 进度消息
    finished = pyqtSignal(bool, str)  # (成功?, 消息)
    
    def __init__(self, config_path: Path, output_path: Path, parent=None):
        super().__init__(parent)
        self.config_path = config_path
        self.output_path = output_path
    
    def run(self):
        try:
            from ludiglot.core.config import load_config
            from ludiglot.core.game_pak_update import update_from_game_paks
            from ludiglot.core.git_manager import GitManager
            from ludiglot.core.text_builder import build_text_db_from_root_all, save_text_db

            cfg = load_config(self.config_path)

            if cfg.use_game_paks or cfg.game_install_root or cfg.game_pak_root:
                self.progress.emit("从游戏 Pak 解包并构建数据库...")
                update_from_game_paks(cfg, self.config_path, self.output_path, progress=self.progress.emit)
                self.finished.emit(True, "成功！已从游戏 Pak 更新数据库")
                return

            # 兼容旧流程：WutheringData
            if not cfg.data_root:
                self.finished.emit(False, "缺少 data_root 配置，无法更新数据库")
                return

            if not cfg.data_root.exists():
                self.progress.emit("克隆 WutheringData (精简版)...")
                success = GitManager.fast_clone_wuthering_data(
                    cfg.data_root,
                    progress_callback=self.progress.emit,
                )
                if not success:
                    self.finished.emit(False, "克隆失败，请检查网络或代理设置")
                    return
            else:
                self.progress.emit("正在检查更新...")
                result = GitManager.pull(cfg.data_root)
                if result.returncode != 0:
                    self.finished.emit(False, f"更新失败: {result.stderr or '未知 Git 错误'}")
                    return

            self.progress.emit("重建数据库...")
            db = build_text_db_from_root_all(cfg.data_root)
            save_text_db(db, self.output_path)
            self.progress.emit(f"数据库已保存到 {self.output_path}")
            self.finished.emit(True, f"成功！数据库包含 {len(db)} 个条目")
            return
                
        except Exception as e:
            self.finished.emit(False, f"更新失败: {e}")
