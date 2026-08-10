from .generate_labels_utils import process_labels


def process_round_json_files():
    """处理公开数据集的标签（兼容原有调用接口）"""
    return process_labels("public")
