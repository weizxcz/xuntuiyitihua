# Geo-Rec 训练入口脚本
# 主要逻辑：根据配置选择模型和训练模式

from src.utils.base_functions import setup_logging, load_config_basic
from src.data_workflow import data_processing_workflow, data_processing_workflow_mfr
from src.trainers.aagnet_train import trainer_module
from src.trainers.brepmfr_train import brepmfr_trainer_module, brepmfr_domain_adapt_trainer_module
if __name__ == "__main__":
    setup_logging()
    config = load_config_basic()
    model_name = config['model_infos']['model_name']
    if model_name == "brepMFR":
        # data_processing_workflow_mfr() 
        train_mode = config.get("model_infos", {}).get("brepmfr_train_mode", "supervised")
        if train_mode == "domain_adapt":
            brepmfr_domain_adapt_trainer_module()
        else:
            brepmfr_trainer_module()
    else:
        data_processing_workflow()
        trainer_module()