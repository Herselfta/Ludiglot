from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Tuple, Any

from ludiglot.core.voice_map import build_voice_map_from_configdb
from ludiglot.core.wwise_hash import WwiseHash



def normalize_en(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


_TAG_RE = re.compile(r"</?[^>]+>")
_BRACE_RE = re.compile(r"\{[^}]+\}")


def clean_en_text(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = _BRACE_RE.sub("", text)
    return text


def _extract_map(obj: object) -> Dict[str, str]:
    """从多种可能的 JSON 结构抽取 {text_key: text} 映射。"""
    if isinstance(obj, dict):
        if all(isinstance(v, str) for v in obj.values()):
            return {str(k): v for k, v in obj.items()}
        extracted: Dict[str, str] = {}
        for k, v in obj.items():
            if isinstance(v, dict):
                text = (
                    v.get("Text")
                    or v.get("Content")
                    or v.get("Value")
                    or v.get("TextValue")
                )
                if isinstance(text, str):
                    extracted[str(k)] = text
        return extracted
    if isinstance(obj, list):
        extracted: Dict[str, str] = {}
        for item in obj:
            if not isinstance(item, dict):
                continue
            key = (
                item.get("Key")
                or item.get("TextKey")
                or item.get("TextMapId")
                or item.get("ID")
            )
            text = (
                item.get("Text")
                or item.get("Content")
                or item.get("Value")
                or item.get("TextValue")
            )
            if isinstance(key, str) and isinstance(text, str):
                extracted[key] = text
        return extracted
    return {}


def _load_map(path: Path) -> Dict[str, str]:
    if path.suffix.lower() == ".db":
        return _load_sqlite_map(path)
    obj = json.loads(path.read_text(encoding="utf-8"))
    return _extract_map(obj)


def _load_sqlite_map(path: Path) -> Dict[str, str]:
    """从 SQLite 数据库提取文本。常见表名为 'Table' 或 'data'，列名为 'TextMapId'/'Key' 和 'Text'/'Content'。"""
    try:
        # 预检：检查是否截断
        with open(path, "rb") as f:
            header = f.read(100)
            if len(header) < 100 or header[:15] != b"SQLite format 3":
                return {}
            # 第 28-31 字节是文件大小（以页为单位，大端序）
            page_count = int.from_bytes(header[28:32], "big")
            # 第 16-17 字节是页大小
            page_size = int.from_bytes(header[16:18], "big")
            if page_size == 1: page_size = 65536
            
            expected_size = page_count * page_size
            actual_size = path.stat().st_size
            if actual_size < expected_size:
                print(f"⚠️ 警告: 数据库 {path.name} 似乎已截断 (预期 {expected_size} 字节, 实际 {actual_size} 字节)。这通常是由于解包不完整导致的。")
                # 即使截断，sqlite3 有时也能读到前面的数据，继续尝试

        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

        cursor = conn.cursor()
        
        # 探测表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        if not tables:
            return {}
        
        # 优先使用 lang_text 或通用表名
        table_name = None
        for cand in ["Table", "data", "lang_text", "text"]:
            if cand in tables:
                table_name = cand
                break
        if not table_name: table_name = tables[0]

        # 探测列名
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = {r[1].lower(): r[1] for r in cursor.fetchall()}
        
        id_col = cols.get("textid") or cols.get("textmapid") or cols.get("key") or cols.get("id")
        text_col = cols.get("text") or cols.get("content") or cols.get("value")
        
        if not id_col or not text_col:
            # 这种情况下尝试猜测第一列和第二列
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
            row = cursor.fetchone()
            if row and len(row) >= 2:
                id_col = list(cols.values())[0]
                text_col = list(cols.values())[1]
            else:
                return {}

        cursor.execute(f"SELECT {id_col}, {text_col} FROM {table_name}")
        mapping = {str(r[0]): str(r[1]) for r in cursor.fetchall() if r[0] and r[1]}
        conn.close()
        return mapping
    except Exception as e:
        print(f"警告: 无法读取 SQLite 数据库 {path.name}: {e}")
        return {}



def _iter_items(payload: object) -> Iterable[dict]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        for key in ("Data", "data", "Items", "items", "List", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
                return


def load_plot_audio_map(data_root: Path) -> Dict[str, str]:
    json_path = data_root / "ConfigDB" / "PlotAudio.json"
    db_path = data_root / "ConfigDB" / "db_plot_audio.db"
    
    mapping: Dict[str, str] = {}
    
    # 1. 尝试 JSON
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            for item in _iter_items(payload):
                text_key = (
                    item.get("TextKey")
                    or item.get("TextMapId")
                    or item.get("TextId")
                    or item.get("Key")
                    or item.get("Content")
                )
                file_name = (
                    item.get("FileName")
                    or item.get("AudioEventName")
                    or item.get("AudioEvent")
                    or item.get("Voice")
                )
                if text_key and file_name:
                    mapping[str(text_key)] = str(file_name)
        except Exception:
            pass
            
    # 2. 尝试 SQLite
    if db_path.exists():
        try:
            import sqlite3
            import re
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cursor.fetchall()]
            
            # 匹配 vo_ 或 play_vo_ 开头的音频事件名（BLOB 扫描用）
            audio_pat = re.compile(rb'(?:play_vo_|vo_)[a-zA-Z0-9_]{3,}')
            
            for tbl in tables:
                cursor.execute(f"PRAGMA table_info({tbl})")
                cols_info = cursor.fetchall()
                cols = {r[1].lower(): r[1] for r in cols_info}
                
                # 寻找 ID 列
                tk_col = cols.get("id") or cols.get("textkey") or cols.get("key") or cols.get("textmapid") or cols.get("textid") or cols.get("content")
                
                # 寻找音频列
                fn_col = cols.get("filename") or cols.get("audioeventname") or cols.get("audioevent") or cols.get("voice")
                
                # 寻找 BLOB 列
                blob_col = next((c[1] for c in cols_info if "blob" in (c[2] or "").lower() or c[1].lower() == "bindata"), None)
                
                if tk_col:
                    if fn_col:
                        # 情况 A：存在平铺列
                        cursor.execute(f"SELECT {tk_col}, {fn_col} FROM {tbl}")
                        for r in cursor.fetchall():
                            if r[0] and r[1]:
                                mapping[str(r[0])] = str(r[1])
                                
                    if blob_col and (not fn_col or tbl.lower() == "plotaudio"):
                        # 情况 B：扫描 BLOB (针对 plotaudio 表或缺失平铺列的情况)
                        cursor.execute(f"SELECT {tk_col}, {blob_col} FROM {tbl}")
                        for tid, blob in cursor.fetchall():
                            if not tid or not isinstance(blob, (bytes, bytearray)):
                                continue
                            matches = audio_pat.findall(blob)
                            if matches:
                                event_name = matches[0].decode('ascii', errors='ignore').strip()
                                if event_name:
                                    mapping[str(tid)] = event_name
            conn.close()
        except Exception:
            pass
            
    return mapping

# The old logic is replaced by the updated load_plot_audio_map


def _parse_event_name(value: str) -> str:
    segment = value.rsplit("/", 1)[-1]
    if "." in segment:
        segment = segment.split(".")[-1]
    return segment


def _resolve_audio_hash(
    text_key: str,
    plot_audio: Dict[str, str] | None,
    voice_map: Dict[str, list[str]] | None,
) -> tuple[str | None, str | None]:
    event_name: str | None = None
    if plot_audio and text_key in plot_audio:
        event_name = plot_audio[text_key]
    elif voice_map and text_key in voice_map and voice_map[text_key]:
        event_name = voice_map[text_key][0]
    if event_name:
        event_name = _parse_event_name(event_name)
    else:
        event_name = f"vo_{text_key}"
    audio_hash = WwiseHash().hash_str(event_name)
    return audio_hash, event_name


def _candidate_paths(root: Path, rel_paths: Iterable[str]) -> list[Path]:
    return [root / rel for rel in rel_paths]


def find_multitext_paths(data_root: Path) -> Tuple[Path, Path]:
    candidates_en = _candidate_paths(
        data_root,
        [
            "ConfigDB/en/lang_text.db",
            "TextMap/en/MultiText.json",
            "TextMap/en/Multitext.json",
        ],
    )
    candidates_zh = _candidate_paths(
        data_root,
        [
            "ConfigDB/zh-Hans/lang_text.db",
            "TextMap/zh-Hans/MultiText.json",
            "TextMap/zh-CN/MultiText.json",
            "TextMap/zh-Hans/Multitext.json",
        ],
    )
    en_path = next((p for p in candidates_en if p.exists()), None)
    zh_path = next((p for p in candidates_zh if p.exists()), None)


    if en_path is None or zh_path is None:
        # 兜底：在 TextMap 下搜索 MultiText.json
        text_map_root = data_root / "TextMap"
        if text_map_root.exists():
            for path in text_map_root.rglob("MultiText*.json"):
                rel = path.as_posix().lower()
                if "textmap/en" in rel and en_path is None:
                    en_path = path
                if "textmap/zh" in rel and zh_path is None:
                    zh_path = path
                if en_path and zh_path:
                    break

    if en_path is None or zh_path is None:
        raise FileNotFoundError(
            f"无法在所选目录中找到游戏文本数据 ({data_root})\n\n"
            "诊断细节:\n"
            f"- 英文路径匹配: {candidates_en[0] if candidates_en else 'N/A'}\n"
            f"- 中文路径匹配: {candidates_zh[0] if candidates_zh else 'N/A'}\n\n"
            "建议解决方法:\n"
            "1. 运行 'ludiglot pak-update' 从游戏 Pak 解包并构建数据库\n"
            "2. 确保 config/settings.json 中配置了正确的 game_pak_root 或 game_install_root\n"
            "3. 详情请参阅 docs/usage/data-management.md"
        )
    return en_path, zh_path


def build_text_db_from_root(data_root: Path) -> Dict[str, dict]:
    en_json, zh_json = find_multitext_paths(data_root)
    plot_audio = load_plot_audio_map(data_root)
    voice_map = build_voice_map_from_configdb(data_root)
    return build_text_db(en_json, zh_json, plot_audio=plot_audio, voice_map=voice_map)


def build_text_db_from_root_all(data_root: Path) -> Dict[str, dict]:
    # 语言对定义
    langs = [("en", "zh-Hans"), ("en", "zh-CN")]
    
    # 探测可能的数据目录
    roots = [
        data_root / "ConfigDB",
        data_root / "Client" / "Content" / "Aki" / "ConfigDB",
        data_root / "TextMap",
        data_root / "Client" / "Content" / "Aki" / "TextMap",
    ]

    plot_audio = load_plot_audio_map(data_root)
    # 启用缓存，确保 voice_map 可读
    cache_path = data_root.parent / "cache" / "voice_map_v6.json"
    voice_map = build_voice_map_from_configdb(data_root, cache_path=cache_path)
    db: Dict[str, dict] = {}

    def scan_pair(en_dir: Path, zh_dir: Path):
        if not en_dir.exists() or not zh_dir.exists():
            return
        for ext in ("*.json", "*.db"):
            for en_path in en_dir.rglob(ext):
                rel = en_path.relative_to(en_dir)
                zh_path = zh_dir / rel
                if not zh_path.exists():
                    continue
                try:
                    partial = build_text_db(en_path, zh_path, plot_audio=plot_audio, voice_map=voice_map)
                    for key, payload in partial.items():
                        if key not in db:
                            db[key] = payload
                        else:
                            db[key]["matches"].extend(payload.get("matches", []))
                except Exception:
                    continue

    for r in roots:
        if not r.exists(): continue
        for en, zh in langs:
            scan_pair(r / en, r / zh)

    # 兜底：如果完全没有扫到，或者扫出的是空的，尝试使用 MultiText 逻辑兜底
    if not db:
        try:
            return build_text_db_from_root(data_root)
        except Exception:
            pass
            
    return db



def build_text_db_from_maps(
    en_map: Dict[str, str],
    zh_map: Dict[str, str],
    source_json: str,
    plot_audio: Dict[str, str] | None = None,
    voice_map: Dict[str, list[str]] | None = None,
) -> Dict[str, dict]:
    db: Dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()

    def add_match(norm_key: str, text_key: str, match: dict) -> None:
        if not norm_key:
            return
        sig = (norm_key, text_key)
        if sig in seen:
            return
        seen.add(sig)
        if norm_key not in db:
            db[norm_key] = {"key": norm_key, "matches": [match]}
        else:
            db[norm_key]["matches"].append(match)

    all_keys = set(en_map.keys()) | set(zh_map.keys())
    for text_key in all_keys:
        en_text = en_map.get(text_key, "")
        zh_text = zh_map.get(text_key, "")
        if not (isinstance(en_text, str) or isinstance(zh_text, str)):
            continue

        if not isinstance(en_text, str):
            en_text = ""
        if not isinstance(zh_text, str):
            zh_text = ""

        cleaned_en = clean_en_text(en_text) if en_text else ""
        cleaned_zh = clean_en_text(zh_text) if zh_text else ""

        key_en = normalize_en(cleaned_en) if cleaned_en else ""
        key_zh = normalize_en(cleaned_zh) if cleaned_zh else ""

        if not key_en and not key_zh:
            continue

        audio_hash, audio_event = _resolve_audio_hash(text_key, plot_audio, voice_map)
        match = {
            "text_key": text_key,
            "official_en": en_text,  # 存储原始英文（包含HTML标记）
            "official_cn": zh_text,
            "source_json": source_json,
            "audio_rule": "vo_{text_key}",
            "audio_hash": audio_hash,
            "audio_event": audio_event,
            "terms": [],
        }

        add_match(key_en, text_key, match)
        add_match(key_zh, text_key, match)
    return db


def build_text_db(
    en_json: Path,
    zh_json: Path,
    plot_audio: Dict[str, str] | None = None,
    voice_map: Dict[str, list[str]] | None = None,
) -> Dict[str, dict]:
    """从 MultiText 构建数据库（兼容多种 JSON 结构）。"""
    en_map = _load_map(en_json)
    zh_map = _load_map(zh_json)
    return build_text_db_from_maps(en_map, zh_map, en_json.name, plot_audio, voice_map)


def save_text_db(db: Dict[str, dict], output: Path) -> None:
    output.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
