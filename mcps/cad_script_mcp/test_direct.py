#!/usr/bin/env python3
"""
直接测试 run_scripts 模块 - 不经过 HTTP/MCP
这样可以快速定位问题
"""

import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from run_scripts import run_scripts, InitEnv

def test_init():
    """测试初始化"""
    print("=" * 50)
    print("测试初始化...")
    print("=" * 50)

    env = InitEnv()
    ncti, yh = env.init_all()

    print(f"NCTI: {ncti}")
    print(f"YH: {yh}")

    if ncti:
        print(f"NCTI.Document: {ncti.Document}")

    if yh:
        print(f"YH 模块属性：{dir(yh)}")
        print(f"SketchWorkPlane 存在：{hasattr(yh, 'SketchWorkPlane')}")

def test_simple():
    """测试最简单的脚本"""
    print("\n" + "=" * 50)
    print("测试最简单脚本...")
    print("=" * 50)

    scripts = [
        {
            "script_type": "python",
            "script_content": "print('Hello!')",
            "should_execute": True
        }
    ]

    result = run_scripts(scripts, "debug/simple.yha")
    print(f"结果：{json.dumps(result, indent=2, ensure_ascii=False)}")

def test_doc_only():
    """测试只使用 NCTI doc"""
    print("\n" + "=" * 50)
    print("测试只使用 NCTI doc...")
    print("=" * 50)

    # 只用 NCTI 的 API，不用 YH
    scripts = [
        {
            "script_type": "python",
            "script_content": """
print(f"doc: {doc}")
print(f"NCTI: {NCTI}")

# 尝试创建点
point = NCTI.Point(0, 0, 0)
print(f"Point created: {point}")
""",
            "should_execute": True
        }
    ]

    result = run_scripts(scripts, "debug/ncti_test.yha")
    print(f"结果：{json.dumps(result, indent=2, ensure_ascii=False)}")

def test_yh_sketch():
    """测试 YH SketchWorkPlane"""
    print("\n" + "=" * 50)
    print("测试 YH SketchWorkPlane...")
    print("=" * 50)

    scripts = [
        {
            "script_type": "python",
            "script_content": """
print("开始创建 Sketch...")
print(f"doc 类型：{type(doc)}")
print(f"YH 类型：{type(YH)}")

# 尝试创建 Sketch
print("调用 YH.SketchWorkPlane...")
skt = YH.SketchWorkPlane(doc)
print(f"Sketch created: {skt}")
""",
            "should_execute": True
        }
    ]

    result = run_scripts(scripts, "debug/sketch_test.yha")
    print(f"结果：{json.dumps(result, indent=2, ensure_ascii=False)}")

def main():
    print("直接测试 run_scripts 模块")

    # 测试初始化
    test_init()

    # 测试简单脚本
    test_simple()

    # 测试 NCTI doc
    test_doc_only()

    # 测试 YH Sketch
    test_yh_sketch()

    print("\n" + "=" * 50)
    print("所有测试完成")
    print("=" * 50)

if __name__ == "__main__":
    main()
