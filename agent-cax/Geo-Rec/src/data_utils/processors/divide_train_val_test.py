import os
import random
import logging
from src.utils.base_functions import load_config_basic


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
    if not configs['data_path_infos']['use_absolute_path']:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        labels_round_dir = os.path.join(base_dir, labels_round_dir)
        txt_save_dir = os.path.join(base_dir, txt_save_dir)
    
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

    # 训练集数量（80%）
    train_count = int(total_files * TRAIN_RATIO)
    # 验证集数量（10%）
    val_count = int(total_files * VAL_RATIO)
    # 测试集数量（剩余10%，避免因取整导致总数不一致）
    test_count = total_files - train_count - val_count

    # 分割列表
    train_files = file_list[:train_count]
    val_files = file_list[train_count : train_count + val_count]
    test_files = file_list[train_count + val_count :]

    # 打印划分结果（验证比例）
    logging.info(f"划分结果：")
    logging.info(f"- 训练集：{len(train_files)} 个文件（{len(train_files)/total_files:.1%}）")
    logging.info(f"- 验证集：{len(val_files)} 个文件（{len(val_files)/total_files:.1%}）")
    logging.info(f"- 测试集：{len(test_files)} 个文件（{len(test_files)/total_files:.1%}）")

    # -------------------------- 5. 定义函数：将文件列表写入TXT --------------------------
    

    # -------------------------- 6. 生成三个TXT文件 --------------------------
    write_to_txt(txt_save_dir,train_files, "train.txt")
    write_to_txt(txt_save_dir,val_files, "val.txt")
    write_to_txt(txt_save_dir,test_files, "test.txt")

    logging.info(f"TXT文件保存目录：{txt_save_dir}")
    logging.info(f"================所有数据划分txt文件生成完成！======================")

def get_train_val_test_info():
    configs = load_config_basic()
    txt_save_dir = configs['data_path_infos']['divide_data_infos']['divide_result_txt_save_dir']
    if not configs['data_path_infos']['use_absolute_path']:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        txt_save_dir = os.path.join(base_dir, txt_save_dir)
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


if __name__ == "__main__":
    split_dataset_to_txt()