from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from ludiglot.core.config import AppConfig
from ludiglot.core.voice_map import _resolve_events_for_text_key
from ludiglot.core.voice_event_index import VoiceEventIndex
from ludiglot.core.audio_mapper import AudioCacheIndex
from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy
from ludiglot.core.audio_extract import find_wem_by_hash, find_bnk_for_event

class AudioResolution(NamedTuple):
    hash_value: int
    event_name: str
    source_type: str # 'cache', 'wem', 'bnk'
    
class AudioResolver:
    def __init__(self, config: AppConfig):
        self.config = config
        self.strategy = WutheringAudioStrategy()
        self._audio_index: AudioCacheIndex | None = None
        self._voice_event_index: VoiceEventIndex | None = None
        
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
        
    @property
    def voice_event_index(self) -> VoiceEventIndex | None:
        if not self.config.audio_bnk_root:
            return None
        if self._voice_event_index is None:
            # 这里可能需要根据实际情况初始化 index，通常它是全量的
            # 简化起见，这里假设 VoiceEventIndex 可以按需加载或者在外部共享
            # 目前 OverlayWindow 是自己构建的，我们在 AudioResolver 里也构建一个
            idx_path = self.config.data_root.parent / "cache" / "voice_event_index.json"
            self._voice_event_index = VoiceEventIndex(idx_path)
            if idx_path.exists():
                self._voice_event_index.load()
        return self._voice_event_index

    def resolve(self, text_key: str, override_event: str | None = None) -> AudioResolution | None:
        """
        全流程解析音频：TextKey -> Events -> Priority Sort -> Hash -> Existence Check -> Result
        """
        # 1. 获取事件列表 (已包含性别互换和重排逻辑)
        events = _resolve_events_for_text_key(text_key, self.config)
        
        # 将 override_event 插入首位
        if override_event and override_event not in events:
            events.insert(0, override_event)
            
        # 2. 生成全量哈希候选 (包含 _f 等变体)
        # 注意：_resolve_events_for_text_key 已经处理了 nvzhu vs nanzhu
        # 这里我们需要处理的是 wwise hash 层面的变体 (WutheringAudioStrategy.build_names)
        
        total_candidates: list[tuple[str, int]] = []
        seen = set()

        # 辅助函数：添加候选
        def add_cand(n):
            if n not in seen:
                h = self.strategy.hash_name(n)
                total_candidates.append((n, h))
                seen.add(n)

        # A. 从已知 Events 生成
        for ev in events:
            for name in self.strategy.build_names(text_key, ev):
                add_cand(name)
                
        # B. 从 Index 补充 (Fuzzy match around text_key)
        if self.voice_event_index:
             seed = events[0] if events else None
             for name in self.voice_event_index.find_candidates(text_key, seed, limit=8):
                 add_cand(name)
                 
        # C. 兜底猜测
        if not total_candidates:
            for name in self.strategy.build_names(text_key, None):
                add_cand(name)
                
        if not total_candidates:
            return None

        # 3. 二次性别过滤 (Double Check)
        # 虽然 Step 1 已经排过序，但 Step 2 生成的变体可能引入杂音
        # 我们再次对所有生成的 name 进行权重排序
        pref = (self.config.gender_preference or "female").lower()
        f_pats = ["_f_", "nvzhu", "roverf", "_female"]
        m_pats = ["_m_", "nanzhu", "roverm", "_male"]
        target_pats = f_pats if pref == "female" else m_pats
        other_pats = m_pats if pref == "female" else f_pats

        def priority(item):
            name = item[0].lower()
            if any(w in name for w in target_pats): return 0
            if any(w in name for w in other_pats): return 2
            return 1
            
        total_candidates.sort(key=priority)
        
        # 4. 物理文件检查
        # 只有当文件真的存在(或可提取)时，我们才返回这个哈希
        index = self.audio_index
        wem_root = self.config.audio_wem_root
        bnk_root = self.config.audio_bnk_root
        
        for name, h in total_candidates:
            # Cache
            if index and index.find(h):
                return AudioResolution(h, name, 'cache')
            # WEM
            if wem_root and find_wem_by_hash(wem_root, h):
                return AudioResolution(h, name, 'wem')
            # BNK
            if bnk_root and find_bnk_for_event(bnk_root, name):
                return AudioResolution(h, name, 'bnk')
                
        # 5. 如果都没有，仅在有明确候选时返回最高优先级的哈希 (Blind Guess)
        # 这允许 Player 尝试去下载或进一步处理
        if total_candidates:
            best = total_candidates[0]
            return AudioResolution(best[1], best[0], 'unknown')
            
        return None
