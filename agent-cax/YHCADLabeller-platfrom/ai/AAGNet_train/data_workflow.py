
from .base_functions import load_config_basic
from .data_utils.real_data_generate_labels import main as generate_real_data_labels
from .data_utils.public_data_generate_labels import process_round_json_files as generate_public_data_labels
from .data_utils.divide_train_val_test import split_dataset_to_txt as divide_data_into_splits
from .data_utils.step2graph_ncti import step2graph_batch


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
