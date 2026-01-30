from __future__ import annotations
import re
import time
from typing import Any, Dict, List, Tuple, Optional
from ludiglot.core.search import FuzzySearcher
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

    def __init__(self, db: Dict[str, Any], voice_map: Dict[str, Any] = None, voice_event_index: VoiceEventIndex = None):
        self.db = db
        self.voice_map = voice_map or {}
        self.voice_event_index = voice_event_index
        self.searcher = FuzzySearcher()
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
        self.log_callback = None

    def set_logger(self, callback):
        self.log_callback = callback

    def log(self, msg: str):
        if self.log_callback:
            self.log_callback(msg)

    def match(self, lines: List[Tuple[str, float]]) -> Dict[str, Any] | None:
        """Main entry point: find best DB entry for OCR lines."""
        return self._lookup_best(lines)

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
        # 1. 直接匹配
        if key in self.db:
            result = dict(self.db[key])
            result["_matched_key"] = key
            return result, 1.0

        # 1.5 子串匹配优化
        if len(key) >= 10:
            # 前缀匹配
            prefix_hits = [k for k in self.db.keys() if k.startswith(key)]
            if prefix_hits:
                best_prefix = min(prefix_hits, key=len)
                result = dict(self.db.get(best_prefix, {}))
                result["_matched_key"] = best_prefix
                return result, 0.99
            
            # 包含匹配 (OCR 包含库项)
            contain_in_ocr = [k for k in self.db.keys() if len(k) >= 10 and k in key]
            if contain_in_ocr:
                best_k = max(contain_in_ocr, key=len)
                length_ratio = len(best_k) / len(key)
                
                # 只有在覆盖度极高时才直接返回 0.95
                if length_ratio >= 0.85:
                    result = dict(self.db.get(best_k, {}))
                    result["_matched_key"] = best_k
                    self.log(f"[MATCH] 高覆盖子串匹配：ratio={length_ratio:.2f}")
                    return result, 0.95
                elif length_ratio >= 0.6:
                    # 中等覆盖度，记录但允许继续搜索（由后方的模糊搜索兜底，或者直接降低分值）
                    self.log(f"[MATCH] 中覆盖子串匹配：ratio={length_ratio:.2f}，降低分值以待进一步匹配")
                    # 这里先不返回，让它进入后的逻辑，或者返回一个较低的基础分
                else:
                    self.log(f"[MATCH] 跳过低覆盖子串匹配：ratio={length_ratio:.2f}")

            # 被包含匹配 (库项包含 OCR)
            if len(key) >= 50:
                contain_hits = [k for k in self.db.keys() if key in k]
                if contain_hits:
                    best_contain = min(contain_hits, key=len)
                    if len(best_contain) <= len(key) * 3:
                        result = dict(self.db.get(best_contain, {}))
                        result["_matched_key"] = best_contain
                        self.log(f"[MATCH] 部分截屏匹配成功：query_len={len(key)}, matched_len={len(best_contain)}")
                        return result, 0.98

            # 松散匹配
            if len(key) >= 100 and fuzz:
                min_len = int(len(key) * 0.7)
                max_len = int(len(key) * 5.0)
                anchor = key[50:100] if len(key) >= 100 else key[:50]
                candidates = [k for k in self.db.keys() if min_len <= len(k) <= max_len and anchor in k]
                
                self.log(f"[MATCH] 松散匹配：query_len={len(key)}, 候选数量={len(candidates)}")
                if candidates:
                    best_loose = max(candidates, key=lambda k: fuzz.token_set_ratio(key, k))
                    similarity = fuzz.token_set_ratio(key, best_loose) / 100.0
                    self.log(f"[MATCH] 最佳候选：key_len={len(best_loose)}, similarity={similarity:.3f}")
                    if similarity >= 0.45:
                        result = dict(self.db.get(best_loose, {}))
                        result["_matched_key"] = best_loose
                        return result, similarity

        # 2. 短查询精确匹配
        key_len = len(key)
        if key_len < 20 and fuzz:
            min_len = int(key_len * 0.6)
            max_len = int(key_len * 1.4)
            candidates = [k for k in self.db.keys() if min_len <= len(k) <= max_len]
            if candidates:
                hit = process.extractOne(key, candidates, scorer=fuzz.ratio)
                if hit:
                    best_item, score_val, _ = hit
                    score = score_val / 100.0
                    if score >= 0.85:
                        result = dict(self.db.get(str(best_item), {}))
                        result["_matched_key"] = str(best_item)
                        self.log(f"[MATCH] 短查询精确匹配：query_len={key_len}, matched_len={len(best_item)}, score={score:.3f}")
                        return result, score

        # 3. 常规模糊搜索
        best, score = self.searcher.search(key, self.db.keys())
        result = dict(self.db.get(best, {}))
        result["_matched_key"] = best
        return result, score

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
            # Construct multi result
            self.log(f"[MATCH] 检测到 {len(multi_items)} 个独立条目")
            items = []
            for line in multi_items:
                matches = line['result'].get("matches")
                match = matches[0] if matches else {}
                official_en = match.get("official_en") or ""
                official_cn = match.get("official_cn") or ""
                time_suffix = line.get('time_suffix')
                if time_suffix:
                    official_en = f"{official_en} {time_suffix}" if official_en and not official_en.rstrip().endswith(':') else f"{official_en}: {time_suffix}" if official_en else ""
                    official_cn = f"{official_cn} {time_suffix}" if official_cn and not official_cn.rstrip().endswith('：') else f"{official_cn}：{time_suffix}" if official_cn else ""
                
                items.append({
                    "ocr": line['cleaned'],
                    "query_key": line['key'],
                    "score": round(line['score'], 3),
                    "text_key": match.get("text_key"),
                    "official_en": official_en,
                    "official_cn": official_cn,
                })
            return {
                "_multi": True, "items": items,
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
                
                if rest_score >= 0.5 and len(rest_text.split()) >= 5:
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

        # Smart Candidates
        smart_result = build_smart_candidates(lines)
        candidates = smart_result.get('candidates', [])
        strategy = smart_result.get('strategy', 'unknown')
        self.log(f"[SEARCH] 智能匹配策略={strategy}, 评估 {len(candidates)} 个候选...")

        start_time = time.time()
        for text, conf in candidates:
             if best_score > 0.96 and len(best_text.split()) > 5: break
             
             key = normalize_en(text)
             if not key: continue

             # Filter short garbage
             if (context_words and len(context_words) >= 6) or (context_len >= 40):
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
                     weighted_score *= 0.2
                     self.log(f"[MATCH] 长查询匹配短条目惩罚: score={weighted_score:.3f}")
                 elif length_diff > 15 and length_ratio < 0.6:
                     weighted_score *= 0.4
                 elif key_len > matched_len * 2:
                     weighted_score *= 0.5
                 elif key_len > matched_len * 1.5 and score < 0.97:
                     weighted_score *= 0.75
            
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
                 if score > 0.8: 
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
            if best_score < 0.35:
                self.log(f"[SEARCH] 耗时: {elapsed:.2f}s, 最佳匹配权重过低 ({best_score:.3f}), 丢弃结果")
                return None
            
            self.log(f"[SEARCH] 耗时: {elapsed:.2f}s, 最佳匹配: {best_result.get('_query_key')} (score={best_result.get('_score')}, weighted={best_score:.3f})")
        else:
            self.log(f"[SEARCH] 耗时: {elapsed:.2f}s, 未找到合适匹配")
        
        return best_result
