"""
@author: Junguang Jiang
@contact: JiangJunguang1123@outlook.com
"""
from typing import Optional, Any, Tuple
import numpy as np
import torch.nn as nn
from torch.autograd import Function
import torch


class GradientReverseFunction(Function):

    @staticmethod
    def forward(ctx: Any, input: torch.Tensor, coeff: Optional[float] = 1.) -> torch.Tensor:
        """前向保持不变，记录系数用于反向梯度翻转"""
        ctx.coeff = coeff
        output = input * 1.0
        return output

    @staticmethod
    def backward(ctx: Any, grad_output: torch.Tensor) -> Tuple[torch.Tensor, Any]:
        """反向传播时对梯度取负，并乘以当前系数。"""
        return grad_output.neg() * ctx.coeff, None


class GradientReverseLayer(nn.Module):
    """基础梯度反转层，用于对抗训练中解除特征与标签的正向关系。"""
    def __init__(self):
        super(GradientReverseLayer, self).__init__()

    def forward(self, *input):
        return GradientReverseFunction.apply(*input)


class WarmStartGradientReverseLayer(nn.Module):
    """Warm-start 版本梯度反转层。

    前向过程：恒等映射，即输出等于输入。
    反向过程：对梯度取负并乘以系数 :math:`\lambda`。

    :math:`\lambda` 从 `lo` 线性升到 `hi`，按如下公式逐步调度：

        \lambda = \frac{2(hi-lo)}{1+\exp(-α i / N)} - (hi-lo) + lo

    其中 `i` 为当前迭代次数，`N` 为最大迭代次数 `max_iters`。

    参数：
        alpha (float, optional): 控制调度曲线陡度。默认 1.0。
        lo (float, optional): 初始值。默认 0.0。
        hi (float, optional): 最终值。默认 1.0。
        max_iters (int, optional): 迭代周期。默认 1000。
        auto_step (bool, optional): 若 True，则每次调用 forward 时自动增加迭代计数；
            否则需手动调用 step()。默认 False。
    """

    def __init__(self, alpha: Optional[float] = 1.0, lo: Optional[float] = 0.0, hi: Optional[float] = 1.,
                 max_iters: Optional[int] = 1000., auto_step: Optional[bool] = False):
        super(WarmStartGradientReverseLayer, self).__init__()
        self.alpha = alpha
        self.lo = lo
        self.hi = hi
        self.iter_num = 0
        self.max_iters = max_iters
        self.auto_step = auto_step

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        """根据当前迭代次数计算系数，并在前向不改变数据的情况下反向翻转梯度。"""
        coeff = float(
            2.0 * (self.hi - self.lo) / (1.0 + np.exp(-self.alpha * self.iter_num / self.max_iters))
            - (self.hi - self.lo) + self.lo
        )
        if self.auto_step:
            self.step()
        return GradientReverseFunction.apply(input, coeff)

    def step(self):
        """手动增加迭代计数，用于支撑非 auto_step 模式。"""
        self.iter_num += 1
