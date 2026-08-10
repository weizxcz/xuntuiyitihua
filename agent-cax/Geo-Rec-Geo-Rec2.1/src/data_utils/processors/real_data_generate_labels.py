
import json
import os
import logging
from src.utils.base_functions import init_ncti,load_config_basic


def count_faces_in_stp(step_file_path, NCTI):
    """使用NCTI接口计算STP文件中面的数量"""
    try:
        doc = NCTI.Document()
        doc.New("OCC", "DCM", 0)
        doc.RunCommand("cmd_ncti_import_file", step_file_path, "testbox")
        ai = NCTI.AiModel(doc, "testbox")
        # 获取面数量 - 通过FaceID列表的长度
        face_count = len(ai.FaceID)
        doc.Delete()
        return face_count, True
    except Exception as e:
        logging.error(f"使用NCTI接口读取STP文件时出错: {e}")

        return 0, False


def generate_round_json_output(stp_filename, face_count, feature_json):
    """
    生成指定格式的JSON输出
    根据要求：将所有圆角的面标为1，其他为0
    inst矩阵仅在对角线位置（行=列）设置为1
    """
    # 提取文件名（不含扩展名）作为ID
    file_id = os.path.splitext(stp_filename)[0]

    # 初始化seg字典，所有面默认类别为0（其他）
    seg = {str(i): 0 for i in range(face_count)}

    # 初始化inst矩阵（全0）
    inst = [[0] * face_count for _ in range(face_count)]

    # 初始化bottom字典（全0）
    bottom = {str(i): 0 for i in range(face_count)}

    # 处理特征信息 - 提取所有圆角相关的特征
    rounded_corner_faces = []
    if "content" in feature_json:
        for feature_name, face_indices in feature_json["content"].items():
            # 检查是否是圆角特征
            if "圆角" in feature_name:
                # 处理面索引（支持单个数值或列表）
                if isinstance(face_indices, int):
                    rounded_corner_faces.append(face_indices)
                elif isinstance(face_indices, list):
                    rounded_corner_faces.extend(face_indices)

    # 标记所有圆角面为1，并设置inst矩阵的对角线
    for face_idx in rounded_corner_faces:
        if isinstance(face_idx, int) and face_idx < face_count:
            seg[str(face_idx)] = 1  # 标记为圆角
            # 只在对角线位置设置为1（行索引=列索引）
            inst[face_idx][face_idx] = 1

    # 构建最终输出结构
    output = [
        [
            file_id,
            {
                "seg": seg,
                "inst": inst,
                "bottom": bottom
            }
        ]
    ]

    return output


def find_corresponding_file(base_name, target_dir, extensions):
    """查找目标目录中与基础名称对应的文件"""
    for ext in extensions:
        candidate = os.path.join(target_dir, f"{base_name}{ext}")
        if os.path.exists(candidate):
            return candidate
    return None


def process_all_files(step_dir, json_dir, output_dir, NCTI):
    """批量处理所有文件"""
    # 创建输出目录（如果不存在）
    os.makedirs(output_dir, exist_ok=True)

    # 定义文件扩展名
    step_extensions = ['.stp', '.step']
    json_extensions = ['.json']

    # 遍历STEP目录中的所有文件
    for filename in os.listdir(step_dir):
        # 获取文件基本名称（不含扩展名）
        base_name = os.path.splitext(filename)[0]
        file_ext = os.path.splitext(filename)[1].lower()

        # 只处理STEP/STP文件
        if file_ext not in step_extensions:
            continue

        # 构建完整路径
        step_file_path = os.path.join(step_dir, filename)

        # 查找对应的JSON文件
        json_file_path = find_corresponding_file(base_name, json_dir, json_extensions)
        if not json_file_path:
            logging.warning(f"警告: 未找到对应的JSON文件，跳过 {filename}")
            continue

        face_count, success = count_faces_in_stp(step_file_path, NCTI)
        if not success:
            logging.warning(f"警告: 无法处理STP文件 {filename}，跳过")
            continue

        logging.info(f"真实数据：{filename}文件包含 {face_count} 个面")

        # 读取特征JSON文件
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                feature_json = json.load(f)
        except Exception as e:
            logging.error(f"读取特征JSON文件时出错: {e}，跳过该文件")
            continue

        # 生成输出JSON
        output_json = generate_round_json_output(filename, face_count, feature_json)

        # 保存输出JSON
        output_file_path = os.path.join(output_dir, f"{base_name}.json")
        try:
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(output_json, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"保存JSON文件时出错: {e}")


def main():
    config = load_config_basic()
    # 设置目录路径
    logging.info("==================真实数据label信息开始处理==========================")
    step_dir = config['data_path_infos']['real_data_path_infos']['raw_step_data']  # STEP文件目录
    json_dir = config['data_path_infos']['real_data_path_infos']['raw_label_data']  # 特征JSON文件目录
    output_dir = config['data_path_infos']['processed_label_data']  # 输出目录
    if not config['data_path_infos']['use_absolute_path']:
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        step_dir = os.path.join(current_dir, step_dir)
        json_dir =  os.path.join(current_dir, json_dir)
        output_dir = os.path.join(current_dir, output_dir)


    # 验证目录是否存在
    if not os.path.exists(step_dir):
        logging.error(f"错误: STEP文件目录不存在 - {step_dir}")
        return

    if not os.path.exists(json_dir):
        logging.error(f"错误: JSON文件目录不存在 - {json_dir}")
        return

    # 初始化NCTI环境
    logging.info("正在初始化NCTI环境...")
    NCTI = init_ncti()
    if not NCTI:
        logging.error("错误: 无法初始化NCTI环境")
        return

    # 批量处理所有文件
    process_all_files(step_dir, json_dir, output_dir, NCTI)

    logging.info("==================真实数据label信息处理完成==========================")


if __name__ == "__main__":
    main()