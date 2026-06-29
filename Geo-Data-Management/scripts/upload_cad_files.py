"""
CAD 模型文件上传脚本

扫描本地 STP/STEP/IGS 文件，上传到服务器，元数据写入本地数据库。
上传时自动跳过已存在的文件和数据库中已有的记录，可反复运行。
支持 SSH 断线自动重连、不完整文件检测、上传进度显示。

依赖: pip install paramiko
用法: python scripts/upload_cad_files.py          # 上传并写入
      python scripts/upload_cad_files.py --dry-run # 仅预览，不执行操作
"""

import json
import os
import sys
import hashlib
import socket
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import paramiko

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.database.models import PartInfo
from scripts._shared import (
    HASH_PREFIX_LEN, REMOTE_FILE_DIR,
    create_ssh_connection, format_time, is_connection_alive, reconnect,
)

LOCAL_BASE_DIR = r"J:\测试用例库模型\装配体拆分零部件转脚本方案\第二阶段\装备"
OVERRIDE_INDUSTRY = None
CAD_EXTENSIONS = {'.stp', '.step', '.igs'}
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".upload_cache.json")

CACHE_SAVE_INTERVAL = 100
MAX_RETRIES = 3
RETRY_WAIT = 5

ERR_RECONNECT_STAT = "重连失败，无法检查远程文件"
ERR_SIZE_MISMATCH = "大小不匹配: 本地 {}, 远程 {}"
ERR_RETRIES_EXHAUSTED = "重试{}次后失败: {}"


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("缓存文件损坏，将重新计算")
    return {}


def save_cache(cache):
    tmp_path = CACHE_FILE + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp_path, CACHE_FILE)


def compute_sha256(file_path):
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def scan_files(base_dir, industry=None):
    """扫描目录，返回 (local_path, name, format, industry, product_type) 列表。"""
    if industry is None:
        industry = os.path.basename(os.path.normpath(base_dir)).replace("行业", "")

    files = []
    for root, _, filenames in os.walk(base_dir):
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in CAD_EXTENSIONS:
                continue

            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, base_dir)
            product_type = Path(rel_path).parts[0]

            files.append((file_path, filename, ext.lstrip('.'), industry, product_type))

    return files


