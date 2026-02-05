#!/usr/bin/env python3
"""GLM-OCR 性能测试脚本"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.ocr import OCREngine


def benchmark_glm_ocr(image_path: str, runs: int = 3, detailed: bool = False) -> None:
    """测试 GLM-OCR 性能"""
    print("=" * 50)
    print("GLM-OCR 性能测试")
    print("=" * 50)
    
    # 初始化引擎
    print("\n[1] 初始化 OCREngine...")
    init_start = time.perf_counter()
    engine = OCREngine(mode="auto")
    init_end = time.perf_counter()
    print(f"    OCREngine 初始化耗时: {init_end - init_start:.3f}s")
    
    # 预热 GLM 本地模型
    print("\n[2] 预热 GLM-OCR 本地模型...")
    warmup_start = time.perf_counter()
    success = engine._init_glm_local()
    warmup_end = time.perf_counter()
    print(f"    预热耗时: {warmup_end - warmup_start:.3f}s")
    print(f"    预热成功: {success}")
    
    if not success:
        print(f"    错误: {engine._glm_last_error}")
        return
    
    # 打印模型信息
    print("\n[3] 模型信息:")
    print(f"    设备: {engine._glm_device}")
    print(f"    数据类型: {engine._glm_dtype}")
    print(f"    模型: {engine.glm_local_model}")
    print(f"    编译启用: {engine._glm_compiled}")
    
    # 运行测试
    print(f"\n[4] 运行 {runs} 次识别测试 (图片: {image_path})...")
    times = []
    for i in range(runs):
        start = time.perf_counter()
        result = engine._glm_local_recognize_boxes(image_path)
        end = time.perf_counter()
        elapsed = end - start
        times.append(elapsed)
        
        texts = [r.get("text", "") for r in result] if result else []
        print(f"    第 {i+1} 次: {elapsed:.3f}s")
        if i == 0 and texts:
            print(f"        识别结果: {texts}")
    
    # 统计
    print("\n[5] 统计结果:")
    print(f"    平均耗时: {sum(times) / len(times):.3f}s")
    print(f"    最快: {min(times):.3f}s")
    print(f"    最慢: {max(times):.3f}s")
    # 排除第一次（编译开销），计算平均值
    if len(times) > 1:
        stable_times = times[1:]
        print(f"    稳定平均 (排除首次): {sum(stable_times) / len(stable_times):.3f}s")
    
    # 检查是否有优化机会
    print("\n[6] 优化建议:")
    
    # 检查 torch.compile 支持
    try:
        import torch
        if hasattr(torch, "compile"):
            print("    - torch.compile 可用，可尝试编译加速")
        else:
            print("    - torch.compile 不可用 (需要 PyTorch 2.0+)")
            
        # 检查 bitsandbytes
        try:
            import bitsandbytes
            print("    - bitsandbytes 已安装，4-bit 量化可用")
        except ImportError:
            print("    - bitsandbytes 未安装，无法使用 4-bit 量化")
            
        # 检查 flash attention
        if torch.cuda.is_available():
            print(f"    - CUDA 可用: {torch.cuda.get_device_name(0)}")
        else:
            print("    - CUDA 不可用，仅 CPU 推理")
            
    except ImportError:
        print("    - PyTorch 未安装")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="GLM-OCR 性能测试")
    parser.add_argument("--image", "-i", default="tools/TestOCR.png", help="测试图片路径")
    parser.add_argument("--runs", "-n", type=int, default=3, help="测试次数")
    parser.add_argument("--detailed", "-d", action="store_true", help="显示详细分步耗时")
    
    args = parser.parse_args()
    
    # 转换为绝对路径
    image_path = Path(args.image)
    if not image_path.is_absolute():
        image_path = project_root / image_path
    
    if not image_path.exists():
        print(f"错误: 图片不存在: {image_path}")
        sys.exit(1)
    
    benchmark_glm_ocr(str(image_path), args.runs, args.detailed)
