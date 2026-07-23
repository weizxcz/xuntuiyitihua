import os
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
from src.utils.base_functions import load_yaml,load_config_basic
from src.data_utils.dataloader.aagnet_dataloader import MFInstSegDataset_single_graph
from src.models.aagnet.inst_segmentors import AAGNetSegmentor

def dataloader_module():
    config = load_config_basic()
    use_absolute_path = config['data_path_infos']['use_absolute_path']
    processed_dataset = config['data_path_infos']['processed_data']
    labels_dir = config['data_path_infos']['processed_label_data']
    model_config_path = config['model_infos']['model_config_path']
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not use_absolute_path:
        processed_dataset = os.path.join(base_dir, processed_dataset)
        model_config_path = os.path.join(base_dir, model_config_path)
        labels_dir = os.path.join(base_dir, labels_dir)
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
    train_loader = train_dataset.get_dataloader(batch_size=model_config.get('batch_size'), pin_memory=True)
    val_loader = val_dataset.get_dataloader(batch_size=model_config.get('batch_size'),shuffle=False, drop_last=False,
                                            pin_memory=True)
    return train_loader,val_loader


def model_module():
    config = load_config_basic()
    use_absolute_path = config['data_path_infos']['use_absolute_path']
    model_config_path = config['model_infos']['model_config_path']
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not use_absolute_path:
        model_config_path = os.path.join(base_dir, model_config_path)
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

def trainer_module():
    config = load_config_basic()
    use_absolute_path = config['data_path_infos']['use_absolute_path']

    # 自动生成带日期时间的模型保存路径
    model_save_dir = config['model_infos'].get('model_save_dir',
                    os.path.dirname(os.path.dirname(config['model_infos'].get('model_save_path', ''))))
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not use_absolute_path:
        model_save_dir = os.path.join(base_dir, model_save_dir)
    timestamp = datetime.now().strftime("%m%d_%H%M")
    model_saved_path = os.path.join(model_save_dir, timestamp, "best_model.pth")
    os.makedirs(os.path.dirname(model_saved_path), exist_ok=True)
    logging.info(f"模型保存路径: {model_saved_path}")
    train_loader,val_loader = dataloader_module()
    model, model_config = model_module()
    seg_loss = nn.CrossEntropyLoss()
    instance_loss = nn.BCEWithLogitsLoss()
    bottom_loss = nn.BCEWithLogitsLoss()
    opt = torch.optim.AdamW(model.parameters(), lr=model_config.get("lr"), weight_decay=model_config.get("weight_decay"))
    n_classes = model_config.get('n_classes')
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=model_config.get("epochs"), eta_min=0)

    train_seg_acc, train_inst_acc, train_bottom_acc, train_seg_iou, train_inst_f1, train_bottom_iou = init_metrics(n_classes, device)
    val_seg_acc, val_inst_acc, val_bottom_acc, val_seg_iou, val_inst_f1, val_bottom_iou = init_metrics(n_classes, device)
    iters = len(train_loader)
    ema_decay = model_config.get("ema_decay_per_epoch") ** (1 / iters)
    ema = ExponentialMovingAverage(model.parameters(), decay=ema_decay)
    best_acc = 0.
    for epoch in range(model_config.get('epochs')):
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
                if cur_acc > best_acc:
                    best_acc = cur_acc
                    logging.info(f'best metric: {cur_acc}, model saved in epoch {epoch}')
                    torch.save(model.state_dict(), model_saved_path)