
import os
import shutil
from datetime import datetime
from tqdm import tqdm
import logging
import torch
from torch import nn
import numpy as np
from torch_ema import ExponentialMovingAverage
from torchmetrics.classification import (
    MulticlassAccuracy,
    BinaryAccuracy,
    BinaryF1Score,
    BinaryJaccardIndex,
    MulticlassJaccardIndex)
from .base_functions import load_yaml,load_config_basic,append_metrics
from .data_utils.aagnet_dataloader import MFInstSegDataset_single_graph
from .models.inst_segmentors import AAGNetSegmentor

def dataloader_module():
    config = load_config_basic()
    processed_dataset = config['data_path_infos']['processed_data']
    labels_dir = config['data_path_infos']['processed_label_data']
    model_config_path = config['model_infos']['model_config_path']
    model_config = load_yaml(model_config_path)
    # 数据增强配置：center_and_scale（居中+缩放，归一化坐标系，train/val 都做）；
    # random_rotate（随机旋转增强，只对 train 做以扩充数据，val 固定 False 保证评估稳定可复现）。
    center_and_scale = model_config.get('center_and_scale', True)
    random_rotate = model_config.get('random_rotate', False)
    train_dataset = MFInstSegDataset_single_graph(root_dir=processed_dataset, split='train',
                                     center_and_scale=center_and_scale, normalize=True, random_rotate=random_rotate,
                                     num_threads=0, labels_dir=labels_dir)
    val_dataset = MFInstSegDataset_single_graph(root_dir=processed_dataset, split='val',
                                   center_and_scale=center_and_scale, normalize=True, random_rotate=False,
                                   num_threads=0, labels_dir=labels_dir)
    train_loader = train_dataset.get_dataloader(batch_size=model_config.get('batch_size'),
                                                 shuffle=True, drop_last=False, pin_memory=True)
    val_loader = val_dataset.get_dataloader(batch_size=model_config.get('batch_size'),shuffle=False, drop_last=False,
                                            pin_memory=True)
    return train_loader,val_loader


