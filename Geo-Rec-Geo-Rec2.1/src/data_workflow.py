

from src.utils.base_functions import load_config_basic
from src.data_utils.processors.real_data_generate_labels import main as generate_real_data_labels
from src.data_utils.processors.public_data_generate_labels import process_round_json_files as generate_public_data_labels
from src.data_utils.processors.divide_train_val_test import split_dataset_to_txt as divide_data_into_splits
from src.data_utils.transforms.step2graph_ncti import step2graph_batch
from src.data_utils.transforms.step2graph_mfr_ncti import step2graph_mfr_batch
from src.data_utils.transforms.step2graph_mfr_ncti_nolabel import step2graph_mfr_nolabel_batch
from src.data_utils.processors.json_to_bin import json_to_bin_batch
from src.data_utils.processors.check_and_clean_invalid import check_and_clean_invalid
from src.data_utils.processors.divide_domain_adapt_splits import generate_domain_adapt_splits


def data_processing_workflow():
    configs = load_config_basic()
    use_public_data = configs['data_path_infos']['use_public_data']
    use_real_data = configs['data_path_infos']['use_real_data']
    if use_public_data:
        generate_public_data_labels()
    if use_real_data:
        generate_real_data_labels()
    divide_data_into_splits()
    step2graph_batch()


def data_processing_workflow_mfr():
    """MFR 专用数据流程：标签 → MFR构图 → JSON→Bin → 清理无效 → 重新划分"""
    configs = load_config_basic()
    use_public_data = configs['data_path_infos']['use_public_data']
    use_real_data = configs['data_path_infos']['use_real_data']
    # if use_public_data:
    #     generate_public_data_labels()
    # if use_real_data:
    #     generate_real_data_labels()

    train_mode = configs.get("model_infos", {}).get("brepmfr_train_mode", "supervised")
    divide_data_into_splits()
    step2graph_mfr_batch()
    json_to_bin_batch()
    check_and_clean_invalid()

    # 对抗学习无label数据：独立路径的构图/转bin/清理
    mfr_data_infos = configs['data_path_infos'].get('mfr_data_infos', {})
    if train_mode == "domain_adapt" and mfr_data_infos.get('adv_unlabeled_step_data'):
        # step2graph_mfr_nolabel_batch()
        # json_to_bin_batch(path_set="adv_unlabeled")
        # check_and_clean_invalid(path_set="adv_unlabeled")
        generate_domain_adapt_splits()

    divide_data_into_splits()


if __name__ == "__main__":
    config = load_config_basic()
    if config['model_infos']['model_name'] == "brepMFR":
        data_processing_workflow_mfr()
    else:
        data_processing_workflow()