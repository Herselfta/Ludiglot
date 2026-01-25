from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable


def _iter_items(payload: Any) -> Iterable[dict]:
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


def _latest_mtime(paths: Iterable[Path]) -> float:
    latest = 0.0
    for path in paths:
        try:
            latest = max(latest, path.stat().st_mtime)
        except Exception:
            continue
    return latest


def _normalize_voice_event(voice: str) -> str:
    raw = voice.strip()
    if not raw:
        return ""
    # 移除末尾的点号
    if raw.endswith("."):
        raw = raw[:-1]
    # 如果有路径，取最后一部分
    if "/" in raw:
        raw = raw.split("/")[-1]
    # 如果有点号分段（如命名空间），取最后一部分
    if "." in raw:
        raw = raw.split(".")[-1]
    return raw.strip()


def build_voice_map_from_configdb(data_root: Path, cache_path: Path | None = None) -> Dict[str, list[str]]:
    configdb = data_root / "ConfigDB"
    if not configdb.exists():
        return {}

    json_paths = list(configdb.rglob("*.json"))
    latest = _latest_mtime(json_paths)

    # 提升至 v4 以应用全字段扫描逻辑
    cache_version = 4
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                isinstance(cached, dict)
                and cached.get("configdb_mtime") == latest
                and cached.get("voice_map_version") == cache_version
            ):
                data = cached.get("voice_map")
                if isinstance(data, dict):
                    return {k: list(v) for k, v in data.items() if isinstance(v, list)}
        except Exception:
            pass

    voice_map: Dict[str, list[str]] = {}
    
    # 增加扫描深度，识别更多潜在的音频关联字段
    TEXT_KEYS = {"Content", "Title", "TextKey", "Text", "Id", "Tid", "TidText"}
    AUDIO_KEYS = {"Voice", "FileName", "Audio", "Event", "VoiceEvent", "Audio1", "Audio2", "Audio3"}

    for path in json_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        
        for item in _iter_items(payload):
            # 1. 寻找所有可能的音频事件名
            found_events = []
            for ak in AUDIO_KEYS:
                val = item.get(ak)
                if isinstance(val, str) and val.strip():
                    ev = _normalize_voice_event(val)
                    if ev: found_events.append(ev)
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str):
                            ev = _normalize_voice_event(v)
                            if ev: found_events.append(ev)
                        elif isinstance(v, dict): # 处理像 LostHealthEventMap 这种结构
                            for v_val in v.values():
                                if isinstance(v_val, str):
                                    ev = _normalize_voice_event(v_val)
                                    if ev: found_events.append(ev)

            if not found_events and path.name == "PlotAudio.json":
                # PlotAudio 特写：如果 FileName 为空，尝试用 Id
                fid = item.get("Id")
                if isinstance(fid, str):
                    found_events.append(_normalize_voice_event(fid))

            if not found_events:
                continue
                
            # 2. 寻找所有可能的文本 Key
            found_text_keys = []
            for tk in TEXT_KEYS:
                val = item.get(tk)
                if isinstance(val, str) and val.strip():
                    found_text_keys.append(val.strip())
                elif isinstance(val, (int, float)): # 有些 ID 是数字
                    found_text_keys.append(str(val))

            # 3. 交叉关联
            for t_key in found_text_keys:
                # 过滤掉一些明显不是 TextKey 的过短数字
                if t_key.isdigit() and len(t_key) < 5 and path.name != "SubtitleText.json":
                    continue
                
                for ev in found_events:
                    if ev not in voice_map.get(t_key, []):
                        voice_map.setdefault(t_key, []).append(ev)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "configdb_mtime": latest,
                    "voice_map_version": cache_version,
                    "voice_map": voice_map,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return voice_map
