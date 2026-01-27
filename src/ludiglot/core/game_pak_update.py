from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.request import urlopen

from ludiglot.core.aes_archive import parse_aes_archive, select_keys, list_versions


AES_ARCHIVE_URL = "https://raw.githubusercontent.com/ClostroOffi/wuwa-aes-archive/main/readme.md"
_PAKCHUNK_RE = re.compile(r"pakchunk[-_]?([0-9]+)", re.IGNORECASE)


@dataclass
class GamePakOptions:
    version: str
    platform: str
    server: str
    languages: list[str]
    audio_languages: list[str]
    extract_audio: bool


class GamePakUpdateError(RuntimeError):
    pass


def _log(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


def _is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _prompt_choice(title: str, options: list[str], default_index: int = 0) -> str:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    for i, opt in enumerate(options, start=1):
        marker = "(默认)" if i - 1 == default_index else ""
        print(f"  [{i}] {opt} {marker}")
    while True:
        raw = input(f"请选择 [1-{len(options)}] (Enter=默认): ").strip()
        if not raw:
            return options[default_index]
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        print("❌ 无效输入，请重试。")


def _prompt_multi_select(title: str, options: list[str], default: list[str]) -> list[str]:
    default_set = {opt.lower() for opt in default}
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    for i, opt in enumerate(options, start=1):
        marker = "(默认)" if opt.lower() in default_set else ""
        print(f"  [{i}] {opt} {marker}")
    print("支持多选：用逗号分隔编号，例如 1,3,4。回车=默认。")
    while True:
        raw = input("请选择: ").strip()
        if not raw:
            return [opt for opt in options if opt.lower() in default_set]
        indices = [part.strip() for part in raw.split(",") if part.strip()]
        selected: list[str] = []
        ok = True
        for part in indices:
            if not part.isdigit():
                ok = False
                break
            idx = int(part) - 1
            if idx < 0 or idx >= len(options):
                ok = False
                break
            selected.append(options[idx])
        if ok and selected:
            return selected
        print("❌ 无效输入，请重试。")


def _fetch_aes_archive(url: str) -> str:
    """获取 AES 归档文本，优先使用网络，网络失败时自动回退到本地缓存。"""
    cache_file = Path(__file__).resolve().parents[3] / "cache" / "aes_archive.md"
    
    from urllib.request import Request
    
    # 尝试从网络获取
    req = Request(url, headers={"User-Agent": "Ludiglot-Updater/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            # 成功后缓存到本地
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(content, encoding="utf-8")
            print("[PAK] AES 表已从网络更新")
            return content
    except Exception as e:
        # 网络失败，尝试使用缓存
        if cache_file.exists():
            print(f"[PAK] 网络请求失败 (可能受限)，正在使用本地缓存: {cache_file.name}")
            return cache_file.read_text(encoding="utf-8")
        raise GamePakUpdateError(
            f"无法获取 AES 表：网络请求失败 ({type(e).__name__}) 且无本地缓存。\n"
            f"请检查网络连接或手动下载 {url} 并保存到 {cache_file}"
        )



def _list_pak_files(pak_dir: Path) -> list[Path]:
    return sorted(pak_dir.rglob("*.pak"))


def _pak_name_to_pattern(pak_name: str) -> str:
    if pak_name.lower() == "main":
        return "pakchunk0"
    match = _PAKCHUNK_RE.search(pak_name)
    if match:
        return f"pakchunk{match.group(1)}"
    return pak_name.replace("-", "").replace("_", "")


def _match_paks(pak_dir: Path, pak_name: str) -> list[Path]:
    pattern = _pak_name_to_pattern(pak_name)
    matches = []
    for path in _list_pak_files(pak_dir):
        if pattern.lower() in path.name.lower():
            matches.append(path)
    return matches


def _choose_options(entries, cfg) -> GamePakOptions:
    version_labels = list_versions(entries)
    latest_version = version_labels[-1] if version_labels else ""

    # 自动选择逻辑：优先使用配置中指定的版本，否则直接使用 AES 表中的最新版
    version_choice = cfg.game_version or latest_version

    if not _is_tty():
        if not (version_choice and cfg.game_platform and cfg.game_server and cfg.game_languages):
            raise GamePakUpdateError("缺少 game_platform/game_server/game_languages 配置")
        return GamePakOptions(
            version=version_choice,
            platform=cfg.game_platform,
            server=cfg.game_server,
            languages=cfg.game_languages,
            audio_languages=cfg.game_audio_languages or cfg.game_languages,
            extract_audio=bool(cfg.extract_audio),
        )

    # 交互模式下，平台、区服、语言等仍保留交互或使用配置
    platform_choice = cfg.game_platform or _prompt_choice("请选择平台", ["Windows", "Android", "iOS"], 0)
    server_choice = cfg.game_server or _prompt_choice("请选择区服", ["OS", "CN"], 0)


    if cfg.game_languages:
        languages = cfg.game_languages
    else:
        languages = _prompt_multi_select("请选择文本语言", ["en", "ja", "ko", "zh-Hans", "zh-CN", "fr", "de", "es", "ru"], ["en", "zh-Hans"])

    audio_languages = cfg.game_audio_languages
    if not audio_languages:
        audio_languages = _prompt_multi_select(
            "请选择语音语言", ["zh", "en", "ja", "ko"], ["zh"]
        )

    extract_audio = cfg.extract_audio
    if extract_audio is None:
        choice = _prompt_choice("是否解包语音资源", ["是", "否"], 0)
        extract_audio = choice == "是"

    return GamePakOptions(
        version=version_choice,
        platform=platform_choice,
        server=server_choice,
        languages=languages,
        audio_languages=audio_languages,
        extract_audio=bool(extract_audio),
    )




def update_from_game_paks(cfg, config_path: Path, output_db_path: Path, progress: Callable[[str], None] | None = None) -> None:
    _log(progress, "[PAK] 正在加载 AES 表...")
    url = cfg.aes_archive_url or AES_ARCHIVE_URL
    archive_text = _fetch_aes_archive(url)
    entries = parse_aes_archive(archive_text)
    if not entries:
        raise GamePakUpdateError("无法解析 AES 表，请检查网络或格式")

    options = _choose_options(entries, cfg)

    selection = select_keys(entries, options.version, options.platform, options.server)
    if not selection.keys:
        raise GamePakUpdateError("未找到匹配的 AES Key，请检查版本/平台/区服")

    _log(progress, f"[PAK] 版本: {selection.version_label} | 平台: {options.platform} | 区服: {options.server}")
    for key in selection.keys:
        _log(progress, f"[PAK] AES: {key.pak_name} -> {key.aes_key[:10]}...")

    pak_root = cfg.game_pak_root
    if pak_root is None and cfg.game_install_root:
        pak_root = cfg.game_install_root / "Client" / "Content" / "Paks"
    if pak_root is None or not pak_root.exists():
        if _is_tty():
            raw = input("请输入游戏 Paks 目录 (例如 .../Client/Content/Paks): ").strip().strip('"')
            if raw:
                pak_root = Path(raw)
        if pak_root is None or not pak_root.exists():
            raise GamePakUpdateError("找不到游戏 Paks 目录，请设置 game_pak_root")

    # FModelCLI is now the only supported extraction method
    _log(progress, f"[PAK] Paks 目录: {pak_root}")

    data_root = cfg.game_data_root or cfg.data_root
    if data_root is None:
        raise GamePakUpdateError("缺少 game_data_root/data_root 配置")
    data_root = data_root.resolve()
    data_root.mkdir(parents=True, exist_ok=True)

    # 语言探测 (目前 FModelCLI 不支持列表语言，跳过自动探测)
    detected_langs: set[str] = set()
    aes_keys = [entry.aes_key for entry in selection.keys]
    
    if detected_langs:
        detected_list = sorted(detected_langs)
        if _is_tty() and not cfg.game_languages:
            options.languages = _prompt_multi_select("检测到可用语言", detected_list, options.languages)

    # 使用 FModelCLI 提取资源
    from ludiglot.infrastructure.native_extractor import NativeExtractor
    from ludiglot.infrastructure.tool_manager import ToolManager
    
    # Ensure tool exists
    tm = ToolManager()
    tm.ensure_fmodel_cli()

    native_extractor = NativeExtractor()
    
    if not native_extractor.tool_path.exists():
        raise GamePakUpdateError(f"FModelCLI not found at {native_extractor.tool_path}. Please run ToolManager setup.")
    
    _log(progress, f"[PAK] 使用 FModelCLI: {native_extractor.tool_path}")
    _log(progress, f"[PAK] 提取语言: {options.languages}, 音频语言: {options.audio_languages}")

    keys_str = ";".join(aes_keys)

    # ConfigDB Extraction (per language)
    for lang in options.languages:
        _log(progress, f"[PAK] 正在提取 ConfigDB/{lang} ...")
        filter_str = f"ConfigDB/{lang}"
        success = native_extractor.run_extraction(pak_root, keys_str, data_root, filter_str)
        if not success:
            _log(progress, f"[PAK] ⚠️  ConfigDB/{lang} 提取报告失败")
    
    # TextMap Extraction (per language)
    for lang in options.languages:
        _log(progress, f"[PAK] 正在提取 TextMap/{lang} ...")
        filter_str = f"TextMap/{lang}"
        native_extractor.run_extraction(pak_root, keys_str, data_root, filter_str)

    # Audio Extraction (if requested, per audio language)
    if options.extract_audio:
        audio_root = cfg.game_audio_root or (data_root / "Audio")
        audio_root.mkdir(parents=True, exist_ok=True)
        for audio_lang in options.audio_languages:
            _log(progress, f"[PAK] 正在提取 WwiseAudio/{audio_lang} ...")
            # Wwise audio uses short lang codes like "zh", "en", "ja"
            filter_str = f"WwiseAudio_Generated/Media/{audio_lang}"
            native_extractor.run_extraction(pak_root, keys_str, audio_root, filter_str)
            # Also extract Event banks
            filter_str = f"WwiseAudio_Generated/Event/{audio_lang}"
            native_extractor.run_extraction(pak_root, keys_str, audio_root, filter_str)
        _log(progress, f"[PAK] 语音资源输出: {audio_root}")

    # 整理目录结构：将解包出来的深层目录移动到 data_root 根目录下
    staged_configdb = data_root / "Client" / "Content" / "Aki" / "ConfigDB"
    staged_textmap = data_root / "Client" / "Content" / "Aki" / "TextMap"
    
    if staged_configdb.exists():
        target = data_root / "ConfigDB"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(staged_configdb), str(target))
        _log(progress, f"[PAK] 已同步 ConfigDB 到 {target}")

    if staged_textmap.exists():
        target = data_root / "TextMap"
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(staged_textmap), str(target))
        _log(progress, f"[PAK] 已同步 TextMap 到 {target}")

    # 清理多余的嵌套目录
    shutil.rmtree(data_root / "Client", ignore_errors=True)


    # 更新配置文件
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        raw["data_root"] = _to_rel_path(config_path, data_root)
        # 不再保存 game_version，以便下次运行自动获取最新版
        if "game_version" in raw:
            del raw["game_version"]

        raw["game_platform"] = options.platform
        raw["game_server"] = options.server
        raw["game_languages"] = options.languages
        raw["game_audio_languages"] = options.audio_languages
        if options.extract_audio:
            audio_root = cfg.game_audio_root or (data_root / "Audio")
            media_lang = options.audio_languages[0] if options.audio_languages else "zh"
            raw["audio_wem_root"] = _to_rel_path(config_path, audio_root / "Client" / "Content" / "Aki" / "WwiseAudio_Generated" / "Media" / media_lang)
            raw["audio_bnk_root"] = _to_rel_path(config_path, audio_root / "Client" / "Content" / "Aki" / "WwiseAudio_Generated" / "Event" / media_lang)
        config_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 构建数据库
    from ludiglot.core.text_builder import build_text_db_from_root_all, save_text_db
    db = build_text_db_from_root_all(data_root)
    save_text_db(db, output_db_path)
    _log(progress, f"[PAK] 数据库已保存: {output_db_path} ({len(db)} 条)")


def _to_rel_path(config_path: Path, target: Path) -> str:
    project_root = config_path.resolve().parents[1]
    try:
        return str(target.resolve().relative_to(project_root))
    except Exception:
        return str(target)
