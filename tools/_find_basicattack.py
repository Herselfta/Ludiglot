import json

db = json.load(open('E:/Ludiglot/game_text_db.json', encoding='utf-8'))

def get_cn(entry):
    """从数据库条目中提取中文翻译"""
    matches = entry.get('matches', [])
    if matches:
        return matches[0].get('official_cn', 'N/A')
    return 'N/A'

# 查找包含 'Basic Attack' 的条目
basic_attack_keys = [k for k in db.keys() if 'basicattack' in k.lower()]
print(f'找到 {len(basic_attack_keys)} 个Basic Attack相关条目\n')

# 显示最长的几个
sorted_keys = sorted(basic_attack_keys, key=len, reverse=True)[:5]
for i, k in enumerate(sorted_keys, 1):
    print(f'{i}. 长度={len(k)}')
    print(f'Key前100字符: {k[:100]}')
    cn_text = get_cn(db[k])
    print(f'CN前100字符: {cn_text[:100]}')
    print()

# 现在查找包含 "performupto4consecutive" 的条目
test_fragment = 'performupto4consecutive'
matching_keys = [k for k in db.keys() if test_fragment in k]
print(f'\n包含"{test_fragment}"的条目: {len(matching_keys)}')
if matching_keys:
    for k in matching_keys[:3]:
        cn = get_cn(db[k])
        print(f'- Key长度={len(k)}, CN前50字符={cn[:50]}...')
