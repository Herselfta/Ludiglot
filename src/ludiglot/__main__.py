from __future__ import annotations

import argparse
import json
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
    
    data_root_str = raw.get("data_root")
    
    # 如果没有配置data_root，直接返回
    if not data_root_str:
        return True
    
    # 解析data_root路径
    data_root = Path(data_root_str)
    if not data_root.is_absolute():
        project_root = Path(__file__).resolve().parents[2]
        data_root = (project_root / data_root).resolve()
    
    # 如果已经存在，直接返回
    if data_root.exists():
        return True
    
    # WutheringData不存在，在终端中询问用户
    print("\n" + "="*70)
    print("📂 WutheringData 未找到")
    print("="*70)
    print(f"\n配置的数据目录不存在：{data_root}")
    print("\nWutheringData 是鸣潮游戏的文本和音频数据库。")
    print("仓库大小约 200MB，需要 git 命令。")
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
    print("\n" + "="*70)
    print("🔄 开始克隆 WutheringData...")
    print("="*70)
    print(f"目标位置: {data_root}")
    print("这可能需要几分钟，请耐心等待...\n")
    
    try:
        # 确保父目录存在
        data_root.parent.mkdir(parents=True, exist_ok=True)
        
        # 获取系统代理设置
        import os
        env = os.environ.copy()
        
        # 尝试从git全局配置中获取代理设置
        proxy_configured = False
        try:
            http_proxy_result = subprocess.run(
                ["git", "config", "--global", "--get", "http.proxy"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if http_proxy_result.returncode == 0 and http_proxy_result.stdout.strip():
                proxy_configured = True
                print(f"🔑 检测到 Git 代理设置: {http_proxy_result.stdout.strip()}")
        except Exception:
            pass
        
        # 如果没有git代理，尝试使用系统环境变量中的代理
        if not proxy_configured:
            system_proxy = env.get('HTTP_PROXY') or env.get('http_proxy') or \
                          env.get('HTTPS_PROXY') or env.get('https_proxy')
            if system_proxy:
                print(f"🔑 使用系统代理: {system_proxy}")
                env['HTTP_PROXY'] = system_proxy
                env['HTTPS_PROXY'] = system_proxy
        
        # 执行git clone，实时显示输出
        process = subprocess.Popen(
            ["git", "clone", "--progress", "https://github.com/Dimbreath/WutheringData.git", str(data_root)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        
        # 实时打印输出
        for line in process.stdout:
            print(line, end='')
        
        process.wait()
        
        if process.returncode != 0:
            print("\n" + "="*70)
            print("❌ 克隆失败")
            print("="*70)
            print("\n请检查：")
            print("  1. 是否已安装 git 命令")
            print("  2. 网络连接是否正常")
            print("  3. 目标路径是否有写入权限")
            print("\n手动克隆命令：")
            print(f"  git clone https://github.com/Dimbreath/WutheringData.git {data_root}")
            print()
            return False
        
        print("\n" + "="*70)
        print("✅ 克隆成功！")
        print("="*70)
        print(f"位置：{data_root}\n")
        return True
        
    except FileNotFoundError:
        print("\n" + "="*70)
        print("❌ Git 未安装")
        print("="*70)
        print("\n请先安装 Git：")
        print("  https://git-scm.com/downloads")
        print("\n或手动克隆仓库：")
        print(f"  git clone https://github.com/Dimbreath/WutheringData.git {data_root}")
        print()
        return False
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作。")
        return False
    except Exception as e:
        print("\n" + "="*70)
        print("❌ 克隆过程出错")
        print("="*70)
        print(f"\n错误信息：{e}\n")
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
    query = normalize_en(args.query)

    if query in db:
        print(json.dumps(db[query], ensure_ascii=False, indent=2))
        return

    searcher = FuzzySearcher()
    best, score = searcher.search(query, db.keys())
    print(f"Best match: {best}  score={score:.3f}")
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
) -> Path | None:
    audio_path = _find_audio(cache_dir, hash_value)
    if audio_path is not None:
        return audio_path
    if wem_root is None or vgmstream_path is None:
        return None
    wem_path = find_wem_by_hash(wem_root, hash_value)
    if wem_path is None:
        return None
    try:
        audio_path = convert_single_wem_to_wav(wem_path, vgmstream_path, cache_dir)
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
    data_root: Path | None,
    audio_index: AudioCacheIndex | None,
) -> int | None:
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


def _resolve_event_for_text_key(text_key: str, data_root: Path | None) -> str | None:
    if not data_root:
        return None
    plot_audio = load_plot_audio_map(data_root)
    voice_event = plot_audio.get(text_key)
    if voice_event:
        return voice_event
    from ludiglot.core.voice_map import build_voice_map_from_configdb
    voice_map = build_voice_map_from_configdb(data_root)
    candidates = voice_map.get(text_key) or []
    return candidates[0] if candidates else None


def _play_audio_for_key(
    text_key: str,
    cfg: AppConfig,
    index: AudioCacheIndex | None = None,
    audio_event: str | None = None,
    audio_hash: str | int | None = None
) -> bool:
    strategy = WutheringAudioStrategy()
    
    # 确定初始事件名
    event_from_db = audio_event or _resolve_event_for_text_key(text_key, cfg.data_root)

    # 如果提供了 hash，优先尝试直接播放
    if audio_hash is not None:
        try:
            h = int(audio_hash)
            audio_path = (index.find(h) if index else None) or _find_audio(cfg.audio_cache_path, h)
            if audio_path is None and cfg.audio_wem_root and cfg.vgmstream_path:
                audio_path = _ensure_audio_for_hash(
                    cfg.audio_cache_path,
                    cfg.audio_wem_root,
                    cfg.vgmstream_path,
                    h,
                    audio_index=index,
                )
            if audio_path:
                AudioPlayer().play(str(audio_path))
                return True
        except Exception:
            pass
    
    # 获取所有候选 Hash 和名称映射
    # build_names 已经按照优先级排好序了
    candidates = strategy.build_names(text_key, event_from_db)

    # 从实际音频资源建立索引，补充候选事件名
    event_index = _get_voice_event_index(cfg)
    if event_index:
        extra_candidates = event_index.find_candidates(text_key, event_from_db, limit=8)
        for name in extra_candidates:
            if name not in candidates:
                candidates.append(name)
    
    # 如果有明确传入的 hash，插入到最前面
    if audio_hash:
        try:
            h = int(audio_hash)
            if h not in [strategy.hash_name(c) for c in candidates]:
                # 这种情况下无法对应回 event_name，但可以尝试 wem 转换
                pass 
        except: pass

    wwiser_path = cfg.wwiser_path or default_wwiser_path()
    
    for name in candidates:
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
                audio_index=index
            )
            
        # 3. 如果还是没有，尝试通过 BNK Event 提取
        if audio_path is None and cfg.audio_bnk_root and cfg.audio_txtp_cache and wwiser_path:
            # 使用当前 candidate 作为 event_name 尝试
            audio_path = _ensure_audio_for_event(
                cfg.audio_cache_path,
                cfg.audio_wem_root,
                cfg.audio_bnk_root,
                cfg.audio_txtp_cache,
                cfg.vgmstream_path,
                wwiser_path,
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
    engine = OCREngine(lang=cfg.ocr_lang, use_gpu=cfg.ocr_gpu, mode=cfg.ocr_mode)
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
    lines = engine.recognize_with_confidence(cfg.image_path)

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
        print(f"\n路径: {config_path}")
        print("\nLudiglot 需要一个配置文件才能运行。\n")
        print("🚀 快速开始：")
        print("\n1. 创建配置目录和文件：")
        print(f"   New-Item -Path '{config_path.parent}' -ItemType Directory -Force")
        print(f"   New-Item -Path '{config_path}' -ItemType File -Force")
        print("\n2. 添加基础配置（复制以下内容到配置文件）：")
        print("   {")
        print('     "data_root": "data/WutheringData",')
        print('     "db_path": "data/game_text_db.json",')
        print('     "auto_rebuild_db": true,')
        print('     "ocr_backend": "auto",')
        print('     "play_audio": true')
        print("   }")
        print("\n3. 重新运行程序。")
        print("\n📖 详细配置说明请参考: README.md")
        print("="*70 + "\n")
        return
    
    # 在启动GUI前先在终端中检测和处理WutheringData
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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd is None:
        cmd_gui(argparse.Namespace(config=args.config))
        return
    args.func(args)


if __name__ == "__main__":
    main()
