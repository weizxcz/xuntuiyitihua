"""
BrepMFR 训练器（Geo-Rec 新架构）

- 该模块封装 BrepMFR 的训练入口，包含普通监督训练和域适应训练；
- 数据加载使用 `CADSynth`（统一训练）和 `TransferDataset`（域迁移）；
- 模型定义使用 `BrepSeg`（基础分割）和 `DomainAdapt`（域适应对抗训练）。
"""
import os
import pathlib
import time
import logging
import argparse
import torch
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint
from pytorch_lightning.loggers import TensorBoardLogger

from src.utils.base_functions import load_config_basic, load_yaml
from src.data_utils.dataloader.brepmfr_dataset import CADSynth, TransferDataset
from src.models.brepMFR import BrepSeg, DomainAdapt


def _build_args_from_config():
    """从 config 构建 BrepSeg 所需的 args 对象

    逻辑：
    1. 读取基础配置和模型配置文件路径；
    2. 根据是否使用绝对路径，调整数据路径、分割文件路径、检查点路径；
    3. 将配置映射为 args 结构体，供 BrepSeg 和 Trainer 使用。
    """
    config = load_config_basic()

    # 默认模型配置文件路径，可在配置中覆盖
    model_config_path = config['model_infos'].get('brepmfr_config_path') or 'configs/model_configs/brepMFR/round_model_config.yaml'
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    if not config['data_path_infos']['use_absolute_path']:
        # 将相对路径转换为绝对路径
        model_config_path = os.path.join(base_dir, model_config_path)
    model_config = load_yaml(model_config_path)

    # 数据路径与输出路径
    processed_data = config['data_path_infos']['processed_data']
    splits_dir = config['data_path_infos']['divide_data_infos']['divide_result_txt_save_dir']
    checkpoint_dir = config['model_infos'].get('brepmfr_checkpoint_dir', 'results/BrepMFR')
    if not config['data_path_infos']['use_absolute_path']:
        processed_data = os.path.join(base_dir, processed_data)
        splits_dir = os.path.join(base_dir, splits_dir)
        checkpoint_dir = os.path.join(base_dir, checkpoint_dir)

    # 将参数组织为一个简单对象
    class Args:
        pass

    args = Args()
    args.num_classes = model_config.get('num_classes', 25)
    args.batch_size = model_config.get('batch_size', 32)
    args.num_workers = model_config.get('num_workers', 0)
    args.dropout = model_config.get('dropout', 0.3)
    args.attention_dropout = model_config.get('attention_dropout', 0.3)
    args.act_dropout = model_config.get('act_dropout', 0.3)
    args.d_model = model_config.get('d_model', 512)
    args.dim_node = model_config.get('dim_node', 256)
    args.n_heads = model_config.get('n_heads', 32)
    args.n_layers_encode = model_config.get('n_layers_encode', 8)
    args.dataset_path = processed_data
    args.splits_dir = splits_dir
    args.checkpoint_dir = checkpoint_dir
    args.experiment_name = "BrepMFR1"
    args.checkpoint = None
    args.traintest = "train"

    # 返回参数结构+模型配置，供训练入口调用
    return args, model_config


