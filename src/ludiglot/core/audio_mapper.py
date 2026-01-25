from __future__ import annotations

from dataclasses import dataclass
import json
import time
from pathlib import Path
from typing import Dict, Iterable


@dataclass
class AudioRule:
    prefix: str = "vo_"

    def resolve_name(self, text_key: str) -> str:
        return f"{self.prefix}{text_key}"


@dataclass
class AudioEntry:
    hash_value: int
    path: Path
    size: int
    mtime: float


class AudioCacheIndex:
    def __init__(
        self,
        cache_dir: Path,
        index_path: Path | None = None,
        max_mb: int = 2048,
        extensions: Iterable[str] | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.index_path = index_path or cache_dir / "audio_index.json"
        self.max_bytes = int(max_mb) * 1024 * 1024
        self.extensions = set(extensions or [".ogg", ".wem", ".wav", ".mp3", ".flac"])
        self.entries: Dict[int, AudioEntry] = {}

    def load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return
        entries: Dict[int, AudioEntry] = {}
        for item in raw.get("entries", []):
            try:
                hash_value = int(item["hash"])
                path = Path(item["path"])
                if not path.exists():
                    continue
                entries[hash_value] = AudioEntry(
                    hash_value=hash_value,
                    path=path,
                    size=int(item.get("size", path.stat().st_size)),
                    mtime=float(item.get("mtime", path.stat().st_mtime)),
                )
            except Exception:
                continue
        self.entries = entries

    def save(self) -> None:
        payload = {
            "generated_at": time.time(),
            "entries": [
                {
                    "hash": entry.hash_value,
                    "path": str(entry.path),
                    "size": entry.size,
                    "mtime": entry.mtime,
                }
                for entry in self.entries.values()
            ],
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def scan(self) -> None:
        if not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        entries: Dict[int, AudioEntry] = {}
        for path in self.cache_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.extensions:
                continue
            try:
                hash_value = int(path.stem)
            except Exception:
                continue
            stat = path.stat()
            entries[hash_value] = AudioEntry(
                hash_value=hash_value,
                path=path,
                size=stat.st_size,
                mtime=stat.st_mtime,
            )
        self.entries = entries
        self._enforce_size_limit()
        self.save()

    def validate(self) -> None:
        to_remove = [key for key, entry in self.entries.items() if not entry.path.exists()]
        for key in to_remove:
            self.entries.pop(key, None)

    def _total_size(self) -> int:
        return sum(entry.size for entry in self.entries.values())

    def _enforce_size_limit(self) -> None:
        if self.max_bytes <= 0:
            return
        total = self._total_size()
        if total <= self.max_bytes:
            return
        # 删除最旧的文件直到满足限制
        ordered = sorted(self.entries.values(), key=lambda e: e.mtime)
        for entry in ordered:
            try:
                entry.path.unlink(missing_ok=True)
            except Exception:
                pass
            total -= entry.size
            self.entries.pop(entry.hash_value, None)
            if total <= self.max_bytes:
                break

    def find(self, hash_value: int) -> Path | None:
        entry = self.entries.get(int(hash_value))
        if entry and entry.path.exists():
            return entry.path
        return None

    def add_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        if path.suffix.lower() not in self.extensions:
            return
        try:
            hash_value = int(path.stem)
        except Exception:
            return
        stat = path.stat()
        self.entries[hash_value] = AudioEntry(
            hash_value=hash_value,
            path=path,
            size=stat.st_size,
            mtime=stat.st_mtime,
        )
        self.save()
