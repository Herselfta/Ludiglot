from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from ludiglot.core.text_builder import find_multitext_paths


@dataclass
class AppConfig:
    data_root: Path | None
    en_json: Path
    zh_json: Path
    db_path: Path
    image_path: Path
    auto_rebuild_db: bool = True
    min_db_entries: int = 1000
    ocr_lang: str = "en"
    ocr_mode: str = "auto"  # auto | gpu | cpu
    ocr_gpu: bool = False  # legacy field
    ocr_backend: str = "auto"  # auto | paddle | tesseract
    audio_cache_path: Path | None = None
    audio_cache_index_path: Path | None = None
    audio_wem_root: Path | None = None
    audio_bnk_root: Path | None = None
    audio_txtp_cache: Path | None = None
    vgmstream_path: Path | None = None
    wwiser_path: Path | None = None
    audio_cache_max_mb: int = 2048
    scan_audio_on_start: bool = True
    play_audio: bool = False
    capture_mode: str = "image"  # image | region | window | select
    window_title: str | None = None
    capture_region: dict | None = None
    hotkey_capture: str = "ctrl+shift+o"
    hotkey_toggle: str | None = None
    window_pos: tuple[int, int] | None = None
    font_en: str = "Source Han Serif SC, 思源宋体, serif"
    font_cn: str = "Source Han Serif SC, 思源宋体, serif"


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    raw: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    
    project_root = Path(__file__).resolve().parents[3]
    
    def resolve_path(p: str | None) -> Path | None:
        if not p: return None
        pp = Path(p)
        if pp.is_absolute(): return pp
        # 相对路径解析：相对于项目根目录
        return (project_root / pp).resolve()

    data_root = resolve_path(raw.get("data_root"))
    db_path = resolve_path(raw.get("db_path"))
    
    # 智能探测数据库文件（如果配置的路径不存在）
    if db_path and not db_path.exists():
        shared_db_candidates = [
            project_root / "game_text_db.json",
            project_root / "data" / "game_text_db.json",
            project_root / "cache" / "game_text_db.json"
        ]
        for candidate in shared_db_candidates:
            if candidate.exists():
                db_path = candidate
                break

    auto_rebuild = raw.get("auto_rebuild_db", True)
    has_db = db_path and db_path.exists()
    
    # 修改逻辑：只有在真正需要 data_root 的时候才报错
    if data_root and not data_root.exists():
        # 需要 data_root 的两种情况：1. 明确要求重建 2. 没有 DB 需要生成
        if auto_rebuild or not has_db:
             # 如果用户已经设置了 false 但还是进来了，说明是 has_db 为 false
             if not auto_rebuild and not has_db:
                 raise FileNotFoundError(
                     f"数据库文件未找到: {raw.get('db_path')}\n"
                     f"且由于 data_root 不存在 ({data_root})，无法自动生成数据库。\n\n"
                     "解决方法：\n"
                     "1. 检查 settings.json 中的 'db_path' 是否正确\n"
                     "2. 或者克隆 WutheringData 并设置正确的 'data_root'"
                 )
             else:
                 raise FileNotFoundError(
                     f"配置的数据根目录不存在: {data_root}\n"
                     "如果您需要自动构建数据库或使用音频功能，请在 config/settings.json 中修改 'data_root' 指向您的 WutheringData 目录。\n"
                     "如果您已有数据库文件，请确保 'db_path' 正确且设置 'auto_rebuild_db': false。"
                 )

    en_json = raw.get("en_json")
    zh_json = raw.get("zh_json")
    
    # 只有在需要重建或者没有 DB 的时候，才强制要求 MultiText 路径
    if (not has_db or auto_rebuild) and (not en_json or not zh_json) and data_root:
        try:
            resolved_en, resolved_zh = find_multitext_paths(data_root)
            en_json = en_json or str(resolved_en)
            zh_json = zh_json or str(resolved_zh)
        except FileNotFoundError:
            if not has_db: raise
    
    # 解析路径
    en_json_path = resolve_path(en_json)
    zh_json_path = resolve_path(zh_json)
    
    # 最终验证：要么有数据库，要么有源数据
    if not has_db and (not en_json_path or not zh_json_path):
         raise ValueError("配置中缺少数据库文件 (db_path) 且无法通过 data_root 构建。请至少提供其中之一。")

    ocr_mode = raw.get("ocr_mode")
    if not ocr_mode:
        ocr_mode = "gpu" if raw.get("ocr_gpu") else "auto"
        
    audio_cache_path = resolve_path(raw.get("audio_cache_path")) or project_root / "cache" / "audio"
    audio_cache_index_path = resolve_path(raw.get("audio_cache_index_path"))
    audio_wem_root = resolve_path(raw.get("audio_wem_root"))
    audio_bnk_root = resolve_path(raw.get("audio_bnk_root"))
    audio_txtp_cache = resolve_path(raw.get("audio_txtp_cache"))
    
    vgmstream_path = resolve_path(raw.get("vgmstream_path"))
    wwiser_path = resolve_path(raw.get("wwiser_path"))
    
    if audio_cache_path and audio_cache_index_path is None:
        audio_cache_index_path = audio_cache_path / "audio_index.json"
    if audio_cache_path and audio_txtp_cache is None:
        audio_txtp_cache = audio_cache_path / "txtp"
        
    if audio_wem_root and audio_bnk_root is None:
        # 尝试从 Media/zh 向上两级找 Event/zh
        candidate = audio_wem_root.parents[1] / "Event" / "zh"
        if candidate.exists():
            audio_bnk_root = candidate
        else:
            # 兼容旧逻辑
            candidate = audio_wem_root / "Client" / "Content" / "Aki" / "WwiseAudio_Generated" / "Event" / "zh"
            if candidate.exists():
                audio_bnk_root = candidate
            
    if wwiser_path is None:
        candidate = project_root / "tools/wwiser.pyz"
        if candidate.exists():
            wwiser_path = candidate
            
    font_en = raw.get("font_en", "Source Han Serif SC, 思源宋体, serif")
    font_cn = raw.get("font_cn", "Source Han Serif SC, 思源宋体, serif")
    
    return AppConfig(
        data_root=data_root,
        en_json=en_json_path,
        zh_json=zh_json_path,
        db_path=resolve_path(raw.get("db_path", "game_text_db.json")) or project_root / "game_text_db.json",
        image_path=resolve_path(raw.get("image_path")) or project_root / "cache/capture.png",
        auto_rebuild_db=bool(raw.get("auto_rebuild_db", True)),
        min_db_entries=int(raw.get("min_db_entries", 1000)),
        ocr_lang=raw.get("ocr_lang", "en"),
        ocr_mode=str(ocr_mode).lower(),
        ocr_gpu=bool(raw.get("ocr_gpu", False)),
        ocr_backend=str(raw.get("ocr_backend", "auto")).lower(),
        audio_cache_path=audio_cache_path,
        audio_cache_index_path=audio_cache_index_path,
        audio_wem_root=audio_wem_root,
        audio_bnk_root=audio_bnk_root,
        audio_txtp_cache=audio_txtp_cache,
        vgmstream_path=vgmstream_path,
        wwiser_path=wwiser_path,
        audio_cache_max_mb=int(raw.get("audio_cache_max_mb", 2048)),
        scan_audio_on_start=bool(raw.get("scan_audio_on_start", True)),
        play_audio=bool(raw.get("play_audio", False)),
        capture_mode=raw.get("capture_mode", "image"),
        window_title=raw.get("window_title"),
        capture_region=raw.get("capture_region"),
        hotkey_capture=raw.get("hotkey_capture", "ctrl+shift+o"),
        hotkey_toggle=raw.get("hotkey_toggle"),
        window_pos=_load_window_pos(raw.get("window_pos")),
        font_en=font_en,
        font_cn=font_cn,
    )


def _load_window_pos(raw: Any) -> tuple[int, int] | None:
    if not isinstance(raw, dict):
        return None
    try:
        x = int(raw.get("x"))
        y = int(raw.get("y"))
        return (x, y)
    except Exception:
        return None
