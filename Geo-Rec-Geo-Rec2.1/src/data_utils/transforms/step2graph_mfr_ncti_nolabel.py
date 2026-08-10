"""
BrepMFR 模型的无 label step 转 graph 模块。

与 `step2graph_mfr_ncti.py` 相比：仅移除对面标签文件的读取逻辑，
并在没有 label 的情况下把每个面的节点特征 `f` 统一填为默认值。
若需要把默认 f 改成别的值，可在 configs/configs.yaml 的 mfr_step2graph_infos 下加入 face_f_default: <值>；当前配置里没有这个字段，所以默认就是 0。
其余几何/拓扑/距离/路径等计算流程保持一致。
"""

import os
import gc
import logging
from itertools import repeat
from multiprocessing.pool import Pool
from pathlib import Path

from tqdm import tqdm

from src.utils.base_functions import (
    load_config_basic,
    save_json_data,
    init_ncti,
)

# 复用原脚本中的核心实现与辅助函数
from src.data_utils.transforms import step2graph_mfr_ncti as labeled_impl


_mfr_extractor = None


class BrepMFRExtractorNoLabel(labeled_impl.BrepMFRExtractor):
    """
    无 label 版本的 BrepMFR 图提取器：
    - 不读取任何 label 文件
    - 对所有面把 feature_labels 统一设为默认值，从而得到统一的 node_data["f"]
    """

    def process(self, step_file):
        doc = None
        try:
            doc = self.NCTI.Document()
            doc.New("OCC", "DCM", 0)
            import_result = doc.RunCommand("cmd_ncti_import_file", str(step_file), "testbox")
            if not import_result:
                raise Exception("Failed to import STEP file")

            ai_u = self.config.get("ai_u_count", 5)
            ai_v = self.config.get("ai_v_count", 5)
            ai_edge = self.config.get("ai_edge_count", 5)
            ai = self.NCTI.AiModel(doc, "testbox", ai_u, ai_v, ai_edge)

            face_ids = ai.FaceID
            if not face_ids:
                json_data = self._get_empty_graph_structure()
                return json_data

            face_f_default = int(self.config.get("face_f_default", 0))
            feature_labels = [face_f_default] * len(face_ids)
            json_data = self._process_core(doc, "testbox", ai, feature_labels)
            return json_data
        except Exception as e:
            logging.error(f"处理 {step_file} 失败: {e}")
            raise
        finally:
            if doc is not None:
                try:
                    doc.Clear()
                except Exception:
                    pass


def _mfr_initializer():
    """多进程初始化：为每个子进程创建 BrepMFRExtractor（无 label 版本）"""
    import signal

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    global _mfr_extractor
    config = load_config_basic()
    ncti = init_ncti()
    mfr_config = _build_mfr_extractor_config(config)
    _mfr_extractor = BrepMFRExtractorNoLabel(config=mfr_config, ncti=ncti)


