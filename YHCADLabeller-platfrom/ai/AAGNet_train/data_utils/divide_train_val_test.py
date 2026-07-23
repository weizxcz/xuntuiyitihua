import os
import random
import logging
from ..base_functions import load_config_basic


def write_to_txt(txt_save_dir,file_list, txt_filename):
    txt_path = os.path.join(txt_save_dir, txt_filename)
    # 写入TXT（每个文件名一行，无后缀）
    with open(txt_path, "w", encoding="utf-8") as f:
        for filename in file_list:
            f.write(f"{filename}\n")
    logging.info(f"已生成 {txt_filename}，保存路径：{txt_path}")


def split_dataset_to_txt():

    """将labels目录下的JSON文件按设置比例划分为训练集、验证集和测试集，并生成对应的TXT文件"""
    logging.info("==================所有数据划分txt文件开始生成==========================")
    configs = load_config_basic()
    RANDOM_SEED = configs['data_path_infos']['divide_data_infos']['random_seed']
    TRAIN_RATIO = configs['data_path_infos']['divide_data_infos']['train_ratio']
    VAL_RATIO = configs['data_path_infos']['divide_data_infos']['val_ratio']
    labels_round_dir = configs['data_path_infos']['processed_label_data']
    txt_save_dir = configs['data_path_infos']['divide_data_infos']['divide_result_txt_save_dir']

    if not os.path.exists(txt_save_dir):
        os.makedirs(txt_save_dir)
        logging.info(f"已创建TXT文件保存目录：{txt_save_dir}")

    # 检查labels_round目录是否存在
    if not os.path.exists(labels_round_dir):
        logging.error(f"错误：目标目录 {labels_round_dir} 不存在，请检查路径！")
        return

    file_list = []
    for filename in os.listdir(labels_round_dir):
        # 仅保留JSON文件
        if filename.lower().endswith(".json"):
            # 去除后缀，获取纯文件名
            pure_filename = os.path.splitext(filename)[0]
            file_list.append(pure_filename)

    total_files = len(file_list)
    if total_files == 0:
        logging.warning(f"警告：在 {labels_round_dir} 中未找到任何JSON文件，无需划分！")
        return
    logging.info(f"成功获取 {total_files} 个有效文件，开始按 8:1:1 划分...")

    random.seed(RANDOM_SEED)  # 固定种子，确保可复现
    random.shuffle(file_list)

    if total_files <= 1:
        # 只有一个文件，全部当训练集，验证/测试留空
        logging.warning("文件总数 <= 1，无法划分验证集/测试集，全部作为训练集")
        train_count, val_count, test_count = total_files, 0, 0
    elif total_files == 2:
        # 只有两个文件，训练 1 / 验证 1，测试留空（训练主循环依赖 val_loader 非空）
        logging.warning("文件总数仅 2 个，无法保留三集，按 训练1/验证1/测试0 划分")
        train_count, val_count, test_count = 1, 1, 0
    else:
        # 训练集数量（80%）
        train_count = int(total_files * TRAIN_RATIO)
        # 验证集数量（10%）
        val_count = int(total_files * VAL_RATIO)
        # 测试集数量（剩余部分，避免因取整导致总数不一致）
        test_count = total_files - train_count - val_count
        # 小数据集下 int() 取整可能让验证集/测试集变 0，强制各至少 1 个，
        # 否则空验证集会让训练主循环（val_loader 必遍历）崩溃
        if val_count < 1:
            train_count -= 1
            val_count = 1
        if test_count < 1:
            train_count -= 1
            test_count = 1

    # 分割列表
    train_files = file_list[:train_count]
    val_files = file_list[train_count : train_count + val_count]
    test_files = file_list[train_count + val_count :]

    # 打印划分结果（验证比例）
    logging.info(f"划分结果：")
    logging.info(f"- 训练集：{len(train_files)} 个文件（{len(train_files)/total_files:.1%}）")
    logging.info(f"- 验证集：{len(val_files)} 个文件（{len(val_files)/total_files:.1%}）")
    logging.info(f"- 测试集：{len(test_files)} 个文件（{len(test_files)/total_files:.1%}）")

    # 生成三个TXT文件
    write_to_txt(txt_save_dir,train_files, "train.txt")
    write_to_txt(txt_save_dir,val_files, "val.txt")
    write_to_txt(txt_save_dir,test_files, "test.txt")

    logging.info(f"TXT文件保存目录：{txt_save_dir}")
    logging.info(f"================所有数据划分txt文件生成完成！======================")

def get_train_val_test_info():
    configs = load_config_basic()
    txt_save_dir = configs['data_path_infos']['divide_data_infos']['divide_result_txt_save_dir']
    train_val_test_info_list = [
        {
            "name": "train",
            "file_list_path": os.path.join(txt_save_dir, "train.txt")
        },
        {
            "name": "val",
            "file_list_path": os.path.join(txt_save_dir, "val.txt")
        },
        {
            "name": "test",
            "file_list_path": os.path.join(txt_save_dir, "test.txt")
        }
    ]
    return train_val_test_info_list
