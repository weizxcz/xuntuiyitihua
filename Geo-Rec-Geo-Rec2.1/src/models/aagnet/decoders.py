import torch
from torch import nn
import torch.nn.functional as F
import dgl
from torch.nn.utils.rnn import pad_sequence


def manual_pad_sequence(sequences, batch_first=False, padding_value=0):
    """
    手动实现的序列填充函数，与PyTorch的torch.nn.utils.rnn.pad_sequence功能完全一致

    参数:
        sequences: 待填充的序列列表，每个元素为torch.Tensor
        batch_first: 若为True，输出形状为(batch_size, max_seq_len, ...)；否则为(max_seq_len, batch_size, ...)
        padding_value: 填充值

    返回:
        填充后的张量
    """
    if not sequences:
        raise RuntimeError("received an empty list of sequences")

    # 检查所有序列的维度、数据类型和设备一致性
    dims = sequences[0].dim()
    dtype = sequences[0].dtype
    device = sequences[0].device
    # 检查特征维度（除第0维外的所有维度）
    feature_dims = sequences[0].shape[1:]

    for seq in sequences[1:]:
        if seq.dim() != dims:
            raise ValueError(f"所有序列必须具有相同的维度，发现 {dims} 维和 {seq.dim()} 维")
        if seq.dtype != dtype:
            raise ValueError(f"所有序列必须具有相同的数据类型，发现 {dtype} 和 {seq.dtype}")
        if seq.device != device:
            raise ValueError(f"所有序列必须位于相同设备，发现 {device} 和 {seq.device}")
        if seq.shape[1:] != feature_dims:
            raise ValueError(f"所有序列必须具有相同的特征维度，发现 {feature_dims} 和 {seq.shape[1:]}")

    # 计算批次大小和最大序列长度
    batch_size = len(sequences)
    max_seq_len = max(seq.size(0) for seq in sequences)
    feature_shape = list(feature_dims)  # 提取特征维度部分

    # 确定输出形状
    if batch_first:
        output_shape = [batch_size, max_seq_len] + feature_shape
    else:
        output_shape = [max_seq_len, batch_size] + feature_shape

    # 创建填充张量
    output = torch.full(
        size=output_shape,
        fill_value=padding_value,
        dtype=dtype,
        device=device
    )

    # 填充原始序列数据
    for batch_idx, seq in enumerate(sequences):
        seq_len = seq.size(0)
        if batch_first:
            if dims == 1:
                output[batch_idx, :seq_len] = seq
            else:
                output[batch_idx, :seq_len, ...] = seq
        else:
            if dims == 1:
                output[:seq_len, batch_idx] = seq
            else:
                output[:seq_len, batch_idx, ...] = seq

    return output


class InnerProductDecoder(nn.Module):
    def __init__(self, Wq=nn.Identity(), Wk=nn.Identity(), return_feat=False, projector=None):
        super().__init__()
        self.Wq = Wq
        self.Wk = Wk
        self.return_feat = return_feat
        self.projector = projector if return_feat else None

    def forward(self, batched_graph, batched_h):
        # the adjaceny matrix should be computed in each graph, rather than batched graph
        # unbatch the features of nodes from graph
        batch_num_nodes = batched_graph.batch_num_nodes().tolist()
        hidden_list = torch.split(batched_h, batch_num_nodes, dim=0)
        # faster version use torch.nn.utils.rnn.unpad_sequence
        padded_hidden = pad_sequence(hidden_list, batch_first=True)
        # padded_hidden = manual_pad_sequence(hidden_list, batch_first=True)
        q = self.Wq(padded_hidden)
        k = self.Wk(padded_hidden)
        inst_out = torch.bmm(q, k.transpose(1, 2))
        # feature after projector
        feat_out = []
        if self.return_feat:
            feat_out = self.projector(padded_hidden)
        
        return inst_out, feat_out


class InstanceDecoder(nn.Module):
    '''
    obsoleted
    '''
    def __init__(self, Wq=nn.Identity(), Wk=nn.Identity(), return_feat=False, projector=None):
        super().__init__()
        self.Wq = Wq
        self.Wk = Wk
        self.return_feat = return_feat
        self.projector = projector if return_feat else None

    def forward(self, batched_graph, batched_h):
        # the adjaceny matrix should be computed in each graph, rather than batched graph
        batched_graph.ndata['h'] = batched_h
        graph_list = dgl.unbatch(batched_graph)
        # the instance prediction should be computed in each graph
        inst_out = []
        feat_out = []
        for idx, graph in enumerate(graph_list):
            h = graph.ndata['h']
            q = self.Wq(h)
            k = self.Wk(h)
            n = h.shape[0]
            fm1 = torch.unsqueeze(q, dim=2)
            fm2 = torch.unsqueeze(k.T, dim=0)
            fm1 = torch.tile(fm1, dims=[1, 1, n])
            fm2 = torch.tile(fm2, dims=[n, 1, 1])
            sm = torch.square(fm1 - fm2)
            sm = torch.sum(sm, axis=1)
            inst_out.append(sm)
            if self.return_feat:
                p = self.projector(h)
                feat_out.append(p)

        return inst_out, feat_out