def model_module():
    config = load_config_basic()
    model_config_path = config['model_infos']['model_config_path']
    model_config = load_yaml(model_config_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AAGNetSegmentor(num_classes=model_config.get('n_classes'),
                            arch=model_config.get('architecture'),
                            edge_attr_dim=model_config.get('edge_attr_dim'),
                            node_attr_dim=model_config.get('node_attr_dim'),
                            edge_attr_emb=model_config.get('edge_attr_emb'),
                            node_attr_emb=model_config.get('node_attr_emb'),
                            edge_grid_dim=model_config.get('edge_grid_dim'),
                            node_grid_dim=model_config.get('node_grid_dim'),
                            edge_grid_emb=model_config.get('edge_grid_emb'),
                            node_grid_emb=model_config.get('node_grid_emb'),
                            num_layers=model_config.get('num_layers'),
                            delta=model_config.get('delta'),
                            mlp_ratio=model_config.get('mlp_ratio'),
                            drop=model_config.get('drop'),
                            drop_path=model_config.get('drop_path'),
                            head_hidden_dim=model_config.get('head_hidden_dim'),
                            conv_on_edge=model_config.get('conv_on_edge'),
                            use_uv_gird=model_config.get('use_uv_gird'),
                            use_edge_attr=model_config.get('use_edge_attr'),
                            use_face_attr=model_config.get('use_face_attr'),)
    model = model.to(device)
    return model, model_config

def init_metrics(n_classes,device):
    seg_acc = MulticlassAccuracy(num_classes=n_classes).to(device)
    inst_acc = BinaryAccuracy().to(device)
    bottom_acc = BinaryAccuracy().to(device)

    seg_iou = MulticlassJaccardIndex(num_classes=n_classes).to(device)
    inst_f1 = BinaryF1Score().to(device)
    bottom_iou = BinaryJaccardIndex().to(device)
    return seg_acc, inst_acc, bottom_acc, seg_iou, inst_f1, bottom_iou

def _copy_attr_stat_next_to_model(processed_dataset, model_saved_path):
    """训练结束后，把归一化统计量 attr_stat.json 复制到模型所在目录，
    并重命名为与模型同名（只把 .pth 后缀换成 .json），方便推理端"选择预训练模型"
    在同目录按同名自动匹配到该 json。"""
    stat_src = os.path.join(processed_dataset, "attr_stat.json")
    if not os.path.exists(stat_src):
        logging.warning(f"未找到 attr_stat.json（{stat_src}），跳过复制到模型目录")
        return
    model_dir = os.path.dirname(model_saved_path)
    os.makedirs(model_dir, exist_ok=True)
    # 与模型同名：<特征>_best_model.pth -> <特征>_best_model.json
    stat_dst = os.path.join(model_dir, os.path.splitext(os.path.basename(model_saved_path))[0] + ".json")
    try:
        shutil.copy(stat_src, stat_dst)
        logging.info(f"已复制并改名为 {os.path.basename(stat_dst)} 到模型目录: {stat_dst}")
    except OSError as e:
        logging.warning(f"复制 attr_stat.json 到模型目录失败: {e}")


def trainer_module():
    config = load_config_basic()
    processed_dataset = config['data_path_infos']['processed_data']

    # 自动生成带日期时间的模型保存路径
    model_save_dir = config['model_infos'].get('model_save_dir',
                    os.path.dirname(os.path.dirname(config['model_infos'].get('model_save_path', ''))))
    timestamp = datetime.now().strftime("%m%d_%H%M")
    model_filename = config['model_infos'].get('model_filename', 'best_model.pth')
    model_saved_path = os.path.join(model_save_dir, timestamp, model_filename)
    os.makedirs(os.path.dirname(model_saved_path), exist_ok=True)
    logging.info(f"模型保存路径: {model_saved_path}")
    metrics_path = config['logs_infos']['metrics_path']
    if os.path.exists(metrics_path):
        os.remove(metrics_path)
    train_loader,val_loader = dataloader_module()
    model, model_config = model_module()
    seg_loss = nn.CrossEntropyLoss()
    instance_loss = nn.BCEWithLogitsLoss()
    bottom_loss = nn.BCEWithLogitsLoss()
    opt = torch.optim.AdamW(model.parameters(), lr=model_config.get("lr"), weight_decay=model_config.get("weight_decay"))
    n_classes = model_config.get('n_classes')
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # epochs 优先取 GUI 弹窗传入的环境变量覆盖（AAGNET_TRAIN_EPOCHS），否则用 yaml 配置
    epochs = model_config.get('epochs')
    gui_epochs = os.environ.get("AAGNET_TRAIN_EPOCHS")
    if gui_epochs is not None:
        try:
            epochs = int(gui_epochs)
        except ValueError:
            logging.warning(f"AAGNET_TRAIN_EPOCHS 值无效（{gui_epochs}），回退使用 yaml 的 epochs={epochs}")
    if not isinstance(epochs, int) or epochs <= 0:
        raise ValueError(f"epochs 必须为正整数，当前为 {epochs!r}")

    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs, eta_min=0)

    train_seg_acc, train_inst_acc, train_bottom_acc, train_seg_iou, train_inst_f1, train_bottom_iou = init_metrics(n_classes, device)
    val_seg_acc, val_inst_acc, val_bottom_acc, val_seg_iou, val_inst_f1, val_bottom_iou = init_metrics(n_classes, device)
    iters = len(train_loader)
    if iters == 0:
        raise RuntimeError(
            "训练集为空（train_loader 没有 batch），无法训练。请检查划分结果："
            "训练集至少需要 1 个样本，且 batch_size 不能大于训练样本数。"
        )
    ema_decay = model_config.get("ema_decay_per_epoch") ** (1 / iters)
    ema = ExponentialMovingAverage(model.parameters(), decay=ema_decay)
    best_acc = 0.
    for epoch in range(epochs):
        logging.info(f'------------- Now start epoch {epoch}------------- ')
        model.train()
        train_losses = []
        train_bar = tqdm(train_loader)
        for data in train_bar:
            graphs = data["graph"].to(device, non_blocking=True)
            inst_label = data["inst_labels"].to(device, non_blocking=True)
            seg_label = graphs.ndata["seg_y"]
            bottom_label = graphs.ndata["bottom_y"]
            # Zero the gradients
            opt.zero_grad(set_to_none=True)
            # Forward pass
            seg_pred, inst_pred, bottom_pred = model(graphs)
            loss_seg = seg_loss(seg_pred, seg_label)
            # loss_seg = 0

            # 计算实例分割损失，只使用上三角部分
            batch_num_nodes = graphs.batch_num_nodes().tolist()
            upper_preds, valid_mask = model.inst_head.extract_upper_triangular(inst_pred, batch_num_nodes)
            upper_targets, _ = model.inst_head.extract_upper_triangular(inst_label.float(), batch_num_nodes)
            # 只计算有效位置的损失
            valid_preds = upper_preds[valid_mask]
            valid_targets = upper_targets[valid_mask]
            loss_inst = instance_loss(valid_preds, valid_targets)
            loss_bottom = bottom_loss(bottom_pred, bottom_label)
            loss = model_config.get("seg_a") * loss_seg + \
                   model_config.get("inst_a") * loss_inst + \
                   model_config.get("bottom_a") * loss_bottom
            train_losses.append(loss.item())

            lr = opt.param_groups[0]["lr"]
            info = "Epoch:%d LR:%f Seg:%f Inst:%f Bottom:%f Total:%f" % (
                epoch, lr, loss_seg, loss_inst, loss_bottom, loss)
            train_bar.set_description(info)
            # # Backward pass
            loss.backward()
            opt.step()
            # Update the moving average with the new parameters from the last optimizer step
            ema.update()
            train_seg_acc.update(seg_pred, seg_label)
            train_seg_iou.update(seg_pred, seg_label)
            # 使用上三角部分计算实例分割指标
            train_inst_acc.update(valid_preds, valid_targets.float())
            train_inst_f1.update(valid_preds, valid_targets.float())
            train_bottom_acc.update(bottom_pred, bottom_label)
            train_bottom_iou.update(bottom_pred, bottom_label)

        scheduler.step()
        # batch end
        mean_train_loss = np.mean(train_losses).item()
        mean_train_seg_acc = train_seg_acc.compute().item()
        mean_train_seg_iou = train_seg_iou.compute().item()
        mean_train_inst_acc = train_inst_acc.compute().item()
        mean_train_inst_f1 = train_inst_f1.compute().item()
        mean_train_bottom_acc = train_bottom_acc.compute().item()
        mean_train_bottom_iou = train_bottom_iou.compute().item()
        logging.info(f'train_loss : {mean_train_loss}, \
                      train_seg_acc: {mean_train_seg_acc}, \
                      train_seg_iou: {mean_train_seg_iou}, \
                      train_inst_acc: {mean_train_inst_acc}, \
                      train_inst_f1: {mean_train_inst_f1}, \
                      train_bottom_acc: {mean_train_bottom_acc}, \
                      train_bottom_iou: {mean_train_bottom_iou}')
        train_seg_acc.reset()
        train_inst_acc.reset()
        train_bottom_acc.reset()
        train_seg_iou.reset()
        train_inst_f1.reset()
        train_bottom_iou.reset()
        with torch.no_grad():
            with ema.average_parameters():
                model.eval()
                val_losses = []
                for data in tqdm(val_loader):
                    graphs = data["graph"].to(device)
                    inst_label = data["inst_labels"].to(device)
                    seg_label = graphs.ndata["seg_y"]
                    bottom_label = graphs.ndata["bottom_y"]
                    # CPU 只支持 bfloat16，GPU 支持 float16
                    autocast_dtype = torch.bfloat16 if device.type == "cpu" else torch.float16
                    with torch.autocast(device_type=device.type, dtype=autocast_dtype):
                        seg_pred, inst_pred, bottom_pred = model(graphs)
                        # loss_seg = seg_loss(seg_pred, seg_label)
                        loss_seg = 0
                        # 计算实例分割损失，只使用上三角部分
                        batch_num_nodes = graphs.batch_num_nodes().tolist()
                        upper_preds, valid_mask = model.inst_head.extract_upper_triangular(inst_pred, batch_num_nodes)
                        upper_targets, _ = model.inst_head.extract_upper_triangular(inst_label.float(), batch_num_nodes)
                        # 只计算有效位置的损失
                        valid_preds = upper_preds[valid_mask]
                        valid_targets = upper_targets[valid_mask]
                        loss_inst = instance_loss(valid_preds, valid_targets)
                        loss_bottom = bottom_loss(bottom_pred, bottom_label)
                        loss = model_config.get("seg_a") * loss_seg + \
                            model_config.get("inst_a") * loss_inst + \
                            model_config.get("bottom_a") * loss_bottom
                    val_losses.append(loss.item())
                    val_seg_acc.update(seg_pred, seg_label)
                    val_seg_iou.update(seg_pred, seg_label)
                    # 使用上三角部分计算实例分割指标
                    val_inst_acc.update(valid_preds, valid_targets.float())
                    val_inst_f1.update(valid_preds, valid_targets.float())
                    val_bottom_acc.update(bottom_pred, bottom_label)
                    val_bottom_iou.update(bottom_pred, bottom_label)
                mean_val_loss = np.mean(val_losses).item()
                mean_val_seg_acc = val_seg_acc.compute().item()
                mean_val_seg_iou = val_seg_iou.compute().item()
                mean_val_inst_acc = val_inst_acc.compute().item()
                mean_val_inst_f1 = val_inst_f1.compute().item()
                mean_val_bottom_acc = val_bottom_acc.compute().item()
                mean_val_bottom_iou = val_bottom_iou.compute().item()
                logging.info(f'val_loss : {mean_val_loss}, \
                            val_seg_acc: {mean_val_seg_acc}, \
                            val_seg_iou: {mean_val_seg_iou}, \
                            val_inst_acc: {mean_val_inst_acc}, \
                            val_inst_f1: {mean_val_inst_f1}, \
                            val_bottom_acc: {mean_val_bottom_acc}, \
                            val_bottom_iou: {mean_val_bottom_iou}')
                val_seg_acc.reset()
                val_seg_iou.reset()
                val_inst_acc.reset()
                val_inst_f1.reset()
                val_bottom_acc.reset()
                val_bottom_iou.reset()
                cur_acc = mean_val_seg_iou + mean_val_inst_f1 + mean_val_bottom_iou
                append_metrics({
                    "epoch": epoch,
                    "train_loss": mean_train_loss,
                    "val_loss": mean_val_loss,
                    "train_seg_acc": mean_train_seg_acc,
                    "val_seg_acc": mean_val_seg_acc,
                    "train_seg_iou": mean_train_seg_iou,
                    "val_seg_iou": mean_val_seg_iou,
                    "train_inst_f1": mean_train_inst_f1,
                    "val_inst_f1": mean_val_inst_f1,
                    "train_bottom_iou": mean_train_bottom_iou,
                    "val_bottom_iou": mean_val_bottom_iou,
                })
                if cur_acc > best_acc:
                    best_acc = cur_acc
                    logging.info(f'best metric: {cur_acc}, model saved in epoch {epoch}')
                    torch.save(model.state_dict(), model_saved_path)

    # 训练结束后，把归一化统计量 attr_stat.json 复制到模型目录，与 best_model.pth 同文件夹，
    # 方便推理端"选择预训练模型"时一同定位（即使不同名也能在同目录找到）
    _copy_attr_stat_next_to_model(processed_dataset, model_saved_path)
