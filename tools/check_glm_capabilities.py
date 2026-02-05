#!/usr/bin/env python3
"""检查 GLM-OCR 模型支持的优化选项"""

import os
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))

# 禁用 torch.compile 以加快测试
os.environ['LUDIGLOT_GLM_COMPILE'] = '0'

import torch
from ludiglot.core.ocr import OCREngine


def check_model_capabilities():
    print("=" * 50)
    print("GLM-OCR 模型能力检查")
    print("=" * 50)
    
    # PyTorch 版本信息
    print(f"\nPyTorch 版本: {torch.__version__}")
    print(f"CUDA 可用: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"CUDA 版本: {torch.version.cuda}")
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    
    # SDPA 支持
    has_sdpa = hasattr(torch.nn.functional, "scaled_dot_product_attention")
    print(f"\nSDPA 支持: {has_sdpa}")
    
    # Flash Attention 支持
    if has_sdpa and torch.cuda.is_available():
        try:
            print(f"Flash SDP 可用: {torch.backends.cuda.flash_sdp_enabled()}")
            print(f"Memory Efficient SDP 可用: {torch.backends.cuda.mem_efficient_sdp_enabled()}")
            print(f"Math SDP 可用: {torch.backends.cuda.math_sdp_enabled()}")
        except Exception as e:
            print(f"SDP 后端检查失败: {e}")
    
    # 加载模型
    print("\n加载 GLM-OCR 模型...")
    engine = OCREngine(mode='auto')
    engine._init_glm_local()
    
    if engine._glm_model_obj is None:
        print("模型加载失败")
        return
    
    model = engine._glm_model_obj
    print(f"\n模型类型: {type(model).__name__}")
    
    # 检查配置
    if hasattr(model, 'config'):
        config = model.config
        print(f"配置类型: {type(config).__name__}")
        
        if hasattr(config, '_attn_implementation'):
            print(f"Attention 实现: {config._attn_implementation}")
        
        if hasattr(config, 'hidden_size'):
            print(f"隐藏层大小: {config.hidden_size}")
        
        if hasattr(config, 'num_attention_heads'):
            print(f"注意力头数: {config.num_attention_heads}")
        
        if hasattr(config, 'vocab_size'):
            print(f"词表大小: {config.vocab_size}")
    
    # 检查模型层
    print("\n模型结构概览:")
    for name, module in model.named_children():
        print(f"  - {name}: {type(module).__name__}")
    
    # 内存使用
    if torch.cuda.is_available():
        print(f"\nGPU 内存使用: {torch.cuda.memory_allocated() / 1024**2:.1f} MB")
        print(f"GPU 内存缓存: {torch.cuda.memory_reserved() / 1024**2:.1f} MB")
    
    # Triton 检查
    print("\nTriton 检查:")
    try:
        import triton
        print(f"  Triton 版本: {triton.__version__}")
    except ImportError:
        print("  Triton 未安装")
    except Exception as e:
        print(f"  Triton 检查失败: {e}")


if __name__ == "__main__":
    check_model_capabilities()
