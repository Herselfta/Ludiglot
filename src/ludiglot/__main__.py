from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy
from ludiglot.core.audio_extract import (
    build_audio_index,
    collect_wem_files,
    convert_wem_to_wav,
    convert_single_wem_to_wav,
    convert_txtp_to_wav,
    default_vgmstream_path,
    default_wwiser_path,
    find_bnk_for_event,
    find_txtp_for_event,
    find_wem_by_hash,
    generate_txtp_for_bnk,
)
from ludiglot.core.audio_mapper import AudioCacheIndex
from ludiglot.core.audio_player import AudioPlayer
from ludiglot.core.capture import (
    CaptureError,
    CaptureRegion,
    capture_fullscreen,
    capture_region,
    capture_window,
)
from ludiglot.core.config import load_config
from ludiglot.core.game_pak_update import GamePakUpdateError, update_from_game_paks
from ludiglot.core.ocr import OCREngine
from ludiglot.core.search import FuzzySearcher
from ludiglot.core.text_builder import (
    build_text_db,
    build_text_db_from_maps,
    build_text_db_from_root,
    build_text_db_from_root_all,
    load_plot_audio_map,
    normalize_en,
    save_text_db,
)
from ludiglot.core.voice_map import build_voice_map_from_configdb
from ludiglot.core.voice_event_index import VoiceEventIndex
from ludiglot.core.wwise_hash import WwiseHash
from ludiglot.ui.overlay_window import run_gui


# 已移至 ludiglot.core.git_manager


def _is_wuthering_data_valid(data_root: Path) -> bool:
    """检查WutheringData目录是否包含必要的数据文件"""
    if not data_root.exists():
        return False
    
    # 检查是否有关键目录（不再检查.git）
    required_dirs = ["TextMap", "ConfigDB"]
    for dir_name in required_dirs:
        dir_path = data_root / dir_name
        if not dir_path.exists():
            return False
        # 检查目录是否为空
        if not any(dir_path.iterdir()):
            return False
    
    return True


def _check_and_setup_wuthering_data(config_path: Path) -> bool:
    """在终端中检测WutheringData，如不存在则交互式询问是否克隆。
    
    Returns:
        bool: True表示data_root可用或用户选择跳过，False表示用户取消操作
    """
    import subprocess
    
    # 检查配置文件是否存在
    if not config_path.exists():
        return True  # 让load_config处理配置文件缺失的错误
    
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return True  # 配置文件解析错误，让后续流程处理

    if raw.get("use_game_paks") or raw.get("game_install_root") or raw.get("game_pak_root"):
        return True
    
    data_root_str = raw.get("data_root")
    
    # 如果没有配置data_root，直接返回
    if not data_root_str:
        return True
    
    # 解析data_root路径
    data_root = Path(data_root_str)
    if not data_root.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        data_root = (project_root / data_root).resolve()
    
    # 检查目录是否存在且完整
    if data_root.exists():
        if _is_wuthering_data_valid(data_root):
            return True  # 目录存在且完整
        else:
            # 目录存在但不完整（可能是上次克隆失败留下的）
            print("\n" + "="*70)
            print("⚠️  WutheringData 目录不完整")
            print("="*70)
            print(f"\n检测到目录存在但不完整：{data_root}")
            print("这可能是上次克隆失败留下的空文件夹。\n")
            print("选项：")
            print("  [Y] 删除并重新克隆 (推荐)")
            print("  [N] 跳过（稍后手动处理）")
            print("  [C] 取消启动")
            print()
            
            while True:
                choice = input("请选择 [Y/N/C]: ").strip().upper()
                
                if choice == 'C':
                    return False
                
                if choice == 'N':
                    print("\n⚠️  跳过重新克隆。如需手动处理：")
                    print(f"   1. 删除目录： Remove-Item '{data_root}' -Recurse -Force")
                    print(f"   2. 重新克隆： git clone https://github.com/Dimbreath/WutheringData.git {data_root}")
                    return True
                
                if choice == 'Y':
                    # 删除不完整的目录
                    print(f"\n🗑️  正在删除不完整的目录...")
                    try:
                        import shutil
                        shutil.rmtree(data_root)
                        print("✅ 已删除\n")
                    except Exception as e:
                        print(f"\n❌ 删除失败：{e}")
                        print("请手动删除后重试。")
                        return False
                    break
                
                print("❌ 无效输入，请输入 Y、N 或 C")
    
    # WutheringData不存在，在终端中询问用户
    print("\n" + "="*70)
    print("📂 WutheringData 未找到")
    print("="*70)
    print(f"\n配置的数据目录不存在：{data_root}")
    print("\nWutheringData 是鸣潮游戏的文本和音频数据库。")
    print("将仅下载必要目录（TextMap, ConfigDB），约 50MB。")
    print("\n选项：")
    print("  [Y] 从 GitHub 自动克隆 (推荐)")
    print("  [N] 跳过（稍后手动设置）")
    print("  [C] 取消启动")
    print()
    
    while True:
        choice = input("请选择 [Y/N/C]: ").strip().upper()
        
        if choice == 'C':
            return False
        
        if choice == 'N':
            print("\n⚠️  跳过克隆。如需完整功能，请手动克隆：")
            print(f"   git clone https://github.com/Dimbreath/WutheringData.git {data_root}")
            return True
        
        if choice == 'Y':
            break
        
        print("❌ 无效输入，请输入 Y、N 或 C")
    
    # 用户选择克隆
    from ludiglot.core.git_manager import GitManager
    
    print("\n" + "="*70)
    print("🔄 开始克隆 WutheringData...")
    print("="*70)
    print(f"目标位置: {data_root}\n")
    
    success = GitManager.fast_clone_wuthering_data(
        data_root, 
        progress_callback=lambda line: print(line)
    )
    
    if success:
        print("\n" + "="*70)
        print("✅ 克隆成功！")
        print("="*70)
        print(f"位置：{data_root}\n")
        return True
    else:
        print("\n" + "="*70)
        print("❌ 克隆失败")
        print("="*70)
        print("\n请检查网络连接或手动执行：")
        print(f"git clone https://github.com/Dimbreath/WutheringData.git {data_root}")
        return False
        return False


