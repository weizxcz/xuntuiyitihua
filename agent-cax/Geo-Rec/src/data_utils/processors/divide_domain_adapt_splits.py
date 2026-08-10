import os
import random
from pathlib import Path

from src.utils.base_functions import load_config_basic


def _split_list(items, train_ratio, val_ratio):
    n = len(items)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    train_items = items[:n_train]
    val_items = items[n_train:n_train + n_val]
    test_items = items[n_train + n_val:]
    return train_items, val_items, test_items


def _write_list(path, values):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in values:
            f.write(str(item) + "\n")


def generate_domain_adapt_splits():
    """
    生成 Domain Adapt 训练需要的:
    s_train/s_val/s_test.txt 与 t_train/t_val/t_test.txt
    """
    config = load_config_basic()
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config["data_path_infos"]["use_absolute_path"]
    data_infos = config["data_path_infos"]
    mfr_infos = data_infos["mfr_data_infos"]
    divide_infos = data_infos["divide_data_infos"]

    source_split_dir = divide_infos["divide_result_txt_save_dir"]
    target_bin_dir = mfr_infos.get("adv_unlabeled_bin_data", mfr_infos["bin_data"])
    output_split_dir = mfr_infos.get(
        "domain_adapt_split_dir",
        os.path.join(data_infos["processed_data"], "domain_adapt_splits"),
    )

    if not use_absolute:
        source_split_dir = os.path.join(base_dir, source_split_dir)
        target_bin_dir = os.path.join(base_dir, target_bin_dir)
        output_split_dir = os.path.join(base_dir, output_split_dir)

    s_train = Path(source_split_dir) / "train.txt"
    s_val = Path(source_split_dir) / "val.txt"
    s_test = Path(source_split_dir) / "test.txt"
    if not (s_train.exists() and s_val.exists() and s_test.exists()):
        raise FileNotFoundError("未找到 source train/val/test 划分文件")

    # source: 直接复用已生成的 train/val/test，复制为 s_*
    for src_name, dst_name in [("train.txt", "s_train.txt"), ("val.txt", "s_val.txt"), ("test.txt", "s_test.txt")]:
        src_file = Path(source_split_dir) / src_name
        dst_file = Path(output_split_dir) / dst_name
        with open(src_file, "r", encoding="utf-8") as f:
            ids = [x.strip() for x in f.readlines() if x.strip()]
        _write_list(str(dst_file), ids)

    # target: 从无label bin目录自动划分生成 t_*
    all_target_ids = [p.stem for p in Path(target_bin_dir).rglob("*.bin")]
    random_seed = divide_infos.get("random_seed", 42)
    random.Random(random_seed).shuffle(all_target_ids)
    t_train, t_val, t_test = _split_list(
        all_target_ids,
        divide_infos.get("train_ratio", 0.8),
        divide_infos.get("val_ratio", 0.1),
    )
    _write_list(str(Path(output_split_dir) / "t_train.txt"), t_train)
    _write_list(str(Path(output_split_dir) / "t_val.txt"), t_val)
    _write_list(str(Path(output_split_dir) / "t_test.txt"), t_test)

    return {
        "split_dir": str(output_split_dir),
        "source_counts": {
            "train": len(open(s_train, "r", encoding="utf-8").read().splitlines()),
            "val": len(open(s_val, "r", encoding="utf-8").read().splitlines()),
            "test": len(open(s_test, "r", encoding="utf-8").read().splitlines()),
        },
        "target_counts": {"train": len(t_train), "val": len(t_val), "test": len(t_test)},
    }
