#!/usr/bin/env python
"""临时脚本：插入修复代码"""

file_path = "src/ludiglot/ui/overlay_window.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到插入点（第1007行之后）
insert_line = 1007  # 0-indexed is 1006

# 要插入的代码
insert_code = """
                # 关键修复：检查匹配到的key长度，避免长文本匹配到短语
                matched_key = str(rest_result.get("_matched_key", ""))
                rest_key_len = len(rest_key)
                matched_key_len = len(matched_key)
                
                # 如果查询很长(>100字符)但匹配到很短的key(<50字符)，这可能是错误匹配
                if rest_key_len > 100 and matched_key_len < 50:
                    # 尝试在数据库中查找长度更接近的匹配
                    self.signals.log.emit(
                        f"[MATCH] 长度差异过大：query_len={rest_key_len}, matched_len={matched_key_len}，寻找更好的匹配"
                    )
                    # 查找长度在合理范围内的候选(50%-150%)
                    min_len = int(rest_key_len * 0.5)
                    max_len = int(rest_key_len * 1.5)
                    better_candidates = [k for k in self.db.keys() if min_len <= len(k) <= max_len]
                    
                    if better_candidates:
                        # 在这些候选中重新搜索
                        try:
                            from rapidfuzz import process, fuzz
                            hit = process.extractOne(rest_key, better_candidates, scorer=fuzz.token_set_ratio)
                            if hit and hit[1] >= 60:  # 降低阈值，因为长文本匹配更难
                                better_key = str(hit[0])
                                better_score = float(hit[1]) / 100.0
                                if better_score >= 0.6:  # 只要有合理匹配就使用
                                    rest_result = dict(self.db.get(better_key, {}))
                                    rest_result["_matched_key"] = better_key
                                    rest_score = better_score
                                    self.signals.log.emit(
                                        f"[MATCH] 找到更好的匹配：new_key_len={len(better_key)}, score={better_score:.3f}"
                                    )
                        except Exception as e:
                            self.signals.log.emit(f"[MATCH] 重新搜索失败: {e}")
"""

# 在第1008行之前插入（在空行之后，"# 优先使用"之前）
lines.insert(insert_line, insert_code + "\n")

# 修改第1023行的阈值(原来是1022，插入后变成1022+33=1055附近)
# 找到 "if rest_score >= 0.85" 这一行
for i, line in enumerate(lines):
    if i > 1000 and "if rest_score >= 0.85 and len(rest_text.split()) >= 5:" in line:
        lines[i] = line.replace("rest_score >= 0.85", "rest_score >= 0.6")
        print(f"✓ 修改第{i+1}行的阈值: 0.85 -> 0.6")
        break

# 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print(f"✓ 修复代码已插入到 {file_path}")
print(f"✓ 插入位置: 第{insert_line+1}行")
print(f"✓ 插入了 {len(insert_code.strip().split(chr(10)))} 行代码")