def load_uploaded_hashes(cache):
    """从缓存和数据库合并已上传的 hash_id → remote_name 映射。"""
    uploaded_hashes = {}
    for info in cache.values():
        if "remote_name" in info:
            uploaded_hashes[info["hash_id"]] = info["remote_name"]

    db = SessionLocal()
    try:
        db_count = 0
        for row in db.query(PartInfo.hash_id, PartInfo.name).all():
            if row.hash_id not in uploaded_hashes:
                uploaded_hashes[row.hash_id] = row.name
                db_count += 1
        if db_count:
            print(f"从数据库补充: {db_count} 条记录")
    finally:
        db.close()

    return uploaded_hashes


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"扫描目录: {LOCAL_BASE_DIR}")
    files = scan_files(LOCAL_BASE_DIR, industry=OVERRIDE_INDUSTRY)
    print(f"找到 {len(files)} 个 CAD 文件\n")

    if not files:
        return

    if dry_run:
        stats = Counter((ind, pt) for _, _, _, ind, pt in files)
        for (ind, pt), count in sorted(stats.items()):
            print(f"  {ind} / {pt}: {count} 个")
        print(f"\n[dry-run] 仅预览，不执行操作")
        return

    cache = load_cache()
    print(f"加载缓存: {len(cache)} 条记录")

    init_db()

    uploaded_hashes = load_uploaded_hashes(cache)
    print(f"已上传记录: {len(uploaded_hashes)} 条\n")

    now = datetime.now(timezone(timedelta(hours=8)))

    # 计算文件哈希（缓存命中的跳过）
    print("计算文件哈希...")
    seen = {}
    new_count = 0
    for i, (local_path, name, fmt, industry, product_type) in enumerate(files):
        if local_path in cache:
            hash_id = cache[local_path]["hash_id"]
        else:
            hash_id = compute_sha256(local_path)
            new_count += 1
            cache[local_path] = {"hash_id": hash_id}

        if hash_id not in seen:
            seen[hash_id] = {
                "hash_id": hash_id,
                "name": name,
                "format": fmt,
                "is_open_source": False,
                "source_type": "private",
                "industry": industry,
                "product_type": product_type,
                "created_time": now,
                "modified_time": now,
                "_local_path": local_path,
            }
        if (i + 1) % 500 == 0:
            print(f"  已处理 {i + 1}/{len(files)}...")

    print(f"  哈希计算完成 (新计算 {new_count} 个，缓存命中 {len(files) - new_count} 个)")

    total = len(files)
    records = list(seen.values())
    if len(records) < total:
        print(f"去重: {total} -> {len(records)} (跳过 {total - len(records)} 个内容重复文件)")

    stats = Counter((r["industry"], r["product_type"]) for r in records)
    for (ind, pt), count in sorted(stats.items()):
        print(f"  {ind} / {pt}: {count} 个")

    # 筛选出需要上传的文件
    to_upload = [r for r in records if r["hash_id"] not in uploaded_hashes]
    skipped_upload = len(records) - len(to_upload)

    if not to_upload:
        print("\n所有文件已上传，无需操作")
    else:
        # 连接服务器并上传，支持断线重连
        print(f"\n连接服务器...")
        print(f"待上传: {len(to_upload)} 个文件\n")

        ssh = create_ssh_connection()
        _, stdout, _ = ssh.exec_command(f"mkdir -p {REMOTE_FILE_DIR}")
        stdout.channel.recv_exit_status()
        sftp = ssh.open_sftp()
        existing = set(sftp.listdir(REMOTE_FILE_DIR))

        uploaded = 0
        failed = []
        start_time = time.time()

        for i, record in enumerate(to_upload):
            hash_id = record["hash_id"]
            remote_name = record["name"]
            remote_path = f"{REMOTE_FILE_DIR}/{remote_name}"

            # 检查服务器上是否已存在同名文件
            if remote_name in existing:
                local_size = os.path.getsize(record["_local_path"])
                file_ok = False
                for attempt in range(MAX_RETRIES):
                    try:
                        if not is_connection_alive(ssh):
                            raise paramiko.SSHException("连接断开")
                        remote_size = sftp.stat(remote_path).st_size
                        if local_size == remote_size:
                            file_ok = True
                        break
                    except (paramiko.SSHException, socket.error, EOFError, OSError):
                        if attempt < MAX_RETRIES - 1:
                            print(f"  检查文件时连接断开，重连中... ({attempt + 1}/{MAX_RETRIES})")
                            time.sleep(RETRY_WAIT)
                            ssh, sftp = reconnect(ssh)
                        else:
                            failed.append((record["name"], ERR_RECONNECT_STAT))
                            file_ok = True  # 跳过此文件

                if file_ok:
                    skipped_upload += 1
                    cache[record["_local_path"]] = {"hash_id": hash_id, "remote_name": remote_name}
                    uploaded_hashes[hash_id] = remote_name
                    continue

                # 文件不完整，删除后重新上传
                try:
                    sftp.remove(remote_path)
                except OSError:
                    pass
                existing.discard(remote_name)

            # 尝试 hash 前缀名称
            if remote_name in existing:
                remote_name = f"{hash_id[:HASH_PREFIX_LEN]}_{remote_name}"
                remote_path = f"{REMOTE_FILE_DIR}/{remote_name}"
                if remote_name in existing:
                    skipped_upload += 1
                    continue

            # 上传文件（带重试和重连）
            local_size = os.path.getsize(record["_local_path"])
            for attempt in range(MAX_RETRIES):
                try:
                    if not is_connection_alive(ssh):
                        raise paramiko.SSHException("连接断开")

                    sftp.put(record["_local_path"], remote_path)
                    remote_size = sftp.stat(remote_path).st_size

                    if local_size != remote_size:
                        sftp.remove(remote_path)
                        failed.append((record["name"], ERR_SIZE_MISMATCH.format(local_size, remote_size)))
                        break

                    existing.add(remote_name)
                    uploaded += 1

                    cache[record["_local_path"]] = {"hash_id": hash_id, "remote_name": remote_name}
                    uploaded_hashes[hash_id] = remote_name

                    if uploaded % CACHE_SAVE_INTERVAL == 0:
                        save_cache(cache)

                    # 显示进度
                    elapsed = time.time() - start_time
                    speed = (i + 1) / elapsed if elapsed > 0 else 0
                    remaining = (len(to_upload) - i - 1) / speed if speed > 0 else 0
                    pct = (i + 1) / len(to_upload) * 100
                    print(f"  [{i + 1}/{len(to_upload)}] {pct:.1f}% 上传: {record['name']} (预计剩余 {format_time(remaining)})")

                    break

                except (paramiko.SSHException, socket.error, EOFError, OSError) as e:
                    if attempt < MAX_RETRIES - 1:
                        print(f"  上传中断，重连中... ({attempt + 1}/{MAX_RETRIES}): {e}")
                        time.sleep(RETRY_WAIT)
                        ssh, sftp = reconnect(ssh)
                    else:
                        failed.append((record["name"], ERR_RETRIES_EXHAUSTED.format(MAX_RETRIES, e)))

        save_cache(cache)
        elapsed = time.time() - start_time
        print(f"\n文件上传: 新上传 {uploaded} 个, 跳过 {skipped_upload} 个 (已存在), 耗时 {format_time(elapsed)}")
        if failed:
            print(f"失败 {len(failed)} 个:")
            for name, reason in failed:
                print(f"  {name}: {reason}")

        ssh.close()

    # 批量写入本地数据库
    print("\n写入本地数据库...")
    db = SessionLocal()
    try:
        existing_hashes = set(row[0] for row in db.query(PartInfo.hash_id).all())

        inserted = 0
        skipped_db = 0
        for record in records:
            if record["hash_id"] in existing_hashes:
                skipped_db += 1
                continue

            data = {k: v for k, v in record.items() if not k.startswith("_")}
            db.add(PartInfo(**data))
            inserted += 1

        db.commit()
        print(f"数据库: 插入 {inserted} 条, 跳过 {skipped_db} 条 (已存在)")
    finally:
        db.close()

    print("\n全部完成!")


if __name__ == "__main__":
    main()
