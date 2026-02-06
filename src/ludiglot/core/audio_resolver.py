from __future__ import annotations

import time
from pathlib import Path
from typing import NamedTuple, Any, List

from ludiglot.core.config import AppConfig
from ludiglot.core.voice_map import _resolve_events_for_text_key
from ludiglot.core.voice_event_index import VoiceEventIndex
from ludiglot.core.audio_mapper import AudioCacheIndex
from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy
from ludiglot.core.audio_extract import (
    find_wem_by_hash, find_bnk_for_event, find_wem_by_event_name, 
    default_wwiser_path, find_txtp_for_event, 
    convert_single_wem_to_wav, generate_txtp_for_bnk, convert_txtp_to_wav
)
import shutil

class AudioResolution(NamedTuple):
    hash_value: int
    event_name: str
    source_type: str  # 'cache', 'wem', 'bnk', 'unknown'

class AudioResolver:
    def __init__(self, config: AppConfig, voice_event_index: VoiceEventIndex = None):
        self.config = config
        self.strategy = WutheringAudioStrategy()
        self._audio_index: AudioCacheIndex | None = None
        self._voice_event_index = voice_event_index
        
    @property
    def audio_index(self) -> AudioCacheIndex | None:
        if not self.config.audio_cache_path:
            return None
        if self._audio_index is None:
            self._audio_index = AudioCacheIndex(
                self.config.audio_cache_path,
                index_path=self.config.audio_cache_index_path,
                max_mb=self.config.audio_cache_max_mb
            )
            self._audio_index.load()
            self._audio_index.scan()
        return self._audio_index

    def get_candidates(self, text_key: str | None, db_event: str | None = None) -> List[str]:
        """依据 TextKey 和数据库已知 Event，生成经过性别排序的候选列表。"""
        events = []
        if text_key:
            events = _resolve_events_for_text_key(text_key, self.config)
        
        if db_event:
            clean_db_event = self.strategy._parse_event_name(db_event)
            if clean_db_event and clean_db_event not in events:
                # 如果是通过 text_key 解析出来的，保持其优先级。
                # 数据库自带的 Event 放在 Stage 0 的末尾，作为参考而非绝对权威。
                events.append(clean_db_event)

        # 0. 准备阶段容器
        stages: list[list[str]] = [
            events,  # Stage 0: DB/TextMap (Highest Confidence)
            [],      # Stage 1: Strategy Heuristics (High Confidence)
            []       # Stage 2: Fuzzy/Index Search (Low Confidence)
        ]

        # 1. 填充 Stage 1 (Strategy) 和 Stage 2 (Fuzzy)
        if text_key:
            stages[1].extend(self.strategy.build_names(text_key, None))
            
            # 恢复模糊搜索：无论是否是 Story ID，如果 Strategy 没命中，都需要 Fuzzy 作为兜底
            # 旧版逻辑证明这是必要的，且通过分级排序可以避免误匹配
            if self._voice_event_index:
                 seed = events[0] if events else None
                 stages[2].extend(self._voice_event_index.find_candidates(text_key, seed, limit=8))

        elif db_event:
            stages[1].extend(self.strategy.build_names(None, db_event))

        # 2. 定义性别排序优先级
        pref = (self.config.gender_preference or "female").lower()
        f_pats = ["_f", "nvzhu", "roverf", "_female"]
        m_pats = ["_m", "nanzhu", "roverm", "_male"]
        target_pats = f_pats if pref == "female" else m_pats
        other_pats = m_pats if pref == "female" else f_pats

        def get_priority(n: str) -> int:
            nl = n.lower()
            if any(w in nl for w in target_pats): return 0  # 命中偏好性别
            if any(w in nl for w in other_pats): return 2   # 命中相反性别
            return 1                                        # 中性/未知

        # 3. 分阶段处理：生成性别变体 -> 组内排序 -> 合并
        final_names: list[str] = []
        seen = set()

        for stage_names in stages:
            # A. 为当前阶段的每个候选项生成性别变体 (扩充)
            # 这样做是为了保证：Stage 1 的 "Name_F" 仍然属于 Stage 1，优于 Stage 2 的任何东西
            expanded_stage = []
            for name in stage_names:
                if not name: continue
                expanded_stage.append(name)
                
                nl = name.lower()
                # 如果本身是中性的，尝试生成性别变体
                if not any(w in nl for w in ["_f", "_m", "nanzhu", "nvzhu", "roverf", "roverm"]):
                    expanded_stage.append(f"{name}_f")
                    expanded_stage.append(f"{name}_m")
            
            # B. 组内排序
            stage_sorted = sorted(expanded_stage, key=get_priority)
            
            # C. 添加到最终列表 (去重)
            for name in stage_sorted:
                if name not in seen:
                    seen.add(name)
                    final_names.append(name)
            
        return final_names

    def resolve(self, text_key: str | None, db_event: str | None = None, db_hash: int | None = None) -> AudioResolution | None:
        """全流程解析音频。
        
        优化：避免慢速文件系统扫描，优先使用缓存和直接路径。
        """
        candidates = self.get_candidates(text_key, db_event)
        
        final_candidates: list[tuple[str, int]] = []
        for name in candidates:
            final_candidates.append((name, self.strategy.hash_name(name)))

        if not final_candidates:
            if db_hash:
                return AudioResolution(int(db_hash), "unknown_from_db", "unknown")
            return None

        index = self.audio_index
        wem_root = self.config.audio_wem_root
        
        # === 第一优先级：缓存查找（O(1)，非常快） ===
        for name, h in final_candidates:
            if index and index.find(h):
                return AudioResolution(h, name, 'cache')
        
        # === 第二优先级：直接路径查找（O(1)） ===
        if wem_root:
            for name, h in final_candidates:
                direct = wem_root / f"{h}.wem"
                if direct.exists():
                    return AudioResolution(h, name, 'wem')
        
        # === 第三优先级：使用数据库提供的hash（跳过慢速扫描） ===
        if db_hash:
            # 检查缓存中是否有这个hash
            if index and index.find(int(db_hash)):
                return AudioResolution(int(db_hash), final_candidates[0][0] if final_candidates else "unknown", 'cache')
            # 检查直接路径
            if wem_root:
                direct = wem_root / f"{db_hash}.wem"
                if direct.exists():
                    return AudioResolution(int(db_hash), final_candidates[0][0] if final_candidates else "unknown", 'wem')
            # 返回db_hash作为后备，让播放器尝试
            return AudioResolution(int(db_hash), final_candidates[0][0] if final_candidates else "unknown_from_db", "db_fallback")
        
        # === 最后：返回计算的hash（跳过BNK扫描，太慢） ===
        if final_candidates:
            return AudioResolution(final_candidates[0][1], final_candidates[0][0], 'computed')
        
        return None

    def ensure_playable_audio(
        self, 
        hash_value: int, 
        text_key: str | None, 
        event_name: str | None,
        log_callback: Any = None
    ) -> Path | None:
        """确保音频可播放（提取WEM/生成TXTP/转码WAV）。"""
        def log(msg):
            if log_callback: log_callback(msg)
        
        index = self.audio_index
        # 1. 再次检查缓存 (可能刚刚被另一个线程生成了)
        if index:
            cached = index.find(hash_value)
            if cached: 
                return cached
        
        wem_root = self.config.audio_wem_root
        external_root = self.config.audio_external_root
        bnk_root = self.config.audio_bnk_root
        
        # 2. 检查 WEM 物理文件 (多目录搜寻)
        search_roots = []
        if wem_root: search_roots.append(wem_root)
        if external_root: search_roots.append(external_root)
        
        wem_file = None
        for root in search_roots:
            wem_file = find_wem_by_hash(root, hash_value)
            if not wem_file and event_name:
                wem_file = find_wem_by_event_name(root, event_name)
            if wem_file:
                break
        
        if wem_file:
            log(f"[AUDIO] 发现 WEM 文件: {wem_file.name}")
            try:
                wav_path = convert_single_wem_to_wav(
                    wem_file, 
                    self.config.vgmstream_path,
                    self.config.audio_cache_path,
                    output_name=str(hash_value),
                )
                if wav_path:
                    # 为了兼容 AudioCacheIndex (只识别数字文件名)，重命名为 hash.wav
                    final_path = wav_path.parent / f"{hash_value}{wav_path.suffix}"
                    if final_path != wav_path:
                         # 如果目标存在且有效，直接使用
                        if final_path.exists() and final_path.stat().st_size > 0:
                            wav_path = final_path
                        else:
                            shutil.move(wav_path, final_path)
                            wav_path = final_path
                    
                    if index:
                        index.add_file(wav_path)
                return wav_path
            except Exception as e:
                log(f"[ERROR] WEM 转码失败: {e}")
                return None

        # 3. 检查 BNK 并生成 TXTP
        if bnk_root and (event_name or hash_value):
            log(f"[AUDIO] 尝试从 BNK 提取: {event_name or hash_value}")
            txtp_cache = self.config.audio_txtp_cache
            if not txtp_cache and self.config.audio_cache_path:
                txtp_cache = self.config.audio_cache_path / "txtp_cache"
                txtp_cache.mkdir(exist_ok=True)
            
            # 使用 wwiser 生成 txtp
            bnk_file = None
            if event_name:
                bnk_file = find_bnk_for_event(bnk_root, event_name)
            
            # 如果没找到 BNK 但有 event_name，或许可以直接搜现有的 txtp?
            txtp_file = None
            if event_name:
                 txtp_file = find_txtp_for_event(txtp_cache, event_name)
            
            if not txtp_file and bnk_file and txtp_cache:
                try:
                    # 调用 wwiser
                    wwiser_path = default_wwiser_path() 
                    txtp_file = generate_txtp_for_bnk(bnk_file, event_name or str(hash_value), txtp_cache)
                except Exception as e:
                    log(f"[ERROR] BNK 处理失败: {e}")
            
            if txtp_file:
                log(f"[AUDIO] 发现/生成 TXTP: {txtp_file.name}")
                try:
                    wav_path = convert_txtp_to_wav(
                        txtp_file,
                        self.config.vgmstream_path,
                        self.config.audio_cache_path
                    )
                    if wav_path:
                        # 重命名为 hash.wav
                        final_path = wav_path.parent / f"{hash_value}{wav_path.suffix}"
                        if final_path != wav_path:
                            if final_path.exists() and final_path.stat().st_size > 0:
                                wav_path = final_path
                            else:
                                shutil.move(wav_path, final_path)
                                wav_path = final_path
                        
                        if index:
                            index.add_file(wav_path)
                    return wav_path
                except Exception as e:
                    log(f"[ERROR] TXTP 转码失败: {e}")
        
        
        return None


def resolve_external_wem_root(config: AppConfig) -> Path | None:
    """尝试解析 WwiseExternalSource 目录位置。"""
    if not config.audio_wem_root:
        return None
    try:
        # e.g. Client/Saved/WwiseAudio/Media/zh -> Client/Saved/WwiseAudio/WwiseExternalSource
        # config.audio_wem_root usually points to .../Media/zh or similar
        # parent=Media, parent.parent=WwiseAudio/Platform
        
        # Let's handle generic traversal upwards till we find WwiseExternalSource?
        # Or stick to the specific structure logic from overlay_window.
        # Original: base = self.config.audio_wem_root.parents[1]
        
        base = config.audio_wem_root.parents[1]
        candidate = base / "WwiseExternalSource"
        if candidate.exists():
            return candidate
        candidate = base / "WwiseExternalSource" / "zh" 
        if candidate.exists():
            return candidate
            
        # Try parents[2] just in case structure differs slightly
        if len(config.audio_wem_root.parts) > 3:
             base2 = config.audio_wem_root.parents[2]
             candidate = base2 / "WwiseExternalSource"
             if candidate.exists(): return candidate
             
    except Exception:
        return None
    return None
