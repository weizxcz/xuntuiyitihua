"""
清理服务器上的重复文件

查找 step_files 目录中，同时存在 原始文件名 和 hash前缀_文件名 的重复文件，
删除 hash 前缀版本。

用法: python scripts/cleanup_duplicates.py          # 清理
      python scripts/cleanup_duplicates.py --dry-run # 仅预览
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._shared import HASH_PREFIX_LEN, REMOTE_FILE_DIR, ssh_connection

DUPLICATE_PATTERN = re.compile(rf'^[0-9a-f]{{{HASH_PREFIX_LEN}}}_.+$')


def main():
    dry_run = "--dry-run" in sys.argv

    print("连接服务器...")
    with ssh_connection() as ssh:
        sftp = ssh.open_sftp()
        files = set(sftp.listdir(REMOTE_FILE_DIR))
        print(f"服务器上共有 {len(files)} 个文件\n")

        duplicates = []
        for f in files:
            if DUPLICATE_PATTERN.match(f):
                original_name = f[HASH_PREFIX_LEN + 1:]
                if original_name in files:
                    duplicates.append((f, original_name))

        if not duplicates:
            print("没有发现重复文件")
            return

        print(f"发现 {len(duplicates)} 个重复文件:")
        for dup, orig in duplicates:
            print(f"  删除: {dup} (原始: {orig})")

        if dry_run:
            print(f"\n[dry-run] 仅预览，不执行删除")
        else:
            for dup, _ in duplicates:
                sftp.remove(f"{REMOTE_FILE_DIR}/{dup}")
            print(f"\n已删除 {len(duplicates)} 个重复文件")


if __name__ == "__main__":
    main()
