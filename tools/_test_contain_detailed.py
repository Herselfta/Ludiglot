import json

db = json.load(open('E:/Ludiglot/game_text_db.json', encoding='utf-8'))

# 自测脚本中的实际查询（152字符）
test_key = 'performupto4consecutiveattackseachattackdealingphysicaldamagetothetargetthelastattacktriggersabasicdodgecounterwhenhitalsorestores5concertoenergyeachhit'

print(f"查询长度: {len(test_key)}")
print(f"查询内容: {test_key}\n")

# 测试包含匹配
print("=== 测试1: 数据库key包含查询 ===")
contain_hits = [k for k in db.keys() if test_key in k]
print(f"结果数量: {len(contain_hits)}")
if contain_hits:
    best = min(contain_hits, key=len)
    print(f"最短包含项长度: {len(best)}")
    print(f"Key前200字符: {best[:200]}")
else:
    print("❌ 没有找到！")

print("\n=== 测试2: 查询包含数据库key（前缀匹配）===")
prefix_hits = [k for k in db.keys() if k.startswith(test_key)]
print(f"结果数量: {len(prefix_hits)}")

print("\n=== 测试3: 数据库key是否以查询开始（反向前缀） ===")
reverse_prefix = [k for k in db.keys() if test_key.startswith(k) and len(k) >= 50]
print(f"结果数量: {len(reverse_prefix)}")
if reverse_prefix:
    longest = max(reverse_prefix, key=len)
    print(f"最长匹配key长度: {len(longest)}")
    print(f"Key: {longest}")

print("\n=== 测试4: 模糊token匹配（查找相似的605字符key） ===")
target_len = 605
similar_keys = [k for k in db.keys() if abs(len(k) - target_len) < 100 and 'performupto4consecutive' in k]
print(f"长度在505-705且包含关键词的key数量: {len(similar_keys)}")
if similar_keys:
    for k in similar_keys[:2]:
        print(f"  - 长度={len(k)}, 前150字符={k[:150]}...")
