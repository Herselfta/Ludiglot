from __future__ import annotations

import time
from pathlib import Path
from typing import NamedTuple, Any, List

from ludiglot.core.config import AppConfig
from ludiglot.core.voice_map import _resolve_events_for_text_key
from ludiglot.core.voice_event_index import VoiceEventIndex
from ludiglot.core.audio_mapper import AudioCacheIndex
from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy
from ludiglot.core.audio_extract import find_wem_by_hash, find_bnk_for_event, find_wem_by_event_name

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

        stages: list[list[str]] = [
            events,
            [],
            []
        ]

        if text_key:
            stages[1].extend(self.strategy.build_names(text_key, None))
            
            # 限制剧情 ID 的模糊搜索：如果 ID 看起来很长且具有典型的剧情结构，禁止模糊发现
            is_story_id = "_" in text_key and sum(ch.isdigit() for ch in text_key) >= 3
            if self._voice_event_index and not is_story_id:
                 seed = events[0] if events else None
                 stages[2].extend(self._voice_event_index.find_candidates(text_key, seed, limit=8))
            elif is_story_id:
                 # 对于剧情 ID，即使没搜到，也不允许模糊 fallback 到邻近 ID
                 pass
        elif db_event:
            # 只有事件名时，添加其变体
            stages[1].extend(self.strategy.build_names(None, db_event))

        pref = (self.config.gender_preference or "female").lower()
        f_pats = ["_f_", "nvzhu", "roverf", "_female"]
        m_pats = ["_m_", "nanzhu", "roverm", "_male"]
        target_pats = f_pats if pref == "female" else m_pats
        other_pats = m_pats if pref == "female" else f_pats

        def get_priority(n):
            nl = n.lower()
            if any(w in nl for w in target_pats): return 0
            if any(w in nl for w in other_pats): return 2
            return 1

        # 收集所有阶段的候选者
        all_stage_names: list[str] = []
        for stage_names in stages:
            for name in stage_names:
                if name and name not in all_stage_names:
                    all_stage_names.append(name)
        
        # 为没有性别标记的候选者主动生成性别版本，确保第一时间覆盖
        extra_gendered = []
        for name in all_stage_names:
            nl = name.lower()
            if not any(w in nl for w in ["_f", "_m", "nanzhu", "nvzhu", "roverf", "roverm"]):
                extra_gendered.append(f"{name}_f")
                extra_gendered.append(f"{name}_m")
        
        all_stage_names.extend(extra_gendered)

        pref = (self.config.gender_preference or "female").lower()
        f_pats = ["_f", "nvzhu", "roverf", "_female"]
        m_pats = ["_m", "nanzhu", "roverm", "_male"]
        target_pats = f_pats if pref == "female" else m_pats
        other_pats = m_pats if pref == "female" else f_pats

        def get_priority(n):
            nl = n.lower()
            # 优先匹配指定性别的，然后是中性的，最后是反性别的
            if any(w in nl for w in target_pats): return 0
            if any(w in nl for w in other_pats): return 2
            return 1

        final_names: list[str] = []
        seen = set()
        # 全局按照性别偏好排序
        sorted_all = sorted(all_stage_names, key=get_priority)
        for name in sorted_all:
            if not name or name in seen:
                continue
            seen.add(name)
            final_names.append(name)
            
        return final_names

    def resolve(self, text_key: str | None, db_event: str | None = None, db_hash: int | None = None) -> AudioResolution | None:
        """全流程解析音频。"""
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
        bnk_root = self.config.audio_bnk_root
        external_root = self.config.audio_external_root
        
        for name, h in final_candidates:
            if index and index.find(h):
                return AudioResolution(h, name, 'cache')
            if wem_root and find_wem_by_hash(wem_root, h):
                return AudioResolution(h, name, 'wem')
            if external_root and find_wem_by_event_name(wem_root, name, external_root=external_root):
                return AudioResolution(h, name, 'wem')
            if bnk_root and find_bnk_for_event(bnk_root, name):
                return AudioResolution(h, name, 'bnk')
        
        # 兜底
        return AudioResolution(final_candidates[0][1], final_candidates[0][0], 'unknown')
