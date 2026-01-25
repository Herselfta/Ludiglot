import json

db = json.load(open('E:/Ludiglot/game_text_db.json', encoding='utf-8'))

# 测试查询（自测脚本中的408字符查询）
test_key = 'performupto4consecutiveattackseachattackdealingphysicaldamagetothetargetthelastattacktriggersabasicdodgecounterwhenhitalsorestores5concertoenergyeachhit'

print(f"查询长度: {len(test_key)}")

# 检查包含匹配：数据库中哪些key包含test_key
contain_hits = [k for k in db.keys() if test_key in k]
print(f'\n包含匹配结果数量（db_key包含query）: {len(contain_hits)}')
if contain_hits:
    best = min(contain_hits, key=len)
    print(f'最短包含项长度: {len(best)}')
    print(f'CN: {db[best].get("cn", "N/A")[:100]}')
else:
    print('没有找到包含匹配！')
    
# 反向检查：test_key包含哪些数据库key
reverse_hits = [k for k in db.keys() if k in test_key]
print(f'\n反向匹配（query包含db_key）: {len(reverse_hits)}')
if reverse_hits:
    longest = max(reverse_hits, key=len)
    print(f'最长被包含项长度: {len(longest)}')
    print(f'Key: {longest[:100]}...')
    print(f'CN: {db[longest].get("cn", "N/A")[:100]}')