def _build_domain_adapt_args_from_config():
    """构建域适应训练所需参数

    处理流程：
    1. 读取基础配置和 brepmfr 通用配置；
    2. 从 mfr_data_infos 中读取源域、目标域、分割记录目录等；
    3. 支持绝对路径和相对路径；
    4. 将参数写入 args 并返回。
    """
    config = load_config_basic()
    args, model_config = _build_args_from_config()  # 继承通用参数

    mfr_data_infos = config["data_path_infos"]["mfr_data_infos"]
    divide_infos = config["data_path_infos"]["divide_data_infos"]
    use_absolute = config["data_path_infos"]["use_absolute_path"]
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # 源域和目标域 bin 文件目录
    source_bin_root = mfr_data_infos.get("bin_data")
    target_bin_root = mfr_data_infos.get("adv_unlabeled_bin_data", source_bin_root)

    # 域适应 split 文件目录（用于划分 source/target 的训练/验证/测试 ID）
    domain_adapt_split_dir = mfr_data_infos.get(
        "domain_adapt_split_dir",
        os.path.join(config["data_path_infos"]["processed_data"], "domain_adapt_splits"),
    )

    # 预训练检查点（实验上下文）
    pre_train_ckpt = config["model_infos"].get("brepmfr_pretrain_ckpt") or config["model_infos"].get("model_save_path")
    # 开放集（open_set）开关：若1则丢弃超出 num_classes 的标签
    open_set = int(mfr_data_infos.get("domain_adapt_open_set", 0))

    if not use_absolute:
        source_bin_root = os.path.join(base_dir, source_bin_root)
        target_bin_root = os.path.join(base_dir, target_bin_root)
        domain_adapt_split_dir = os.path.join(base_dir, domain_adapt_split_dir)
        if pre_train_ckpt:
            pre_train_ckpt = os.path.join(base_dir, pre_train_ckpt)

    # 赋值到 args
    args.source_path = source_bin_root
    args.target_path = target_bin_root
    args.domain_adapt_split_dir = domain_adapt_split_dir
    args.pre_train = pre_train_ckpt
    args.open_set = open_set
    args.max_epochs = model_config.get("domain_adapt_max_epochs", model_config.get("max_epochs", 150))
    args.domain_adapt_experiment_name = model_config.get("domain_adapt_experiment_name", "BrepMFR_DA")
    args.random_seed = divide_infos.get("random_seed", 42)

    return args, model_config


