"""
检查 bin 目录中的图文件，若 spatial_pos 包含 -2147483648 则删除对应的 step、label、bin。
来源：BrepMFR-main/data/check_and_clean_invalid.py
"""
import os
import logging
from dgl.data.utils import load_graphs

from src.utils.base_functions import load_config_basic


def _get_mfr_clean_paths(config, path_set="default"):
    """获取 MFR 清理相关路径。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config['data_path_infos']['use_absolute_path']
    mfr_data_infos = config['data_path_infos']['mfr_data_infos']

    if path_set == "adv_unlabeled":
        bin_dir = mfr_data_infos.get('adv_unlabeled_bin_data', mfr_data_infos['bin_data'])
        deleted_txt = mfr_data_infos.get(
            'adv_unlabeled_deleted_invalid_txt',
            mfr_data_infos.get('deleted_invalid_txt', 'data/processed/round/deleted_invalid_files.txt')
        )
        label_dir = None
        step_dirs = [mfr_data_infos.get('adv_unlabeled_step_data', "")]
    else:
        bin_dir = mfr_data_infos['bin_data']
        deleted_txt = mfr_data_infos.get('deleted_invalid_txt', 'data/processed/round/deleted_invalid_files.txt')
        label_dir = config['data_path_infos']['processed_label_data']
        step_dirs = []
        if config['data_path_infos']['use_public_data']:
            p = config['data_path_infos']['public_data_path_infos']['raw_step_data']
            step_dirs.append(p)
        if config['data_path_infos']['use_real_data']:
            p = config['data_path_infos']['real_data_path_infos']['raw_step_data']
            step_dirs.append(p)

    if not use_absolute:
        bin_dir = os.path.join(base_dir, bin_dir)
        if label_dir:
            label_dir = os.path.join(base_dir, label_dir)
        deleted_txt = os.path.join(base_dir, deleted_txt)
        step_dirs = [os.path.join(base_dir, p) if p else p for p in step_dirs]

    return bin_dir, label_dir, step_dirs, deleted_txt


def _has_invalid_spatial_pos(spatial_pos):
    """检查 spatial_pos 是否包含 -2147483648"""
    if spatial_pos is None:
        return False
    try:
        arr = spatial_pos.numpy() if hasattr(spatial_pos, 'numpy') else spatial_pos
        return (arr == -2147483648).any()
    except Exception:
        return False


def check_and_clean_invalid(path_set="default"):
    """
    检查 bin 目录中的图文件，若 spatial_pos 包含 -2147483648 则删除对应的 step、label、bin。
    返回被删除的文件名列表。
    """
    config = load_config_basic()
    bin_dir, label_dir, step_dirs, deleted_txt_path = _get_mfr_clean_paths(config, path_set=path_set)

    if not os.path.exists(bin_dir):
        logging.warning(f"Bin 目录不存在: {bin_dir}")
        return []

    deleted_files = []

    for root, _dirs, files in os.walk(bin_dir):
        for bin_file in files:
            if not bin_file.endswith(".bin"):
                continue
            bin_path = os.path.join(root, bin_file)
            file_id = os.path.splitext(bin_file)[0]
            rel_path = os.path.relpath(root, bin_dir)

            try:
                graphs, labels = load_graphs(bin_path)
                if not graphs:
                    continue
                graph = graphs[0]

                if not labels or "spatial_pos" not in labels:
                    continue
                spatial_pos = labels["spatial_pos"]
                if not _has_invalid_spatial_pos(spatial_pos):
                    continue

                os.remove(bin_path)
                deleted_files.append(os.path.join(rel_path, file_id) if rel_path != '.' else file_id)
                logging.info(f"已删除无效文件: {file_id}")

                if label_dir:
                    label_file = os.path.join(label_dir, rel_path, f"{file_id}.json") if rel_path != '.' else os.path.join(label_dir, f"{file_id}.json")
                    if os.path.exists(label_file):
                        os.remove(label_file)

                for step_dir in step_dirs:
                    if not os.path.exists(step_dir):
                        continue
                    step_file = os.path.join(step_dir, rel_path, f"{file_id}.step") if rel_path != '.' else os.path.join(step_dir, f"{file_id}.step")
                    if os.path.exists(step_file):
                        os.remove(step_file)
                        break
                    step_file_stp = os.path.join(step_dir, rel_path, f"{file_id}.stp") if rel_path != '.' else os.path.join(step_dir, f"{file_id}.stp")
                    if os.path.exists(step_file_stp):
                        os.remove(step_file_stp)
                        break
            except Exception as e:
                logging.error(f"处理 {bin_file} 时出错: {e}")

    if deleted_files:
        os.makedirs(os.path.dirname(deleted_txt_path), exist_ok=True)
        with open(deleted_txt_path, "a", encoding="utf-8") as f:
            for file_id in deleted_files:
                f.write(file_id + "\n")
        logging.info(f"共删除 {len(deleted_files)} 个无效文件，记录已写入 {deleted_txt_path}")

    return deleted_files


if __name__ == "__main__":
    deleted = check_and_clean_invalid()
    print(f"\n共删除 {len(deleted)} 个无效文件")
    if deleted:
        for fid in deleted:
            print(f"  - {fid}")
    else:
        print("未发现无效文件")
