"""
@author: Junguang Jiang
@contact: JiangJunguang1123@outlook.com
"""
from typing import Optional
import torch
import torch.nn as nn
import torch.nn.functional as F

from .grl import WarmStartGradientReverseLayer
from .utils.metric import binary_accuracy

__all__ = ['DomainAdversarialLoss']


class DomainAdversarialLoss(nn.Module):
    r"""
    域对抗损失，用于缩小源域和目标域特征分布差异。

    通过域判别器判断特征来自源域还是目标域，
    并使用反向梯度分离（GRL）使特征编码器学习域不可区分表示。

    参考论文：Domain-Adversarial Training of Neural Networks (ICML 2015), https://arxiv.org/abs/1505.07818

    定义：当判别器 D 预测源域概率为 1、目标域概率为 0 时，损失为：

        L = E_{x^s~D_s}[-log(D(f^s))] + E_{x^t~D_t}[-log(1-D(f^t))]

    参数：
        domain_discriminator (torch.nn.Module): 域判别器，输入形状 (N, F)，输出形状 (N, 1)
        reduction (str, optional): 输出规约方式：'none'|'mean'|'sum'，默认 'mean'
        grl (WarmStartGradientReverseLayer, optional): 分离层，默认 None（自动创建）

    输入：
        - f_s (tensor): 源域特征表示，形状 (N, F)
        - f_t (tensor): 目标域特征表示，形状 (N, F)
        - w_s (tensor, optional): 源域样本权重
        - w_t (tensor, optional): 目标域样本权重

    输出：
        标量（默认），若 reduction='none' 则形状 (N,)

    Examples::

        >>> from dalib.modules.domain_discriminator import DomainDiscriminator
        >>> discriminator = DomainDiscriminator(in_feature=1024, hidden_size=1024)
        >>> loss = DomainAdversarialLoss(discriminator, reduction='mean')
        >>> # features from source domain and target domain
        >>> f_s, f_t = torch.randn(20, 1024), torch.randn(20, 1024)
        >>> # If you want to assign different weights to each instance, you should pass in w_s and w_t
        >>> w_s, w_t = torch.randn(20), torch.randn(20)
        >>> output = loss(f_s, f_t, w_s, w_t)
    """

    def __init__(self, domain_discriminator: nn.Module, reduction: Optional[str] = 'mean',
                 grl: Optional = None):
        super(DomainAdversarialLoss, self).__init__()
        self.grl = WarmStartGradientReverseLayer(alpha=1., lo=0., hi=1., max_iters=1000, auto_step=True) if grl is None else grl
        self.domain_discriminator = domain_discriminator
        self.bce = lambda input, target, weight: \
            F.binary_cross_entropy(input, target, weight=weight, reduction=reduction)
        self.domain_discriminator_accuracy = None

    def forward(self, f_s: torch.Tensor, f_t: torch.Tensor,
                w_s: Optional[torch.Tensor] = None, w_t: Optional[torch.Tensor] = None) -> torch.Tensor:
        """前向传播：计算域对抗损失和域判别器准确率。"""
        # 1. 合并源域和目标域特征并通过 GRL
        f = self.grl(torch.cat((f_s, f_t), dim=0))
        # 2. 域判别器输出（接近 1 源域，0 目标域）
        d = self.domain_discriminator(f)
        d_s, d_t = d.chunk(2, dim=0)
        # 3. 真实域标签
        d_label_s = torch.ones((f_s.size(0), 1)).to(f_s.device)
        d_label_t = torch.zeros((f_t.size(0), 1)).to(f_t.device)

        # 域判别准确率（监控对抗训练性质）
        self.domain_discriminator_accuracy = 0.5 * (binary_accuracy(d_s, d_label_s) + binary_accuracy(d_t, d_label_t))

        if w_s is None:
            w_s = torch.ones_like(d_label_s)
        if w_t is None:
            w_t = torch.ones_like(d_label_t)
        return 0.5 * (self.bce(d_s, d_label_s, w_s.view_as(d_s)) + self.bce(d_t, d_label_t, w_t.view_as(d_t)))