def _check_and_setup_game_data(config_path: Path) -> bool:
    """在终端中检测游戏 Pak 解包数据，如不存在则交互式更新。"""
    if not config_path.exists():
        return True
    try:
        cfg = load_config(config_path)
    except Exception:
        return True

    if not (cfg.use_game_paks or cfg.game_install_root or cfg.game_pak_root):
        return True

    # 检查 Pak 解包数据是否存在
    data_root = cfg.data_root
    if data_root:
        data_root = Path(data_root).resolve()
        # 检查关键目录是否存在
        configdb = data_root / "ConfigDB"
        if configdb.exists() and any(configdb.iterdir()):
            # ConfigDB 存在且非空，认为数据就绪
            return True

    if not sys.stdin.isatty():
        print("\n⚠️  Pak 模式已启用，但数据缺失。请运行 ludiglot pak-update 更新数据。")
        return False

    print("\n" + "=" * 70)
    print("📦 游戏 Pak 数据未就绪")
    print("=" * 70)
    print("将从本地游戏 Pak 解包文本/音频资源。")
    print("选项：")
    print("  [Y] 立即解包并构建数据库 (推荐)")
    print("  [N] 跳过 (稍后手动执行 ludiglot pak-update)")
    print("  [C] 取消启动")

    while True:
        choice = input("请选择 [Y/N/C]: ").strip().upper()
        if choice == "C":
            return False
        if choice == "N":
            return True
        if choice == "Y":
            break
        print("❌ 无效输入，请输入 Y、N 或 C")

    try:
        update_from_game_paks(cfg, config_path, cfg.db_path, progress=lambda m: print(m))
        return True
    except GamePakUpdateError as exc:
        print(f"\n❌ Pak 更新失败: {exc}")
        return False