def brepmfr_trainer_module():
    """BrepMFR 训练入口（普通监督训练）

    流程：
    1. 构建参数 args + model_config；
    2. 创建保存 checkpoint 的目录（按时间戳划分）；
    3. 配置 Trainer（回调、日志、加速器、最大 epoch 等）；
    4. 构建模型 BrepSeg；
    5. 构建 CADSynth 数据集与 DataLoader；
    6. 运行 trainer.fit。
    """
    torch.backends.cudnn.enabled = True
    torch.backends.cudnn.benchmark = True

    # 读取配置并创建保存目录
    args, model_config = _build_args_from_config()
    os.makedirs(args.checkpoint_dir, exist_ok=True)

    # 训练结果按日期和时间保存到子目录，方便多次试验管理
    month_day = time.strftime("%m%d")
    hour_min_second = time.strftime("%H%M%S")
    run_dir = pathlib.Path(args.checkpoint_dir) / month_day / hour_min_second
    run_dir.mkdir(parents=True, exist_ok=True)

    # 最佳模型 checkpoint 回调（根据 eval_loss）
    checkpoint_callback = ModelCheckpoint(
        monitor="eval_loss",
        dirpath=str(run_dir),
        filename="best",
        save_top_k=10,
        save_last=True,
    )

    # 初始化 Trainer
    trainer = Trainer(
        callbacks=[checkpoint_callback],
        logger=TensorBoardLogger(str(args.checkpoint_dir), name=month_day, version=hour_min_second),
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        devices=1 if torch.cuda.is_available() else None,
        gradient_clip_val=1.0,
        max_epochs=model_config.get("max_epochs", 150),
    )

    # 初始化模型
    model = BrepSeg(args)

    # 初始化数据集和数据加载器（训练/验证）
    train_data = CADSynth(
        root_dir=args.dataset_path,
        split="train",
        random_rotate=True,
        num_class=args.num_classes,
        splits_dir=args.splits_dir,
    )
    val_data = CADSynth(
        root_dir=args.dataset_path,
        split="val",
        random_rotate=False,
        num_class=args.num_classes,
        splits_dir=args.splits_dir,
    )
    train_loader = train_data.get_dataloader(
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )
    val_loader = val_data.get_dataloader(
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    # 日志信息
    logging.info(
        f"BrepMFR 训练开始，日志: {run_dir}\n"
        f"tensorboard --logdir {run_dir}"
    )

    # 启动训练
    trainer.fit(model, train_loader, val_loader)


def brepmfr_domain_adapt_trainer_module():
    """
    该函数负责域自适应训练流程：
    - 加载 domain adapt 专用参数（源域/目标域数据路径、预训练 checkpoint、开放集配置）；
    - 初始化 Lightning Trainer（回调、日志、加速器、最大 epoch）；
    - 创建 DomainAdapt 模型；
    - 构造 TransferDataset（源域 + 目标域）并加载数据；
    - 执行 trainer.fit。
    """
    torch.backends.cudnn.enabled = True
    torch.backends.cudnn.benchmark = True

    # 读取 domain adapt 参数
    args, model_config = _build_domain_adapt_args_from_config()
    os.makedirs(args.checkpoint_dir, exist_ok=True)

    # 训练结果按时间戳目录保存
    month_day = time.strftime("%m%d")
    hour_min_second = time.strftime("%H%M%S")
    run_dir = pathlib.Path(args.checkpoint_dir) / month_day / hour_min_second
    run_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_callback = ModelCheckpoint(
        monitor="eval_loss",
        dirpath=str(run_dir),
        filename="best",
        save_top_k=10,
        save_last=True,
    )

    trainer = Trainer(
        callbacks=[checkpoint_callback],
        logger=TensorBoardLogger(str(args.checkpoint_dir), name=month_day, version=hour_min_second),
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        devices=1 if torch.cuda.is_available() else None,
        gradient_clip_val=1.0,
        max_epochs=args.max_epochs,
    )

    # 域适应模型实例（含预训练初始化）
    model = DomainAdapt(args)

    # 训练集和验证集都使用 TransferDataset（源域 + 目标域数据对）
    train_data = TransferDataset(
        root_dir_source=args.source_path,
        root_dir_target=args.target_path,
        split="train",
        random_rotate=True,
        num_class=args.num_classes,
        open_set=args.open_set,
        source_splits_dir=args.domain_adapt_split_dir,
        target_splits_dir=args.domain_adapt_split_dir,
    )

    val_data = TransferDataset(
        root_dir_source=args.source_path,
        root_dir_target=args.target_path,
        split="val",
        random_rotate=False,
        num_class=args.num_classes,
        open_set=args.open_set,
        source_splits_dir=args.domain_adapt_split_dir,
        target_splits_dir=args.domain_adapt_split_dir,
    )

    train_loader = train_data.get_dataloader(
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )
    val_loader = val_data.get_dataloader(
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    logging.info(
        f"BrepMFR Domain Adapt 训练开始，日志: {run_dir}\n"
        f"source={args.source_path}\n"
        f"target={args.target_path}\n"
        f"split_dir={args.domain_adapt_split_dir}\n"
        f"pretrain={args.pre_train}"
    )

    # 开始域适应训练
    trainer.fit(model, train_loader, val_loader)


def brepmfr_test_module(checkpoint_path=None):
    """BrepMFR 测试入口"""
    args, model_config = _build_args_from_config()
    if checkpoint_path:
        args.checkpoint = checkpoint_path

    assert args.checkpoint, "测试需要提供 checkpoint 路径"

    torch.serialization.add_safe_globals([argparse.Namespace])
    model = BrepSeg.load_from_checkpoint(
        args.checkpoint,
        map_location="cuda:0" if torch.cuda.is_available() else "cpu",
    )

    test_data = CADSynth(
        root_dir=args.dataset_path,
        split="test",
        random_rotate=False,
        num_class=args.num_classes,
        splits_dir=args.splits_dir,
    )
    test_loader = test_data.get_dataloader(
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=0,
    )

    trainer = Trainer(
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        devices=1 if torch.cuda.is_available() else None,
    )
    trainer.test(model, dataloaders=[test_loader], ckpt_path=args.checkpoint, verbose=False)
