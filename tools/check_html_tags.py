import json
from pathlib import Path

db_path = Path("E:/Ludiglot/game_text_db.json")
if not db_path.exists():
    db_path = Path("E:/Ludiglot/data/game_text_db.json")
if not db_path.exists():
    db_path = Path("E:/Ludiglot/cache/game_text_db.json")
if not db_path.exists():
    print("数据库文件不存在")
    exit(1)

db = json.load(open(db_path, 'r', encoding='utf-8'))
samples = [(k, v) for k, v in list(db.items())[:1000] if 'matches' in v and v['matches']]
html_samples = []

for k, v in samples:
    for m in v['matches'][:1]:
        cn = m.get('official_cn', '')
        if '<' in cn:
            html_samples.append((k, cn[:200]))

print(f'找到 {len(html_samples)} 个HTML标记条目\n')
for i, (k, cn) in enumerate(html_samples[:10]):
    print(f'{i+1}. {k}:')
    print(f'   {cn}')
    print()