def _build_mfr_extractor_config(config):
    """构建 BrepMFRExtractorNoLabel 所需的 config 字典"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config["data_path_infos"]["use_absolute_path"]

    # 兼容原脚本配置结构：即便我们不读取 label，也保留 label_dir 字段
    label_dir = config["data_path_infos"]["processed_label_data"]
    if not use_absolute:
        label_dir = os.path.join(base_dir, label_dir)

    mfr_graph_config = config.get("mfr_step2graph_infos", {})
    return {
        "label_dir": label_dir,
        "ai_u_count": mfr_graph_config.get("ai_u_count", 5),
        "ai_v_count": mfr_graph_config.get("ai_v_count", 5),
        "ai_edge_count": mfr_graph_config.get("ai_edge_count", 5),
        # 无 label 场景下的默认面特征 f
        "face_f_default": mfr_graph_config.get("face_f_default", 0),
    }


def _process_one_mfr_file(args):
    """处理单个 step 文件，生成 MFR 格式 JSON（无 label 版本）"""
    global _mfr_extractor
    step_path, dataset_name = args
    config = load_config_basic()
    mfr_data_infos = config.get("data_path_infos", {}).get("mfr_data_infos", {})
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config["data_path_infos"]["use_absolute_path"]
    output_dir = mfr_data_infos.get("adv_unlabeled_graphs_mfr_json", mfr_data_infos.get("graphs_mfr_json"))
    if not use_absolute:
        output_dir = os.path.join(base_dir, output_dir)

    os.makedirs(output_dir, exist_ok=True)
    json_filename = f"{step_path.stem}.json"
    json_path = os.path.join(output_dir, json_filename)

    if os.path.exists(json_path):
        logging.info(f"跳过 [{dataset_name}] {json_filename}：已存在")
        return (str(step_path.stem), True)

    try:
        json_data = _mfr_extractor.process(step_path)
        if json_data is None:
            return (str(step_path.stem), False)
        save_json_data(json_path, json_data)
        return (str(step_path.stem), True)
    except Exception as e:
        logging.error(f"处理 {step_path.stem} 失败: {e}")
        return (str(step_path.stem), False)


def step2graph_mfr_nolabel_batch():
    """
    无 label 批量 step 转 graph。

    计算逻辑与 `step2graph_mfr_batch()` 保持一致，仅把节点特征 `f`
    在无 label 的情况下统一设为默认值 `face_f_default`（默认 0）。
    """
    config = load_config_basic()
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config["data_path_infos"]["use_absolute_path"]
    mfr_data_infos = config.get("data_path_infos", {}).get("mfr_data_infos", {})
    adv_step_dir = mfr_data_infos.get("adv_unlabeled_step_data", "")
    if not adv_step_dir:
        logging.error("未配置 mfr_data_infos.adv_unlabeled_step_data，无法处理无label对抗数据")
        return
    adv_step_dir = adv_step_dir if use_absolute else os.path.join(base_dir, adv_step_dir)
    if not os.path.isdir(adv_step_dir):
        logging.error(f"无label对抗数据路径不存在或不是目录: {adv_step_dir}")
        return

    output_dir = mfr_data_infos.get("adv_unlabeled_graphs_mfr_json", mfr_data_infos.get("graphs_mfr_json"))
    if not use_absolute:
        output_dir = os.path.join(base_dir, output_dir)
    os.makedirs(output_dir, exist_ok=True)

    adv_step_files = sorted(Path(adv_step_dir).glob("*.st*p"))
    if not adv_step_files:
        logging.warning(f"无label对抗数据目录中未找到 step 文件: {adv_step_dir}")
        return

    num_workers = config["step2graph_infos"]["num_workers"]
    success_count = 0
    fail_count = 0
    dataset_name = "adv_unlabeled"
    process_args = list(zip(adv_step_files, repeat(dataset_name)))
    logging.info(f"【处理 {dataset_name}】共 {len(adv_step_files)} 个 step 文件")

    if num_workers <= 1:
        global _mfr_extractor
        ncti = init_ncti()
        mfr_config = _build_mfr_extractor_config(config)
        _mfr_extractor = BrepMFRExtractorNoLabel(config=mfr_config, ncti=ncti)

        for args in tqdm(process_args, desc=f"{dataset_name} 进度"):
            _, ok = _process_one_mfr_file(args)
            if ok:
                success_count += 1
            else:
                fail_count += 1
    else:
        with Pool(processes=num_workers, initializer=_mfr_initializer) as pool:
            for result in tqdm(
                pool.imap_unordered(_process_one_mfr_file, process_args),
                total=len(process_args),
                desc=f"{dataset_name} 进度",
            ):
                _, ok = result
                if ok:
                    success_count += 1
                else:
                    fail_count += 1

    gc.collect()
    logging.info(f"MFR 无 label 构图完成：成功 {success_count}，失败 {fail_count}")

if __name__ == "__main__":
    step2graph_mfr_nolabel_batch()