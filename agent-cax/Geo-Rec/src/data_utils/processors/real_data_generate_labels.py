from src.data_utils.processors.generate_labels_utils import process_labels


def main():
    """处理真实数据的标签（兼容原有调用接口）"""
    return process_labels("real")


if __name__ == "__main__":
    main()
