from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ludiglot.core.text_builder import find_multitext_paths


@dataclass
class WutheringDataPaths:
    en_text: Path
    zh_text: Path


class WutheringDataMapper:
    """解析 WutheringData 的结构与字段。"""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root

    def parse(self) -> WutheringDataPaths:
        en_json, zh_json = find_multitext_paths(self.data_root)
        return WutheringDataPaths(en_text=en_json, zh_text=zh_json)
