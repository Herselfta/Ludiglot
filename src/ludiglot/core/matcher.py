from __future__ import annotations
import re
import time
from typing import Any, Dict, List, Tuple, Optional
from ludiglot.core.search import FuzzySearcher
from ludiglot.core.indexed_search import IndexedSearchEngine
from ludiglot.core.text_builder import normalize_en
from ludiglot.core.smart_match import build_smart_candidates
from ludiglot.core.voice_event_index import VoiceEventIndex

try:
    from rapidfuzz import fuzz, process
except Exception:
    fuzz = None
    process = None

class MatchResult:
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @property
    def matched_key(self) -> str:
        return self.data.get("_matched_key", "")

    @property
    def score(self) -> float:
        return self.data.get("_score", 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return self.data


class TextMatcher:
    """Core logic for matching, extracted from OverlayWindow."""

    def __init__(
        self,
        db: Dict[str, Any],
        voice_map: Dict[str, Any] = None,
        voice_event_index: VoiceEventIndex = None,
        gender_preference: str = "female",
    ):
        self.db = db
        self.voice_map = voice_map or {}
        self.voice_event_index = voice_event_index
        self.searcher = FuzzySearcher()
        pref = str(gender_preference or "female").strip().lower()
        self.gender_preference = pref if pref in {"female", "male"} else "female"
        
        # 先初始化 log_callback
        self.log_callback = None
        
        # 别名映射
        self.alias_map = {
            "hp": "mainhp",
            "atk": "mainatk",
            "def": "maindef",
            "energyregen": "mainenergyregen",
            "critrate": "maincritrate",
            "critdmg": "maincritdmg",
            "critdamage": "maincritdmg",
            "critdmgbonus": "maincritdmg",
        }
        
        # 然后初始化索引化搜索引擎（可能调用 log）
        db_keys = list(db.keys())
        self.indexed_searcher = IndexedSearchEngine(db_keys)
        self.log(f"[MATCHER] 索引引擎已初始化 ({len(db_keys)} keys)")

    def set_logger(self, callback):
        self.log_callback = callback

    def log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def _prioritize_protagonist_gender(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """只在主角男女主并存时重排 matches[0]，避免误伤普通语音。"""
        matches = result.get("matches")
        if not isinstance(matches, list) or len(matches) < 2:
            return result

        female_tokens = ("nvzhu", "roverf", "_female")
        male_tokens = ("nanzhu", "roverm", "_male")
        target_tokens = female_tokens if self.gender_preference == "female" else male_tokens
        other_tokens = male_tokens if self.gender_preference == "female" else female_tokens
        protagonist_tokens = female_tokens + male_tokens

        scored: list[tuple[int, int, Any]] = []
        has_target = False
        has_other = False

        for idx, item in enumerate(matches):
            if not isinstance(item, dict):
                scored.append((1, idx, item))
                continue
            hay = f"{item.get('audio_event', '')} {item.get('text_key', '')}".lower()
            has_protagonist = any(tok in hay for tok in protagonist_tokens)
            hit_target = any(tok in hay for tok in target_tokens)
            hit_other = any(tok in hay for tok in other_tokens)
            has_target = has_target or hit_target
            has_other = has_other or hit_other

            if has_protagonist:
                if hit_target and not hit_other:
                    pri = 0
                elif hit_other and not hit_target:
                    pri = 2
                else:
                    pri = 1
            else:
                pri = 1
            scored.append((pri, idx, item))

        # 仅在主角男女两套并存时触发重排
        if not (has_target and has_other):
            result["matches"] = [m.copy() if isinstance(m, dict) else m for m in matches]
            return result

        scored.sort(key=lambda x: (x[0], x[1]))
        reordered = [item for _, _, item in scored]
        result["matches"] = reordered
        top = reordered[0] if reordered else {}
        if isinstance(top, dict):
            self.log(
                f"[MATCH] 主角性别优先: pref={self.gender_preference}, "
                f"text_key={top.get('text_key')}, event={top.get('audio_event')}"
            )
        return result

    def _build_result(self, matched_key: str) -> Dict[str, Any]:
        result = dict(self.db.get(matched_key, {}))
        result["_matched_key"] = matched_key
        return self._prioritize_protagonist_gender(result)

    def match(self, lines: List[Tuple[str, float]]) -> Dict[str, Any] | None:
        """Main entry point: find best DB entry for OCR lines."""
        start = time.time()
        result = self._lookup_best(lines)
        elapsed = time.time() - start
        
        # 性能监控日志
        if elapsed > 1.0:
            self.log(f"[PERF] match() 耗时较长: {elapsed:.2f}s")
        
        # 缓存统计
        cache_stats = self.indexed_searcher.get_cache_stats()
        hit_rate = cache_stats['hits'] / max(cache_stats['hits'] + cache_stats['misses'], 1) * 100
        if cache_stats['hits'] + cache_stats['misses'] > 100:
            self.log(f"[CACHE] 命中率: {hit_rate:.1f}% (hits={cache_stats['hits']}, misses={cache_stats['misses']})")
        
        return result

    def _clean_ocr_line(self, text: str) -> str:
        # 去掉图标/分隔符噪声，保留字母数字与空格
        cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
        cleaned = " ".join(cleaned.split())
        return cleaned.strip()

    def _has_voice_match(self, result: dict) -> bool:
        """检查匹配结果是否有对应的语音文件。"""
        if not isinstance(result, dict):
            return False
        matches = result.get('matches', [])
        if not matches:
            return False
        text_key = matches[0].get('text_key', '')
        if not text_key:
            return False
        # 检查语音映射或缓存
        event_name = f"vo_{text_key}"
        if self.voice_map and event_name in self.voice_map:
            return True
        if self.voice_event_index:
            events = self.voice_event_index.find_candidates(text_key=text_key, voice_event=event_name, limit=1)
            if events:
                return True
        return False
    
    def _is_list_mode(self, lines: list[tuple[str, float]]) -> bool:
        if len(lines) < 4:
            return False
        cleaned = [self._clean_ocr_line(text) for text, _ in lines if text]
        cleaned = [c for c in cleaned if c]
        filtered = []
        for c in cleaned:
            if not c: continue
            if len(c.split()) > 3 or len(c) > 20: continue
            digit_ratio = sum(ch.isdigit() for ch in c) / max(len(c), 1)
            if digit_ratio > 0.4: continue
            filtered.append(c)
        if len(filtered) < 3: return False
        lengths = [len(c) for c in filtered]
        max_len = max(lengths)
        avg_words = sum(len(c.split()) for c in filtered) / max(len(filtered), 1)
        return max_len <= 16 and avg_words <= 2.2

    def search_key(self, key: str) -> tuple[Dict[str, Any], float]:
        """
        高性能搜索实现 - 使用索引化搜索引擎
        
        优化策略：
        1. 精确匹配
        2. 前缀匹配
        3. 子串匹配（包含关系）
        4. 模糊搜索（使用长度预筛选）
        """
        # 1. 精确匹配（最快）
        if self.indexed_searcher.exact_match(key):
            result = self._build_result(key)
            return result, 1.0

        key_len = len(key)
        
        # 2. 前缀匹配（针对长查询）
        if key_len >= 10:
            prefix_hits = self.indexed_searcher.prefix_search(key, max_results=1)
            if prefix_hits:
                best_prefix = prefix_hits[0]
                result = self._build_result(best_prefix)
                return result, 0.99
        
        # 3. 子串匹配优化
        if key_len >= 10:
            # 查找包含query的键（OCR包含库项的情况）
            contain_in_ocr = self.indexed_searcher.substring_search(key, direction='in')
            if contain_in_ocr:
                # 选择最长的匹配（最具体）
                best_k = max(contain_in_ocr, key=len)
                length_ratio = len(best_k) / len(key)
                
                if length_ratio >= 0.82: # Revert to safer high
                    result = self._build_result(best_k)
                    self.log(f"[MATCH] 高覆盖子串匹配：ratio={length_ratio:.2f}")
                    return result, 0.95
                elif length_ratio >= 0.6: # Revert to safer medium
                    # 中等覆盖度，记录但继续搜索
                    self.log(f"[MATCH] 中覆盖子串匹配：ratio={length_ratio:.2f}，继续搜索更优匹配")
            
            # 查找被query包含的键（库项包含OCR的情况）
            if key_len >= 50:
                contained_keys = self.indexed_searcher.substring_search(key, direction='contains')
                if contained_keys:
                    best_contain = min(contained_keys, key=len)
                    
                    # BUG FIX: Ensure the matched key is substantial enough to represent the query
                    # If direction='contains' means "DB Key is in Query" (which seems to be the case based on logs),
                    # we must ensure we aren't matching a tiny generic word inside a long sentence.
                    if len(best_contain) > key_len * 0.7 or (len(best_contain) >= 20 and len(best_contain) > key_len * 0.4):
                        if len(best_contain) <= key_len * 3: # Keep original safety check
                            result = self._build_result(best_contain)
                            self.log(f"[MATCH] 部分截屏匹配成功：query_len={key_len}, matched_len={len(best_contain)}")
                            return result, 0.98
        
        # 4. 短查询精确匹配（严格相似度）
        if key_len < 20:
            fuzzy_results = self.indexed_searcher.fuzzy_search(key, top_k=1, score_threshold=0.85)
            if fuzzy_results:
                best_item, score = fuzzy_results[0]
                result = self._build_result(best_item)
                self.log(f"[MATCH] 短查询精确匹配：query_len={key_len}, matched_len={len(best_item)}, score={score:.3f}")
                return result, score
        
        # 5. 常规模糊搜索（使用索引加速）
        fuzzy_results = self.indexed_searcher.fuzzy_search(key, top_k=3, score_threshold=0.4)
        if fuzzy_results:
            best_item, score = fuzzy_results[0]
            result = self._build_result(best_item)
            return result, score
        
        # 6. 未找到任何匹配
        return {}, 0.0

    def _lookup_best(self, lines: list[tuple[str, float]]) -> Dict[str, Any] | None:
        best_result: Dict[str, Any] | None = None
        best_score = -1.0
        best_text = ""
        best_conf = 0.0

        context_text = " ".join(self._clean_ocr_line(text) for text, _ in lines if text)
        context_words = [w for w in context_text.split() if w]
        context_len = len(normalize_en(context_text))

        line_info: list[dict] = []
        for idx, (text, conf) in enumerate(lines):
            cleaned = self._clean_ocr_line(text)
            if not cleaned: continue
            key = normalize_en(cleaned)
            if not key: continue
            key = self.alias_map.get(key, key)
            result, score = self.search_key(key)
            
            word_count = len(cleaned.split())
            is_short = word_count <= 3 and len(cleaned) <= 20
            is_title_like = is_short and not any(ch in cleaned for ch in [',', '.', '!', '?'])
            
            line_info.append({
                'idx': idx, 'text': text, 'cleaned': cleaned, 'key': key,
                'conf': conf, 'score': score, 'result': result,
                'is_title_like': is_title_like, 'score_val': score # cache score
            })

        if not line_info: return None
        
        # 0. 尝试全量文本合并匹配 (针对长句被OCR拆分的情况)
        full_text_key = normalize_en(context_text)
        if full_text_key and len(full_text_key) > 30:
             # Try substring first for safety
             full_res, full_score = self.search_key(full_text_key)
             # Relaxed threshold for long text blocks
             if full_score > 0.5: 
                 self.log(f"[MATCH] 完整文本块匹配成功: score={full_score:.3f}")
                 return full_res
        
        # --- Multiline Checks (from original code) ---
        multi_items = []
        for line in line_info:
            cleaned = line['cleaned']
            # Time format check
            if re.match(r'^\d+[dhms](\s+\d+[dhms])*$', cleaned.lower().strip()):
                 if multi_items: multi_items[-1]['time_suffix'] = cleaned
                 continue
            if sum(ch.isdigit() for ch in cleaned) / max(len(cleaned), 1) > 0.8: continue

            # Quality check
            matched_key = line['result'].get('_matched_key', '')
            key_len = len(line['key'])
            matched_len = len(matched_key)
            
            special_char_count = len(re.findall(r'[^\w\s\-]', cleaned))
            has_special_pollution = (special_char_count / max(len(cleaned), 1)) > 0.15

            is_high_score = line['score'] >= 0.75 and not has_special_pollution
            is_length_match = matched_len >= key_len * 0.5 and matched_len <= key_len * 2.0
            is_long_text = key_len > 50 and line['score'] >= 0.60
            is_short_text_strict = key_len < 15 and line['score'] >= 0.85
            is_good_match = is_high_score or (is_length_match and line['score'] >= 0.55) or is_long_text or is_short_text_strict
            
            if has_special_pollution and line['score'] < 0.85: continue

            if is_good_match:
                multi_items.append(line)
                self.log(f"[FILTER] 保留条目: {cleaned} (score={line['score']:.3f}, len={key_len})")
        
        if len(multi_items) >= 3:
            # 去重：合并匹配到同一个 text_key 的多个 OCR 行
            text_key_map = {}  # text_key -> list of line info
            for line in multi_items:
                matches = line['result'].get("matches")
                match = matches[0] if matches else {}
                text_key = match.get("text_key")
                if not text_key:
                    continue
                if text_key not in text_key_map:
                    text_key_map[text_key] = []
                text_key_map[text_key].append(line)
            
            # 构建去重后的条目列表
            self.log(f"[MATCH] 检测到 {len(multi_items)} 个匹配，去重后 {len(text_key_map)} 个独立条目")
            
            # 如果去重后只剩1-2个条目，说明是同一条长文本被OCR拆分了
            if len(text_key_map) <= 2:
                # 合并为单条目处理
                merged_lines = []
                for text_key, lines in text_key_map.items():
                    # 合并所有OCR文本
                    merged_ocr = " ".join(l['cleaned'] for l in lines)
                    merged_key = normalize_en(merged_ocr)
                    # 使用第一个匹配结果（它们都指向同一个条目）
                    first_line = lines[0]
                    merged_lines.append({
                        'cleaned': merged_ocr,
                        'key': merged_key,
                        'score': max(l['score'] for l in lines),  # 使用最高分
                        'result': first_line['result'],
                        'conf': max(l['conf'] for l in lines),
                    })
                
                # 如果只有一个条目，返回单条目结果
                if len(merged_lines) == 1:
                    line = merged_lines[0]
                    self.log(f"[MATCH] OCR拆分检测：多行匹配同一条目，合并为单条目")
                    result = line['result']
                    result['_score'] = round(line['score'], 3)
                    result['_query_key'] = line['key']
                    result['_ocr_text'] = line['cleaned']
                    return result
            
            # 构建多条目结果
            items = []
            has_high_confidence_audio = False
            
            for text_key, lines in text_key_map.items():
                # 合并同一条目的多个OCR行
                merged_ocr = " ".join(l['cleaned'] for l in lines)
                merged_key = normalize_en(merged_ocr)
                max_score = max(l['score'] for l in lines)
                
                first_line = lines[0]
                matches = first_line['result'].get("matches")
                match = matches[0] if matches else {}
                official_en = match.get("official_en") or ""
                official_cn = match.get("official_cn") or ""
                
                # 处理时间后缀
                time_suffix = first_line.get('time_suffix')
                if time_suffix:
                    official_en = f"{official_en} {time_suffix}" if official_en and not official_en.rstrip().endswith(':') else f"{official_en}: {time_suffix}" if official_en else ""
                    official_cn = f"{official_cn} {time_suffix}" if official_cn and not official_cn.rstrip().endswith('：') else f"{official_cn}：{time_suffix}" if official_cn else ""
                
                # 检测是否有高置信度音频
                if max_score >= 0.85 and self._has_voice_match(first_line['result']):
                    has_high_confidence_audio = True
                
                items.append({
                    "ocr": merged_ocr,
                    "query_key": merged_key,
                    "score": round(max_score, 3),
                    "text_key": text_key,
                    "official_en": official_en,
                    "official_cn": official_cn,
                })
            
            return {
                "_multi": True, 
                "items": items,
                "_has_audio": has_high_confidence_audio,  # 新增标记
                "_official_en": " / ".join([i.get("official_en") or i.get("ocr") or "" for i in items if i.get("official_en") or i.get("ocr")]),
                "_official_cn": " / ".join([i.get("official_cn") or "" for i in items if i.get("official_cn")]),
                "_query_key": " / ".join([i["query_key"] for i in items if i.get("query_key")]),
                "_ocr_text": " / ".join([i["ocr"] for i in items if i.get("ocr")]),
            }

        # Mixed Content Check
        if len(line_info) >= 2 and len(multi_items) < 3:
            first_line = line_info[0]
            rest_lines = line_info[1:]
            if first_line['is_title_like']:
                rest_text = " ".join(l['cleaned'] for l in rest_lines)
                rest_key = normalize_en(rest_text)
                rest_result, rest_score = self.search_key(rest_key)
                
                rest_word_count = len(rest_text.split())
                if rest_score >= 0.5 and rest_word_count >= 3:
                    rest_has_voice = self._has_voice_match(rest_result)
                    first_has_voice = self._has_voice_match(first_line['result'])
                    matched_key = rest_result.get('_matched_key', '')
                    is_good_match = len(matched_key) >= len(rest_key) * 0.6
                    
                    if is_good_match and (len(rest_key) > 100 or rest_has_voice or (not first_has_voice and rest_score > first_line['score'])):
                         self.log(f"[MATCH] 混合内容策略生效")
                         rest_result['_score'] = round(rest_score, 3)
                         rest_result['_query_key'] = rest_key
                         rest_result['_ocr_text'] = rest_text
                         rest_result['_first_line'] = first_line['cleaned']
                         return rest_result

        # List Mode Check (Original logic copied)
        line_scores = [(l['cleaned'], l['score'], l['result']) for l in line_info]
        if self._is_list_mode(lines) and line_scores:
            strong_lines = [(c, s, r) for c, s, r in line_scores if s >= 0.9] # Simplified check
            if len(strong_lines) >= 3:
                 # Return list
                 items = []
                 for cleaned, score, result in strong_lines:
                     matches = result.get("matches")
                     match = matches[0] if matches else {}
                     items.append({"ocr": cleaned, "query_key": normalize_en(cleaned), "score": round(score, 3), "text_key": match.get("text_key"), "official_cn": match.get("official_cn")})
                 return {"_multi": True, "items": items, "_query_key": "list", "_ocr_text": "list"}

        # Single-line high-confidence fast path:
        # 避免短剧情句在 smart-candidate 的后置过滤阶段被误丢弃。
        if len(line_info) == 1:
            line = line_info[0]
            matched_key = line['result'].get('_matched_key', '')
            key_len = len(line['key'])
            matched_len = len(matched_key)
            if (
                line['score'] >= 0.95
                and key_len >= 12
                and matched_len >= max(10, int(key_len * 0.75))
                and matched_len <= key_len * 2
            ):
                self.log(f"[MATCH] 单行高置信快速命中: score={line['score']:.3f}, len={key_len}")
                result = line['result']
                result['_score'] = round(line['score'], 3)
                result['_query_key'] = line['key']
                result['_ocr_text'] = line['cleaned']
                result['_ocr_conf'] = round(float(line.get('conf', 0.0)), 3)
                result['_weighted'] = round(float(line['score']), 3)
                return result

        # Smart Candidates
        smart_result = build_smart_candidates(lines)
        candidates = smart_result.get('candidates', [])
        strategy = smart_result.get('strategy', 'unknown')
        self.log(f"[SEARCH] 智能匹配策略={strategy}, 评估 {len(candidates)} 个候选...")

        start_time = time.time()
        
        # 优化：减少候选数量，优先处理高质量候选
        max_candidates = 5 if len(candidates) > 10 else len(candidates)
        
        for idx, (text, conf) in enumerate(candidates[:max_candidates]):
             # 早期退出：如果已经找到高质量匹配，停止搜索
             if best_score > 0.96 and len(best_text.split()) > 5:
                 self.log(f"[SEARCH] 早期退出：已找到高质量匹配 (score={best_score:.3f})")
                 break
             
             key = normalize_en(text)
             if not key: continue

             # Filter short garbage
             # 仅在长上下文中启用，避免误杀“短但完整”的剧情句。
             if context_len >= 40:
                 if len(text.split()) <= 3: continue
                 if len(key) < 20: continue

             result, score = self.search_key(key)
             matched_key = result.get("_matched_key", "")
             
             word_count = max(len(text.split()), 1)
             length_bonus = min(len(key) / 100.0, 1.0)
             word_bonus = min(word_count / 8.0, 1.0)
             weighted_score = score * (0.6 + 0.2 * length_bonus + 0.2 * word_bonus)
             
             # Penalties
             if matched_key:
                 key_len = len(key)
                 matched_len = len(matched_key)
                 length_diff = abs(key_len - matched_len)
                 length_ratio = matched_len / max(key_len, 1)

                 if key_len > 25 and matched_len < 20:
                     weighted_score *= 0.4 # Relaxed from 0.2
                     self.log(f"[MATCH] 长查询匹配短条目惩罚: score={weighted_score:.3f}")
                 elif length_diff > 15 and length_ratio < 0.6:
                     weighted_score *= 0.6 # Relaxed from 0.4
                 elif key_len > matched_len * 2:
                     weighted_score *= 0.7 # Relaxed from 0.5
                 elif key_len > matched_len * 1.5 and score < 0.97:
                     weighted_score *= 0.85 # Relaxed from 0.75
            
             # Audio Bonus - Check if match has audio
             matches = result.get("matches", [])
             has_audio = False
             if matches:
                 first_match = matches[0]
                 if first_match.get("audio_hash") or first_match.get("audio_event"):
                     has_audio = True
                 elif self._has_voice_match(result):
                     has_audio = True
            
             if has_audio:
                 # FIX: Only apply audio bonus if the base score is decent
                 if score > 0.65: 
                     weighted_score *= 1.15
                     self.log(f"[MATCH] 语音条目加成: has_audio=True, weighted={weighted_score:.3f}")
                 else:
                     self.log(f"[MATCH] 语音条目忽视: 分数过低 ({score:.3f})")

             if weighted_score > best_score:
                 best_score = weighted_score
                 best_result = result
                 best_text = text
                 best_conf = conf
                 best_result["_score"] = round(score, 3)
                 best_result["_query_key"] = key
                 best_result["_ocr_text"] = best_text
                 best_result["_ocr_conf"] = round(best_conf, 3)
                 best_result["_weighted"] = round(weighted_score, 3)

        elapsed = time.time() - start_time
        if best_result:
            # 修改：增加全局置信度阈值
            if best_score < 0.55:
                self.log(f"[SEARCH] 耗时: {elapsed:.2f}s, 最佳匹配权重过低 ({best_score:.3f}), 丢弃结果")
                return None
            
            self.log(f"[SEARCH] 耗时: {elapsed:.2f}s, 最佳匹配: {best_result.get('_query_key')} (score={best_result.get('_score')}, weighted={best_score:.3f})")
        else:
            self.log(f"[SEARCH] 耗时: {elapsed:.2f}s, 未找到合适匹配")
        
        return best_result
