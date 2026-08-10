"""上传脚本共享配置和工具函数。"""

from contextlib import contextmanager

import paramiko

SERVER_IP = "172.16.45.61"
SERVER_USER = "root"
SERVER_PASSWORD = "Admin@102112"
REMOTE_FILE_DIR = "/mnt/data/geometry_data/steps/step_files"
HASH_PREFIX_LEN = 8


def create_ssh_connection():
    """创建新的 SSH 连接。"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASSWORD)
    return ssh


def is_connection_alive(ssh):
    """检查 SSH 连接是否仍然活跃。"""
    transport = ssh.get_transport()
    return transport is not None and transport.is_active()


def format_time(seconds):
    """格式化秒数为可读时间。"""
    if seconds < 60:
        return f"{seconds:.0f} 秒"
    elif seconds < 3600:
        return f"{seconds / 60:.0f} 分钟"
    else:
        return f"{seconds / 3600:.1f} 小时"


def reconnect(ssh):
    """关闭旧连接，创建新 SSH 连接和 SFTP 会话，返回 (ssh, sftp)。"""
    try:
        ssh.close()
    except Exception:
        pass
    ssh = create_ssh_connection()
    sftp = ssh.open_sftp()
    return ssh, sftp


@contextmanager
def ssh_connection():
    ssh = create_ssh_connection()
    try:
        yield ssh
    finally:
        ssh.close()
