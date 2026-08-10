# -*- coding: utf-8 -*-
import numpy as np
import pytorch_lightning as pl
import torch
from torch import nn
import torch.nn.functional as F

from .modules.domain_adv.domain_discriminator import DomainDiscriminator
from .modules.domain_adv.dann import DomainAdversarialLoss
from .brepseg_model import BrepSeg


def cross_entropy_loss(label, predict_prob, epsilon=1e-12):
    n, c = label.size()
    n_pred, c_pred = predict_prob.size()
    assert n == n_pred and c == c_pred, "dimension mismatch"
    ce = -label * torch.log(predict_prob + epsilon)
    return torch.sum(ce) / float(n)


def entropy_loss(predict_prob, epsilon=1e-20):
    n, _ = predict_prob.size()
    entropy = -predict_prob * torch.log(predict_prob + epsilon)
    return torch.sum(entropy) / float(n)


class DomainAdapt(pl.LightningModule):
    """BrepMFR 对抗学习模型，来源于 BrepMFR-main/domain_adapt.py 迁移版。"""

    def __init__(self, args):
        super().__init__()
        self.save_hyperparameters()
        self.num_classes = args.num_classes

        if not args.pre_train:
            raise ValueError("DomainAdapt 训练需要 pre_train checkpoint")
        pre_trained_model = BrepSeg.load_from_checkpoint(args.pre_train, args=args)
        self.brep_encoder = pre_trained_model.brep_encoder
        self.attention = pre_trained_model.attention
        self.classifier = pre_trained_model.classifier

        domain_discri = DomainDiscriminator(args.dim_node, hidden_size=512)
        self.domain_adv = DomainAdversarialLoss(domain_discri)

        self.pred_s, self.label_s = [], []
        self.pred_t, self.label_t = [], []

    def _forward_split(self, batch):
        """前向传播并分离源域和目标域特征。

        处理联合批次（源域+目标域），提取节点和图嵌入，
        分离为源域和目标域部分，并通过注意力机制融合后分类。

        参数:
            batch: 联合批次数据（源域+目标域拼接）

        返回值:
            z_s: 源域融合特征
            z_t: 目标域融合特征
            node_seg_s: 源域节点分类概率
            node_seg_t: 目标域节点分类概率
        """
        # 1. 编码器提取节点和图嵌入
        node_emb, graph_emb = self.brep_encoder(batch, last_state_only=True)
        # 调整维度：去掉全局节点，取有效节点嵌入
        node_emb = node_emb[0].permute(1, 0, 2)[:, 1:, :]
        # 分离源域和目标域节点嵌入（批次前半源域，后半目标域）
        node_emb_s, node_emb_t = node_emb.chunk(2, dim=0)
        # 分离填充掩码
        padding_mask_s, padding_mask_t = batch["padding_mask"].chunk(2, dim=0)

        # 筛选有效节点（非填充部分）
        node_z_s = node_emb_s[torch.where(padding_mask_s == False)]
        node_z_t = node_emb_t[torch.where(padding_mask_t == False)]

        # 分离图级嵌入
        graph_emb_s, graph_emb_t = graph_emb.chunk(2, dim=0)
        # 计算每图有效节点数
        num_nodes_s = torch.sum((~padding_mask_s).long(), dim=-1)
        num_nodes_t = torch.sum((~padding_mask_t).long(), dim=-1)
        # 扩展图嵌入以匹配节点数
        graph_z_s = graph_emb_s.repeat_interleave(num_nodes_s, dim=0).to(graph_emb.device)
        graph_z_t = graph_emb_t.repeat_interleave(num_nodes_t, dim=0).to(graph_emb.device)

        # 注意力融合节点和图特征
        z_s = self.attention([node_z_s, graph_z_s])
        z_t = self.attention([node_z_t, graph_z_t])
        # 分类器输出概率
        node_seg_s = self.classifier(z_s)
        node_seg_t = self.classifier(z_t)
        return z_s, z_t, node_seg_s, node_seg_t

    def training_step(self, batch, batch_idx):
        self.brep_encoder.train()
        self.attention.train()
        self.classifier.train()
        self.domain_adv.train()

        z_s, z_t, node_seg_s, node_seg_t = self._forward_split(batch)
        num_node_s = node_seg_s.size(0)
        num_node_t = node_seg_t.size(0)

        label_s = batch["label_feature"][:num_node_s].long()
        
        if self.num_classes == 2:
            # For binary classification, use BCEWithLogitsLoss
            labels_float = label_s.float().unsqueeze(1)  # [total_nodes, 1]
            loss_s = nn.BCEWithLogitsLoss()(node_seg_s, labels_float)
        else:
            # For multi-class classification, use CrossEntropyLoss
            label_s_onehot = F.one_hot(label_s, self.num_classes)
            loss_s = cross_entropy_loss(label_s_onehot, node_seg_s)
        
        # For entropy loss, we need probabilities, so apply sigmoid for binary classification
        if self.num_classes == 2:
            node_seg_t_prob = torch.sigmoid(node_seg_t)
            # For binary classification, entropy loss needs to handle single-channel output
            # We need to create a 2-channel probability distribution
            node_seg_t_prob = torch.cat([1 - node_seg_t_prob, node_seg_t_prob], dim=1)
        else:
            node_seg_t_prob = node_seg_t
        
        loss_t = entropy_loss(node_seg_t_prob)

        max_num_node = max(num_node_s, num_node_t)
        z_s_ = nn.ZeroPad2d(padding=(0, 0, 0, max_num_node - num_node_s))(z_s)
        z_t_ = nn.ZeroPad2d(padding=(0, 0, 0, max_num_node - num_node_t))(z_t)
        weight_s = torch.zeros([max_num_node], device=z_s.device, dtype=z_s.dtype)
        weight_t = torch.zeros([max_num_node], device=z_t.device, dtype=z_t.dtype)
        weight_s[:num_node_s] = 1.0
        weight_t[:num_node_t] = 1.0
        loss_adv = self.domain_adv(z_s_, z_t_, weight_s, weight_t)
        domain_acc = self.domain_adv.domain_discriminator_accuracy

        self.log("train_loss_s", loss_s, on_step=False, on_epoch=True)
        self.log("train_loss_t", loss_t, on_step=False, on_epoch=True)
        self.log("train_loss_transfer", loss_adv, on_step=False, on_epoch=True)
        self.log("train_transfer_acc", domain_acc, on_step=False, on_epoch=True)

        # loss = loss_s + 0.3 * loss_adv + 0.1 * loss_t
        loss = loss_s + 0.15 * loss_adv + 0.3 * loss_t
        self.log("train_loss", loss, on_step=False, on_epoch=True)
        return loss

    def validation_step(self, batch, batch_idx):
        self.brep_encoder.eval()
        self.attention.eval()
        self.classifier.eval()
        self.domain_adv.eval()

        _z_s, _z_t, node_seg_s, node_seg_t = self._forward_split(batch)
        num_node_s = node_seg_s.size(0)
        label_s = batch["label_feature"][:num_node_s].long()
        label_t = batch["label_feature"][num_node_s:].long()

        if self.num_classes == 2:
            # For binary classification, use BCEWithLogitsLoss
            labels_float = label_s.float().unsqueeze(1)  # [total_nodes, 1]
            loss_s = nn.BCEWithLogitsLoss()(node_seg_s, labels_float)
        else:
            # For multi-class classification, use CrossEntropyLoss
            loss_s = cross_entropy_loss(F.one_hot(label_s, self.num_classes), node_seg_s)
        
        # For entropy loss, we need probabilities, so apply sigmoid for binary classification
        if self.num_classes == 2:
            node_seg_t_prob = torch.sigmoid(node_seg_t)
            # For binary classification, entropy loss needs to handle single-channel output
            # We need to create a 2-channel probability distribution
            node_seg_t_prob = torch.cat([1 - node_seg_t_prob, node_seg_t_prob], dim=1)
        else:
            node_seg_t_prob = node_seg_t
        
        loss_t = entropy_loss(node_seg_t_prob)
        self.log("eval_loss_s", loss_s, on_step=False, on_epoch=True)
        self.log("eval_loss_t", loss_t, on_step=False, on_epoch=True)

        if self.num_classes == 2:
            # For binary classification, get predictions by applying sigmoid and thresholding at 0.5
            pred_s = (torch.sigmoid(node_seg_s) > 0.5).float().squeeze(1).long()
            pred_t = (torch.sigmoid(node_seg_t) > 0.5).float().squeeze(1).long()
        else:
            # For multi-class classification, get predictions by taking argmax
            pred_s = torch.argmax(node_seg_s, dim=-1)
            pred_t = torch.argmax(node_seg_t, dim=-1)
        
        known_pos = torch.where(label_t < self.num_classes)
        pred_t_ = pred_t[known_pos]
        label_t_ = label_t[known_pos]

        self.pred_s.extend(pred_s.detach().cpu().numpy().tolist())
        self.label_s.extend(label_s.detach().cpu().numpy().tolist())
        self.pred_t.extend(pred_t_.detach().cpu().numpy().tolist())
        self.label_t.extend(label_t_.detach().cpu().numpy().tolist())

        per_face_comp_t = (pred_t_.detach().cpu().numpy() == label_t_.detach().cpu().numpy()).astype(np.int32)
        eval_loss = 1.0 / max(np.mean(per_face_comp_t), 1e-8)
        self.log("eval_loss", eval_loss, on_step=False, on_epoch=True)
        return eval_loss

    def on_validation_epoch_end(self):
        if self.pred_s and self.label_s:
            pred_s_np = np.array(self.pred_s)
            label_s_np = np.array(self.label_s)
            self.log("per_face_accuracy_source", float(np.mean((pred_s_np == label_s_np).astype(np.int32))))
        if self.pred_t and self.label_t:
            pred_t_np = np.array(self.pred_t)
            label_t_np = np.array(self.label_t)
            self.log("per_face_accuracy_target", float(np.mean((pred_t_np == label_t_np).astype(np.int32))))
        self.pred_s, self.label_s, self.pred_t, self.label_t = [], [], [], []

    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(self.brep_encoder.parameters(), lr=0.0001, betas=(0.99, 0.999))
        optimizer.add_param_group({"params": self.classifier.parameters(), "lr": 0.0001, "betas": (0.99, 0.999)})
        optimizer.add_param_group({"params": self.domain_adv.parameters(), "lr": 0.001, "betas": (0.99, 0.999)})
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            mode="min",
            factor=0.5,
            patience=5,
            threshold=0.0001,
            threshold_mode="rel",
            min_lr=0.000001,
            cooldown=2,
            verbose=False,
        )
        return {
            "optimizer": optimizer,
            "lr_scheduler": {"scheduler": scheduler, "interval": "epoch", "frequency": 1, "monitor": "eval_loss"},
        }
