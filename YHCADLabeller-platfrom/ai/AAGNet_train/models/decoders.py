import torch
from torch import nn
from torch.nn.utils.rnn import pad_sequence


class InnerProductDecoder(nn.Module):
    def __init__(self, Wq=nn.Identity(), Wk=nn.Identity(), return_feat=False, projector=None, upper_triangular=False):
        super().__init__()
        self.Wq = Wq
        self.Wk = Wk
        self.return_feat = return_feat
        self.projector = projector if return_feat else None
        self.upper_triangular = upper_triangular

    def forward(self, batched_graph, batched_h):
        # the adjaceny matrix should be computed in each graph, rather than batched graph
        # unbatch the features of nodes from graph
        batch_num_nodes = batched_graph.batch_num_nodes().tolist()
        hidden_list = torch.split(batched_h, batch_num_nodes, dim=0)
        # faster version use torch.nn.utils.rnn.unpad_sequence
        padded_hidden = pad_sequence(hidden_list, batch_first=True)
        q = self.Wq(padded_hidden)
        k = self.Wk(padded_hidden)
        inst_out = torch.bmm(q, k.transpose(1, 2))

        # feature after projector
        feat_out = []
        if self.return_feat:
            feat_out = self.projector(padded_hidden)

        return inst_out, feat_out

    def get_upper_triangular_mask(self, seq_len, device):
        """
        获取上三角掩码（不包括对角线）

        Args:
            seq_len: 序列长度（节点数）
            device: 设备

        Returns:
            布尔掩码张量，形状为 (seq_len, seq_len)，上三角部分为 True
        """
        return torch.triu(torch.ones(seq_len, seq_len, device=device, dtype=torch.bool), diagonal=1)

    def extract_upper_triangular(self, inst_out, batch_num_nodes):
        """
        从完整的 adjacency matrix 中提取上三角部分（不包括对角线）
        用于损失计算

        Args:
            inst_out: 完整的 adjacency matrix，形状为 (batch_size, max_seq_len, max_seq_len)
            batch_num_nodes: 每个图的节点数列表

        Returns:
            upper_preds: 展平后的上三角预测值，形状为 (batch_size * max_upper_tri_elements,)
            valid_mask: 有效掩码，标识哪些位置是有效的（非 padding），形状与 upper_preds 相同
        """
        batch_size = inst_out.shape[0]
        max_seq_len = inst_out.shape[1]

        # 计算最大上三角元素数（对于 max_seq_len 的图）
        max_upper_tri = max_seq_len * (max_seq_len - 1) // 2

        # 创建结果张量
        upper_preds = torch.zeros(batch_size, max_upper_tri, device=inst_out.device)
        valid_mask = torch.zeros(batch_size, max_upper_tri, device=inst_out.device, dtype=torch.bool)

        for i in range(batch_size):
            n = batch_num_nodes[i]
            if n < 2:
                continue
            mask = self.get_upper_triangular_mask(n, inst_out.device)
            # 提取上三角部分
            upper_pred = inst_out[i][:n, :n][mask]
            num_upper = n * (n - 1) // 2
            # 确保提取的元素数量正确
            assert upper_pred.shape[0] == num_upper, f"Expected {num_upper} elements, got {upper_pred.shape[0]}"
            upper_preds[i, :num_upper] = upper_pred
            valid_mask[i, :num_upper] = True

        return upper_preds, valid_mask
