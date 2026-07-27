#!/usr/bin/env python3
"""本地测试脚本 - 测试 MCP 服务器"""

import requests
import json
import time

# 服务器配置
BASE_URL = "http://localhost:8310"

def test_health():
    """测试健康检查端点"""
    print(f"\n=== 测试健康检查 ===")
    try:
        resp = requests.get(f"{BASE_URL}/health")
        print(f"状态码：{resp.status_code}")
        print(f"响应：{resp.json()}")
    except Exception as e:
        print(f"错误：{e}")

def test_mcp_initialize():
    """测试 MCP initialize"""
    print(f"\n=== 测试 MCP initialize ===")
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    try:
        resp = requests.post(f"{BASE_URL}/mcp", json=request)
        print(f"状态码：{resp.status_code}")
        print(f"响应：{json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"错误：{e}")

def test_mcp_tools_list():
    """测试 tools/list"""
    print(f"\n=== 测试 tools/list ===")
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    try:
        resp = requests.post(f"{BASE_URL}/mcp", json=request)
        print(f"状态码：{resp.status_code}")
        print(f"响应：{json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"错误：{e}")

def test_run_scripts():
    """测试 run_scripts 工具"""
    print(f"\n=== 测试 run_scripts ===")

    # 简单的测试脚本 - 使用正确的 SketchWorkPlane 签名
    test_script = """
# 逐步测试
print("Step 1: NCTI 可用")
print(f"NCTI type: {type(NCTI)}")

print("Step 2: doc 可用")
print(f"doc type: {type(doc)}")

print("Step 3: YH 可用")
print(f"YH type: {type(YH)}")

skt = YH.SketchWorkPlane(doc, NCTI.Point(0,0,0), NCTI.Vector(1,0,0), NCTI.Vector(0,1,0))
# 定义中心线输入起止点
input_start = NCTI.Point(10, 0, 0)
input_end = NCTI.Point(5, 20, 0)
# 创建中心线
skt.AddCenterLine(input_start, input_end)
# 获取中心线对象
center_line = skt.GetCenterLine()
# 校验中心线创建与坐标匹配

result = YH.Error()
tolerance = 1e-6

if center_line is not None:
    # 读取中心线实际起止点
    real_start = center_line.StartPoint()
    real_end = center_line.EndPoint()

    # 校验起点坐标
    err_sx = abs(real_start.X - input_start.X)
    err_sy = abs(real_start.Y - input_start.Y)
    err_sz = abs(real_start.Z - input_start.Z)
    # 校验终点坐标
    err_ex = abs(real_end.X - input_end.X)
    err_ey = abs(real_end.Y - input_end.Y)
    err_ez = abs(real_end.Z - input_end.Z)

    if err_sx <= tolerance and err_sy <= tolerance and err_sz <= tolerance and err_ex <= tolerance and err_ey <= tolerance and err_ez <= tolerance:
        result.SetErrorState(0)
    else:
        result.SetErrorState(1, "error: 中心线起止点坐标与输入不匹配")
else:
    result.SetErrorState(1, "error: 获取中心线对象失败，中心线未创建")

print("All steps completed successfully!")
"""

    request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "run_scripts",
            "arguments": {
                "model_path": "debug/test_line.yha",
                "scripts": [
                    {
                        "script_type": "python",
                        "script_content": test_script,
                        "should_execute": True
                    }
                ]
            }
        }
    }

    try:
        print("发送请求...")
        start_time = time.time()
        resp = requests.post(f"{BASE_URL}/mcp", json=request, timeout=30)
        elapsed = time.time() - start_time
        print(f"请求耗时：{elapsed:.2f}秒")
        print(f"状态码：{resp.status_code}")
        print(f"响应：{json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    except requests.exceptions.Timeout:
        print("错误：请求超时（30 秒）")
    except Exception as e:
        print(f"错误：{e}")

def test_simple_python():
    """测试简单的 Python 代码"""
    print(f"\n=== 测试简单 Python 代码 ===")

    # 最简单的测试 - 只用 print
    test_script = """
print("Hello from CAD script!")
print(f"doc 类型：{type(doc)}")
print(f"NCTI 类型：{type(NCTI)}")
print(f"YH 类型：{type(YH)}")
"""

    request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "run_scripts",
            "arguments": {
                "model_path": "debug/simple_test.yha",
                "scripts": [
                    {
                        "script_type": "python",
                        "script_content": test_script,
                        "should_execute": True
                    }
                ]
            }
        }
    }

    try:
        print("发送请求...")
        start_time = time.time()
        resp = requests.post(f"{BASE_URL}/mcp", json=request, timeout=30)
        elapsed = time.time() - start_time
        print(f"请求耗时：{elapsed:.2f}秒")
        print(f"状态码：{resp.status_code}")
        print(f"响应：{json.dumps(resp.json(), indent=2, ensure_ascii=False)}")
    except requests.exceptions.Timeout:
        print("错误：请求超时（30 秒）")
    except Exception as e:
        print(f"错误：{e}")

def main():
    print("MCP 服务器本地测试脚本")
    print(f"服务器地址：{BASE_URL}")

    # 先测试健康检查
    test_health()

    # 测试 MCP 协议
    test_mcp_initialize()
    test_mcp_tools_list()

    # 测试简单脚本
    test_simple_python()

    # 测试完整脚本
    test_run_scripts()

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    main()
