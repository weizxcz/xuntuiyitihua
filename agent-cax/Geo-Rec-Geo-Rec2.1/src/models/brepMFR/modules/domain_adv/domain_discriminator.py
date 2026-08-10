"""
@author: Junguang Jiang
@contact: JiangJunguang1123@outlook.com
"""
from typing import List, Dict
import torch.nn as nn

__all__ = ['DomainDiscriminator']


class DomainDiscriminator(nn.Sequential):
    r"""域判别器模型（源于 Domain-Adversarial Training of Neural Networks, ICML 2015）。

    主要用于二分类判别：判断特征来自源域还是目标域。
    源域标签为 1，目标域标签为 0。

    参数：
        in_feature (int): 输入特征维度。
        hidden_size (int): 隐层特征维度。
        batch_norm (bool): 是否使用批归一化（BatchNorm1d）。
            如果为 False，则在残差间使用 Dropout。默认 True。

    形状：
        - 输入: (minibatch, in_feature)
        - 输出: (minibatch, 1)
    """

    def __init__(self, in_feature: int, hidden_size: int, batch_norm=True):
        if batch_norm:
            super(DomainDiscriminator, self).__init__(
                nn.Linear(in_feature, hidden_size),
                nn.BatchNorm1d(hidden_size),
                nn.ReLU(),
                nn.Linear(hidden_size, hidden_size),
                nn.BatchNorm1d(hidden_size),
                nn.ReLU(),
                nn.Linear(hidden_size, 1),
                nn.Sigmoid()
            )
        else:
            super(DomainDiscriminator, self).__init__(
                nn.Linear(in_feature, hidden_size),
                nn.ReLU(inplace=True),
                nn.Dropout(0.5),
                nn.Linear(hidden_size, hidden_size),
                nn.ReLU(inplace=True),
                nn.Dropout(0.5),
                nn.Linear(hidden_size, 1),
                nn.Sigmoid()
            )

    def get_parameters(self) -> List[Dict]:
        """返回参数组，方便外部直接使用。"""
        return [{"params": self.parameters(), "lr": 1.}]


