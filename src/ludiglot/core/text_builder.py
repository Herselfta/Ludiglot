from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, Tuple

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
    obj = json.loads(path.read_text(encoding="utf-8"))
    return _extract_map(obj)


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
    path = data_root / "ConfigDB" / "PlotAudio.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    mapping: Dict[str, str] = {}
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
        if not text_key or not file_name:
            continue
        mapping[str(text_key)] = str(file_name)
    return mapping


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
            "TextMap/en/MultiText.json",
            "TextMap/en/Multitext.json",
        ],
    )
    candidates_zh = _candidate_paths(
        data_root,
        [
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
            "1. 请确保您已克隆 WutheringData (https://github.com/Dimbreath/WutheringData)\n"
            "2. 检查 config/settings.json 中的 'data_root' 是否指向正确的路径\n"
            "3. 如果您是手动下载的，请确保保留了 TextMap/en/MultiText.json 这种目录结构\n"
            "详情请参阅 docs/DataManagement.md"
        )
    return en_path, zh_path


def build_text_db_from_root(data_root: Path) -> Dict[str, dict]:
    en_json, zh_json = find_multitext_paths(data_root)
    plot_audio = load_plot_audio_map(data_root)
    voice_map = build_voice_map_from_configdb(data_root)
    return build_text_db(en_json, zh_json, plot_audio=plot_audio, voice_map=voice_map)


def build_text_db_from_root_all(data_root: Path) -> Dict[str, dict]:
    text_map_root = data_root / "TextMap"
    en_root = text_map_root / "en"
    zh_root = text_map_root / "zh-Hans"
    if not en_root.exists() or not zh_root.exists():
        # 兜底使用 MultiText
        return build_text_db_from_root(data_root)

    plot_audio = load_plot_audio_map(data_root)
    voice_map = build_voice_map_from_configdb(data_root)
    db: Dict[str, dict] = {}
    for en_path in en_root.rglob("*.json"):
        rel = en_path.relative_to(en_root)
        zh_path = zh_root / rel
        if not zh_path.exists():
            continue
        try:
            partial = build_text_db(
                en_path,
                zh_path,
                plot_audio=plot_audio,
                voice_map=voice_map,
            )
        except Exception:
            continue
        for key, payload in partial.items():
            if key not in db:
                db[key] = payload
            else:
                db[key]["matches"].extend(payload.get("matches", []))
    return db


def build_text_db_from_maps(
    en_map: Dict[str, str],
    zh_map: Dict[str, str],
    source_json: str,
    plot_audio: Dict[str, str] | None = None,
    voice_map: Dict[str, list[str]] | None = None,
) -> Dict[str, dict]:
    db: Dict[str, dict] = {}
    for text_key, en_text in en_map.items():
        if not isinstance(en_text, str):
            continue
        cleaned = clean_en_text(en_text)
        key = normalize_en(cleaned)
        if not key:
            continue
        audio_hash, audio_event = _resolve_audio_hash(text_key, plot_audio, voice_map)
        match = {
            "text_key": text_key,
            "official_en": en_text,  # 存储原始英文（包含HTML标记）
            "official_cn": zh_map.get(text_key, ""),
            "source_json": source_json,
            "audio_rule": "vo_{text_key}",
            "audio_hash": audio_hash,
            "audio_event": audio_event,
            "terms": [],
        }
        if key not in db:
            db[key] = {"key": key, "matches": [match]}
        else:
            db[key]["matches"].append(match)
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