def _load_db(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_demo(args: argparse.Namespace) -> None:
    en_map = {
        "Main_LahaiRoi_3_1_1_2": "Stop right there!",
        "Main_LahaiRoi_3_1_1_3": "Who are you?",
    }
    zh_map = {
        "Main_LahaiRoi_3_1_1_2": "站住！",
        "Main_LahaiRoi_3_1_1_3": "你是谁？",
    }
    db = build_text_db_from_maps(en_map, zh_map, "demo.json")
    output = Path(args.output)
    save_text_db(db, output)

    query = "stop right ther"
    key = normalize_en(query)
    if key in db:
        print("Exact hit:")
        print(json.dumps(db[key], ensure_ascii=False, indent=2))
        return

    searcher = FuzzySearcher()
    best, score = searcher.search(key, db.keys())
    print(f"Best match: {best}  score={score:.3f}")
    print(json.dumps(db.get(best, {}), ensure_ascii=False, indent=2))


def cmd_build(args: argparse.Namespace) -> None:
    en_json = Path(args.en) if args.en else None
    zh_json = Path(args.zh) if args.zh else None
    output = Path(args.output)
    if en_json and zh_json:
        db = build_text_db(en_json, zh_json)
    else:
        if not args.data_root:
            raise RuntimeError("缺少 --en/--zh 或 --data-root")
        data_root = Path(args.data_root)
        db = build_text_db_from_root_all(data_root)
    save_text_db(db, output)
    print(f"OK: {output}")


def cmd_hash(args: argparse.Namespace) -> None:
    print(WwiseHash().hash_str(args.text))


def cmd_search(args: argparse.Namespace) -> None:
    db = _load_db(Path(args.db))
    query_raw = args.query.lower()
    query_norm = normalize_en(args.query)

    if query_norm in db:
        print(f"Match found for key: {query_norm}")
        print(json.dumps(db[query_norm], ensure_ascii=False, indent=2))
        return

    # 内容匹配 (CN/EN)
    hits = []
    for k, v in db.items():
        found = False
        for m in v.get("matches", []):
            if query_raw in m.get("official_en", "").lower() or query_raw in m.get("official_cn", "").lower():
                hits.append((k, m))
                found = True
                break # 每一组只出一个
        if len(hits) >= 10: break

    if hits:
        print(f"Found {len(hits)} content matches:")
        for k, m in hits:
            print(f"\n[Key: {k}]")
            print(json.dumps(m, ensure_ascii=False, indent=2))
        return

    searcher = FuzzySearcher()
    best, score = searcher.search(query_norm, db.keys())
    print(f"Best key match: {best}  score={score:.3f}")
    print(json.dumps(db.get(best, {}), ensure_ascii=False, indent=2))


def cmd_ocr(args: argparse.Namespace) -> None:
    db = _load_db(Path(args.db))
    engine = OCREngine(lang=args.lang, use_gpu=args.gpu)
    lines = engine.recognize_with_confidence(Path(args.image))

    if not lines:
        print("OCR 未识别到文本")
        return

    searcher = FuzzySearcher()
    for text, conf in lines:
        key = normalize_en(text)
        if not key:
            continue
        if key in db:
            result = db[key]
            print(f"[OCR {conf:.2f}] {text}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            continue

        best, score = searcher.search(key, db.keys())
        print(f"[OCR {conf:.2f}] {text}")
        print(f"Best match: {best}  score={score:.3f}")
        print(json.dumps(db.get(best, {}), ensure_ascii=False, indent=2))


def _find_audio(cache_dir: Path, hash_value: int) -> Path | None:
    for ext in (".wav", ".ogg", ".wem", ".mp3"):
        cand = cache_dir / f"{hash_value}{ext}"
        if cand.exists():
            return cand
    return None


def _ensure_audio_for_hash(
    cache_dir: Path,
    wem_root: Path | None,
    vgmstream_path: Path | None,
    hash_value: int,
    audio_index: AudioCacheIndex | None = None,
    event_name: str | None = None,
) -> Path | None:
    audio_path = _find_audio(cache_dir, hash_value)
    if audio_path is not None:
        return audio_path
    if wem_root is None or vgmstream_path is None:
        return None
        
    # 1. Try finding by Hash in wem_root
    wem_path = find_wem_by_hash(wem_root, hash_value)
    
    # 2. Fallback: Try finding by Event Name in WwiseExternalSource
    if wem_path is None and event_name:
        # Check if wem_root is already WwiseExternalSource or if we need to navigate
        if "WwiseExternalSource" in str(wem_root):
            ext_root = wem_root
        else:
            # Assuming wem_root is .../Media/zh, go up to .../WwiseExternalSource
            ext_root = wem_root.parents[1] / "WwiseExternalSource"
        
        if ext_root.exists():
            # Try multiple patterns
            for pat in [f"*{event_name}*.wem", f"zh_{event_name}*.wem"]:
                matches = list(ext_root.rglob(pat))
                if matches:
                    wem_path = matches[0]
                    break
    
    if wem_path is None:
        return None
        
    try:
        audio_path = convert_single_wem_to_wav(wem_path, vgmstream_path, cache_dir, output_name=str(hash_value))
    except Exception:
        return None
    if audio_index is not None:
        audio_index.add_file(audio_path)
    return audio_path


def _ensure_audio_for_event(
    cache_dir: Path,
    wem_root: Path | None,
    bnk_root: Path | None,
    txtp_cache: Path | None,
    vgmstream_path: Path | None,
    wwiser_path: Path | None,
    hash_value: int,
    event_name: str | None,
    audio_index: AudioCacheIndex | None = None,
) -> Path | None:
    audio_path = _find_audio(cache_dir, hash_value)
    if audio_path is not None:
        return audio_path
    if wem_root is None or bnk_root is None or txtp_cache is None:
        return None
    if vgmstream_path is None or wwiser_path is None:
        return None
    bnk_path = find_bnk_for_event(bnk_root, event_name)
    if bnk_path is None:
        return None
    try:
        txtp_files = generate_txtp_for_bnk(bnk_path, wem_root, txtp_cache, wwiser_path)
    except Exception:
        return None
    if not txtp_files:
        return None
    txtp_dir = txtp_cache / bnk_path.stem
    txtp_path = find_txtp_for_event(txtp_dir, event_name) or txtp_files[0]
    output_path = cache_dir / f"{hash_value}.wav"
    try:
        audio_path = convert_txtp_to_wav(txtp_path, vgmstream_path, output_path)
    except Exception:
        return None
    if audio_index is not None:
        audio_index.add_file(audio_path)
    return audio_path
def _resolve_hash_for_text_key(
    text_key: str,
    cfg: AppConfig,
    audio_index: AudioCacheIndex | None,
) -> int | None:
    data_root = cfg.data_root
    strategy = WutheringAudioStrategy()
    if data_root:
        plot_audio = load_plot_audio_map(data_root)
        voice_map = build_voice_map_from_configdb(data_root)
        candidates: list[tuple[str, int]] = []
        voice_event = plot_audio.get(text_key)
        if voice_event:
            for name in strategy.build_names(text_key, voice_event):
                candidates.append((name, strategy.hash_name(name)))
        voice_list = voice_map.get(text_key, [])
        for voice in voice_list:
            for name in strategy.build_names(text_key, voice):
                candidates.append((name, strategy.hash_name(name)))
        if not candidates:
            for name in strategy.build_names(text_key, None):
                candidates.append((name, strategy.hash_name(name)))
        seen: set[int] = set()
        for name, hash_value in candidates:
            if hash_value in seen:
                continue
            seen.add(hash_value)
            if audio_index and audio_index.find(hash_value):
                return hash_value
        if candidates:
            # 同样应用性别筛选
            pref = (cfg.gender_preference or "female").lower()
            if pref == "female":
                f_keywords = ["_f", "nvzhu", "roverf", "female"]
                f_cands = [c for c in candidates if any(k in c[0].lower() for k in f_keywords)]
                if f_cands: return f_cands[0][1]
            elif pref == "male":
                m_keywords = ["_m", "nanzhu", "roverm", "male"]
                m_cands = [c for c in candidates if any(k in c[0].lower() for k in m_keywords)]
                if m_cands: return m_cands[0][1]

            return candidates[0][1]
        return None
    return strategy.build_hash(text_key)


_EVENT_INDEX_CACHE: dict[str, VoiceEventIndex] = {}


def _collect_voice_events(data_root: Path) -> list[str]:
    events: list[str] = []
    try:
        plot_audio = load_plot_audio_map(data_root)
        events.extend([str(v) for v in plot_audio.values() if v])
    except Exception:
        pass
    try:
        voice_map = build_voice_map_from_configdb(data_root)
        for items in voice_map.values():
            if isinstance(items, list):
                events.extend([str(v) for v in items if v])
    except Exception:
        pass
    # 去重
    dedup: list[str] = []
    seen = set()
    for ev in events:
        if ev in seen:
            continue
        seen.add(ev)
        dedup.append(ev)
    return dedup


def _get_voice_event_index(cfg: AppConfig) -> VoiceEventIndex | None:
    if not cfg.audio_bnk_root and not cfg.audio_txtp_cache:
        return None

    cache_path = None
    if cfg.audio_cache_path:
        cache_path = cfg.audio_cache_path / "voice_event_index.json"

    key = f"{cfg.audio_bnk_root}|{cfg.audio_txtp_cache}|{cfg.data_root}|{cache_path}"
    cached = _EVENT_INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    extra_names: list[str] = []
    if cfg.data_root:
        extra_names = _collect_voice_events(cfg.data_root)

    index = VoiceEventIndex(
        bnk_root=cfg.audio_bnk_root,
        txtp_root=cfg.audio_txtp_cache,
        cache_path=cache_path,
        extra_names=extra_names,
    )
    index.load_or_build()
    _EVENT_INDEX_CACHE.clear()
    _EVENT_INDEX_CACHE[key] = index
    return index


def load_plot_audio_map(data_root: Path) -> Dict[str, str]:
    path = data_root / "ConfigDB" / "PlotAudio.json"
    if not path.exists():
        return {}
    try:
        from ludiglot.core.voice_map import _iter_items
        data = json.loads(path.read_text(encoding="utf-8"))
        res = {}
        for item in _iter_items(data):
            # 假设 PlotAudio.json 的 Key 是 Content/TextKey，Value 是 Voice
            tk = item.get("TextKey") or item.get("Name")
            v = item.get("Voice")
            if tk and v:
                res[tk] = v
        return res
    except Exception:
        return {}


from ludiglot.core.voice_map import (
    build_voice_map_from_configdb,
    _resolve_events_for_text_key
)


def _play_audio_for_key(
    text_key: str,
    cfg: AppConfig,
    index: AudioCacheIndex | None = None,
    audio_event: str | None = None,
    audio_hash: str | int | None = None
) -> bool:
    strategy = WutheringAudioStrategy()
    
    # 直接由解析器返回已经排序、去重、互换好的候选列表
    final_events = _resolve_events_for_text_key(text_key, cfg)
    if audio_event and audio_event not in final_events:
        final_events.insert(0, audio_event)
            
    # 如果此时还是空的，尝试回退到猜测模式
    if not final_events:
        final_events = [None]  # 让 strategy.build_names 生成默认猜测

    # 后续播放逻辑...
    wwiser_path = cfg.wwiser_path or default_wwiser_path()
    
    total_candidates = []
    seen = set()
    
    for event_name in final_events:
        for name in strategy.build_names(text_key, event_name):
            if name not in seen:
                total_candidates.append(name)
                seen.add(name)

    # 从实际音频资源建立索引，补充候选事件名
    event_index = _get_voice_event_index(cfg)
    if event_index:
        ref_event = next((e for e in final_events if e), None)
        extra = event_index.find_candidates(text_key, ref_event, limit=8)
        for name in extra:
            if name not in seen:
                total_candidates.append(name)
                seen.add(name)
    
    # 终极全局排优：不仅是 Event 名，连生成的哈希名也必须符合性别偏好
    pref = (cfg.gender_preference or "female").lower()
    f_pats = ["_f_", "nvzhu", "roverf", "_female"]
    m_pats = ["_m_", "nanzhu", "roverm", "_male"]
    target_pats = f_pats if pref == "female" else m_pats
    other_pats = m_pats if pref == "female" else f_pats

    def final_priority(n):
        nl = n.lower()
        if any(w in nl for w in target_pats): return 0
        if any(w in nl for w in other_pats): return 2
        return 1

    total_candidates.sort(key=final_priority)
    
    print(f"[AUDIO] 尝试播放 TextKey: {text_key}")
    print(f"[AUDIO] 最终排序 (前2名): {total_candidates[:2]}")
    
    # 如果有明确传入的 hash，插入到最前面
    if audio_hash:
        pass
    
    for name in total_candidates:
        h = strategy.hash_name(name)
        # 1. 查缓存
        audio_path = (index.find(h) if index else None) or _find_audio(cfg.audio_cache_path, h)
        
        # 2. 如果缓存没有，尝试从 WEM 提取 (WEM 名通常就是 hash)
        if audio_path is None and cfg.audio_wem_root and cfg.vgmstream_path:
            audio_path = _ensure_audio_for_hash(
                cfg.audio_cache_path,
                cfg.audio_wem_root,
                cfg.vgmstream_path,
                h,
                audio_index=index,
                event_name=name,
            )
    
        # 3. 如果还是没有，尝试通过 BNK Event 提取
        if audio_path is None and cfg.audio_bnk_root and cfg.audio_txtp_cache and cfg.wwiser_path:
            audio_path = _ensure_audio_for_event(
                cfg.audio_cache_path,
                cfg.audio_wem_root,
                cfg.audio_bnk_root,
                cfg.audio_txtp_cache,
                cfg.vgmstream_path,
                cfg.wwiser_path,
                h,
                name,
                audio_index=index
            )
            
        if audio_path:
            AudioPlayer().play(str(audio_path))
            return True
            
    return False


def cmd_play(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache)
    if args.hash is not None:
        hash_value = int(args.hash)
    else:
        resolved = _resolve_hash_for_text_key(args.text_key, None, None)
        if resolved is None:
            print("无法解析 TextKey 对应的音频 Hash")
            return
        hash_value = resolved

    audio_path = _find_audio(cache_dir, hash_value)
    if audio_path is None:
        print(f"未找到音频文件：{hash_value}.*")
        return
    player = AudioPlayer()
    player.play(str(audio_path))


def cmd_audio_extract(args: argparse.Namespace) -> None:
    wem_root = Path(args.wem_root)
    cache_dir = Path(args.cache)
    vgmstream_path = Path(args.vgmstream) if args.vgmstream else default_vgmstream_path()
    files = collect_wem_files(
        wem_root,
        extensions=args.ext,
        contains=args.contains,
        limit=args.limit,
    )
    if not files:
        print("未找到可用的 WEM 文件")
        return
    result = convert_wem_to_wav(
        files,
        vgmstream_path,
        cache_dir,
        preserve_paths=args.preserve_paths,
        root_dir=wem_root,
        skip_existing=not args.force,
    )
    index_path = Path(args.index_path) if args.index_path else None
    index = build_audio_index(cache_dir, index_path=index_path, max_mb=args.max_mb)
    print(
        f"WEM: {len(files)} | 转码: {result.converted} | 跳过: {result.skipped} | 失败: {result.failed} | 索引: {len(index.entries)}"
    )


def cmd_audio_build(args: argparse.Namespace) -> None:
    cfg = load_config(Path(args.config))
    wem_root = Path(args.wem_root) if args.wem_root else cfg.audio_wem_root
    cache_dir = Path(args.cache) if args.cache else cfg.audio_cache_path
    if wem_root is None:
        raise RuntimeError("缺少 --wem-root 或 config.audio_wem_root")
    if cache_dir is None:
        raise RuntimeError("缺少 --cache 或 config.audio_cache_path")
    vgmstream_path = None
    if args.vgmstream:
        vgmstream_path = Path(args.vgmstream)
    elif cfg.vgmstream_path:
        vgmstream_path = cfg.vgmstream_path
    else:
        vgmstream_path = default_vgmstream_path()
    wwiser_path = cfg.wwiser_path or default_wwiser_path()
    bnk_root = cfg.audio_bnk_root
    txtp_cache = cfg.audio_txtp_cache

    index_path = Path(args.index_path) if args.index_path else cfg.audio_cache_index_path
    index = build_audio_index(cache_dir, index_path=index_path, max_mb=args.max_mb)

    if args.full_convert:
        files = collect_wem_files(
            wem_root,
            extensions=args.ext,
            contains=args.contains,
            limit=args.limit,
        )
        if not files:
            print("未找到可用的 WEM 文件")
            return
        result = convert_wem_to_wav(
            files,
            vgmstream_path,
            cache_dir,
            preserve_paths=args.preserve_paths,
            root_dir=wem_root,
            skip_existing=not args.force,
        )
        index.scan()
        print(
            f"WEM: {len(files)} | 转码: {result.converted} | 跳过: {result.skipped} | 失败: {result.failed} | 索引: {len(index.entries)}"
        )

    if args.test_hash or args.test_text_key:
        if args.test_hash:
            hash_val = int(args.test_hash)
            audio_path = (index.find(hash_val) if index else None) or _find_audio(cache_dir, hash_val)
            if not audio_path:
                audio_path = _ensure_audio_for_hash(cache_dir, wem_root, vgmstream_path, hash_val, index)
            if audio_path:
                AudioPlayer().play(str(audio_path))
            else:
                print(f"未找到哈希 {hash_val} 对应的音频")
        else:
            if not _play_audio_for_key(args.test_text_key, cfg, index):
                print(f"测试播放失败：未找到对应音频 {args.test_text_key}")

    if args.start_gui:
        run_gui(Path(args.config))


def cmd_run(args: argparse.Namespace) -> None:
    cfg = load_config(Path(args.config))

    if not cfg.db_path.exists():
        if cfg.data_root:
            db = build_text_db_from_root_all(cfg.data_root)
        else:
            db = build_text_db(cfg.en_json, cfg.zh_json)
        save_text_db(db, cfg.db_path)

    try:
        if cfg.capture_mode == "window":
            if not cfg.window_title:
                raise RuntimeError("capture_mode=window 需要 window_title")
            capture_window(cfg.window_title, cfg.image_path)
        elif cfg.capture_mode == "region":
            if not cfg.capture_region:
                raise RuntimeError("capture_mode=region 需要 capture_region")
            region = CaptureRegion(
                left=int(cfg.capture_region["left"]),
                top=int(cfg.capture_region["top"]),
                width=int(cfg.capture_region["width"]),
                height=int(cfg.capture_region["height"]),
            )
            capture_region(region, cfg.image_path)
        elif cfg.capture_mode == "image":
            if not cfg.image_path.exists():
                capture_fullscreen(cfg.image_path)
        else:
            raise RuntimeError(f"未知 capture_mode: {cfg.capture_mode}")
    except CaptureError as exc:
        print(f"捕获失败：{exc}，将回退到全屏截图")
        capture_fullscreen(cfg.image_path)

    db = _load_db(cfg.db_path)
    engine = OCREngine(
        lang=cfg.ocr_lang,
        use_gpu=cfg.ocr_gpu,
        mode=cfg.ocr_mode,
        glm_endpoint=getattr(cfg, "ocr_glm_endpoint", None),
        glm_model=getattr(cfg, "ocr_glm_model", None),
        glm_timeout=getattr(cfg, "ocr_glm_timeout", None),
    )
    try:
        engine.win_ocr_adaptive = bool(getattr(cfg, "ocr_adaptive", True))
        engine.win_ocr_preprocess = bool(getattr(cfg, "ocr_preprocess", False))
        engine.win_ocr_line_refine = bool(getattr(cfg, "ocr_line_refine", False))
        engine.win_ocr_segment = bool(getattr(cfg, "ocr_word_segment", False))
        engine.win_ocr_multiscale = bool(getattr(cfg, "ocr_multiscale", False))
    except Exception:
        pass
    cache_index = None
    if cfg.audio_cache_path and cfg.scan_audio_on_start:
        cache_index = AudioCacheIndex(
            cfg.audio_cache_path,
            index_path=cfg.audio_cache_index_path,
            max_mb=cfg.audio_cache_max_mb,
        )
        cache_index.load()
        cache_index.scan()
    wwiser_path = cfg.wwiser_path or default_wwiser_path()
    lines = engine.recognize_with_confidence(cfg.image_path, backend=cfg.ocr_backend)

    if not lines:
        print("OCR 未识别到文本")
        return

    searcher = FuzzySearcher()
    for text, conf in lines:
        key = normalize_en(text)
        if not key:
            continue
        if key in db:
            result = db[key]
        else:
            best, score = searcher.search(key, db.keys())
            result = db.get(best, {})
            result = {**result, "_score": round(score, 3)}

        print(f"[OCR {conf:.2f}] {text}")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if cfg.play_audio and cfg.audio_cache_path and result.get("matches"):
            match = result["matches"][0]
            text_key = match.get("text_key")
            if text_key:
                _play_audio_for_key(
                    text_key, 
                    cfg, 
                    index=cache_index,
                    audio_event=match.get("audio_event"),
                    audio_hash=match.get("audio_hash")
                )


def cmd_gui(args: argparse.Namespace) -> None:
    config_path = Path(args.config)
    
    # 检查配置文件是否存在
    if not config_path.exists():
        print("\n" + "="*70)
        print("📝 配置文件不存在")
        print("="*70)
        print(f"\n请将 config/settings.example.json 重命名为 settings.json 并配置数据路径。\n")
        print("="*70 + "\n")
        return
    
    # 在启动GUI前先在终端中检测和处理WutheringData / Pak 数据
    if not _check_and_setup_game_data(config_path):
        print("\n❌ 启动已取消。")
        return
    if not _check_and_setup_wuthering_data(config_path):
        print("\n❌ 启动已取消。")
        return
    
    run_gui(config_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ludiglot")
    parser.add_argument("--config", default="config/settings.json")
    sub = parser.add_subparsers(dest="cmd", required=False)

    demo = sub.add_parser("demo", help="生成演示 DB 并做一次查询")
    demo.add_argument("--output", default="game_text_db.json")
    demo.set_defaults(func=cmd_demo)

    build = sub.add_parser("build", help="从 MultiText JSON 构建 DB")
    build.add_argument("--en", help="英文 MultiText JSON")
    build.add_argument("--zh", help="中文 MultiText JSON")
    build.add_argument("--data-root", help="WutheringData 根目录（可自动定位 MultiText）")
    build.add_argument("--output", default="game_text_db.json")
    build.set_defaults(func=cmd_build)

    hash_cmd = sub.add_parser("hash", help="计算 vo_ 哈希")
    hash_cmd.add_argument("text")
    hash_cmd.set_defaults(func=cmd_hash)

    search = sub.add_parser("search", help="在 DB 中查询")
    search.add_argument("--db", required=True)
    search.add_argument("query")
    search.set_defaults(func=cmd_search)

    ocr = sub.add_parser("ocr", help="对图片进行 OCR 并查库")
    ocr.add_argument("--image", required=True, help="截图或图片路径")
    ocr.add_argument("--db", required=True, help="game_text_db.json")
    ocr.add_argument("--lang", default="en", help="OCR 语言，如 en/zh")
    ocr.add_argument("--gpu", action="store_true", help="启用 GPU")
    ocr.set_defaults(func=cmd_ocr)

    play = sub.add_parser("play", help="按 TextKey/Hash 播放音频")
    play.add_argument("--cache", required=True, help="音频缓存目录")
    group = play.add_mutually_exclusive_group(required=True)
    group.add_argument("--text-key", help="文本 Key，如 Main_LahaiRoi_3_1_1_2")
    group.add_argument("--hash", help="已知的 Hash 数值")
    play.set_defaults(func=cmd_play)

    audio = sub.add_parser("audio-extract", help="从 FModel 导出的 WEM 转码并建立索引")
    audio.add_argument("--wem-root", required=True, help="FModel 导出的 WEM 根目录")
    audio.add_argument("--cache", required=True, help="输出音频缓存目录")
    audio.add_argument("--vgmstream", help="vgmstream-cli.exe 路径")
    audio.add_argument("--ext", nargs="+", default=[".wem"], help="过滤扩展名")
    audio.add_argument("--contains", nargs="*", default=None, help="路径包含关键词")
    audio.add_argument("--limit", type=int, help="仅处理前 N 个")
    audio.add_argument("--preserve-paths", action="store_true", help="保留导出目录结构")
    audio.add_argument("--force", action="store_true", help="覆盖已有文件")
    audio.add_argument("--index-path", help="缓存索引输出路径")
    audio.add_argument("--max-mb", type=int, default=2048, help="缓存上限 (MB)")
    audio.set_defaults(func=cmd_audio_extract)

    audio_build = sub.add_parser("audio-build", help="自动构建语音缓存并可选测试/启动 GUI")
    audio_build.add_argument("--config", default="config/settings.json")
    audio_build.add_argument("--wem-root", help="FModel 导出的 WEM 根目录")
    audio_build.add_argument("--cache", help="输出音频缓存目录")
    audio_build.add_argument("--vgmstream", help="vgmstream-cli.exe 路径")
    audio_build.add_argument("--ext", nargs="+", default=[".wem"], help="过滤扩展名")
    audio_build.add_argument("--contains", nargs="*", default=None, help="路径包含关键词")
    audio_build.add_argument("--limit", type=int, help="仅处理前 N 个")
    audio_build.add_argument("--preserve-paths", action="store_true", help="保留导出目录结构")
    audio_build.add_argument("--force", action="store_true", help="覆盖已有文件")
    audio_build.add_argument("--index-path", help="缓存索引输出路径")
    audio_build.add_argument("--max-mb", type=int, default=2048, help="缓存上限 (MB)")
    audio_build.add_argument("--full-convert", action="store_true", help="全量转码（默认按需）")
    audio_build.add_argument("--test-text-key", help="构建后按 TextKey 播放测试")
    audio_build.add_argument("--test-hash", help="构建后按 Hash 播放测试")
    audio_build.add_argument("--start-gui", action="store_true", help="构建完成后启动 GUI")
    audio_build.set_defaults(func=cmd_audio_build)

    run = sub.add_parser("run", help="一键运行：构建DB + OCR + 查库(+播放)")
    run.add_argument("--config", default="config/settings.json")
    run.set_defaults(func=cmd_run)

    gui = sub.add_parser("gui", help="启动 GUI 覆盖层")
    gui.add_argument("--config", default="config/settings.json")
    gui.set_defaults(func=cmd_gui)

    pak_update = sub.add_parser("pak-update", help="从本地游戏 Pak 解包并重建数据库")
    pak_update.add_argument("--config", default="config/settings.json")
    pak_update.set_defaults(func=cmd_pak_update)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd is None:
        cmd_gui(argparse.Namespace(config=args.config))
        return
    args.func(args)


def cmd_pak_update(args: argparse.Namespace) -> None:
    cfg = load_config(Path(args.config))
    try:
        update_from_game_paks(cfg, Path(args.config), cfg.db_path, progress=print)
        print("✅ Pak 更新完成")
    except GamePakUpdateError as exc:
        print(f"❌ Pak 更新失败: {exc}")


if __name__ == "__main__":
    main()
