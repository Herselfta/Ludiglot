"""测试HTML转换功能"""
import re

def convert_game_html(text: str) -> str:
    """将游戏的自定义HTML标记转换为标准HTML格式。
    
    游戏格式: <color=#RRGGBB>文本</color>
    标准HTML: <span style="color: #RRGGBB">文本</span>
    """
    # 替换 <color=#RRGGBB>...</color> 为 <span style="color: #RRGGBB">...</span>
    text = re.sub(
        r'<color=(#[0-9a-fA-F]{6})>(.*?)</color>',
        r'<span style="color: \1">\2</span>',
        text
    )
    
    # 保留换行符
    text = text.replace('\n', '<br>')
    
    return text

# 测试用例
test_cases = [
    "<color=#59b4d3>3阶</color>",
    "触发协奏作用时，若两个角色的属性类型同为<color=#7e1f57>解离</color>，则触发<color=#8c7e51>解离齐奏</color>，对目标造成<color=#7e1f57>解离</color>伤害。",
    "全队造成的属性伤害提升<color=#8c7e51>20%</color>，持续<color=#8c7e51>12</color>秒。",
]

print("=" * 80)
print("HTML 转换测试")
print("=" * 80)

for i, test in enumerate(test_cases, 1):
    print(f"\n测试 {i}:")
    print(f"原始: {test}")
    converted = convert_game_html(test)
    print(f"转换: {converted}")
    print()
