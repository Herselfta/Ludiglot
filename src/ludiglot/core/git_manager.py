from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RepoSpec:
    url: str
    branch: str = "main"
    path: Optional[Path] = None


class GitManager:
    """占位：自动同步上游数据仓库。

    未来实现：clone/pull、分支切换、校验等。
    """

    def __init__(self, repo: RepoSpec) -> None:
        self.repo = repo

    def sync(self) -> None:
        raise NotImplementedError("GitManager.sync 尚未实现")
