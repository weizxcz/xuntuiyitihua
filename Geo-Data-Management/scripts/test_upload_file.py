"""测试 upload_file 接口"""

import requests

URL = "http://127.0.0.1:5060/api/label/upload_file"
FILE_PATH = r"D:\wyg\data\含盲孔.stp"  # 替换成你本地的 stp 文件路径


def main():
    print(f"上传文件: {FILE_PATH}")
    print(f"目标接口: {URL}\n")

    try:
        with open(FILE_PATH, "rb") as f:
            resp = requests.post(URL, files={"file": f}, timeout=60)
    except FileNotFoundError:
        print(f"文件不存在: {FILE_PATH}，请修改 FILE_PATH")
        return
    except requests.ConnectionError:
        print("连接失败，确认服务器是否启动")
        return

    print(f"状态码: {resp.status_code}")
    try:
        print(f"返回: {resp.json()}")
    except Exception:
        print(f"返回(原始): {resp.text}")


if __name__ == "__main__":
    main()
