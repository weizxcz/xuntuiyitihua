import torch
from torch import nn

from ai.AAGNet_train.models.layers import DropPath, MLP, Scale


class PNAConvTowerTensor(nn.Module):
    def __init__(self, in_size, out_size, delta, edge_feat_size, dropout=0.0):
        super().__init__()
        self.M = nn.Linear(2 * in_size + edge_feat_size, in_size)
        self.U = nn.Linear(3 * in_size, out_size)
        self.norm_drop = nn.Sequential(nn.BatchNorm1d(out_size), nn.Dropout(dropout))

    def forward(self, node_feat, edge_feat, src, dst):
        num_nodes = node_feat.shape[0]
        message = self.M(torch.cat([node_feat[src], node_feat[dst], edge_feat], dim=-1))
        dst_index = dst.unsqueeze(1).expand(-1, message.shape[1])
        summed = torch.zeros(num_nodes, message.shape[1], dtype=message.dtype, device=message.device)
        summed = summed.scatter_reduce(0, dst_index, message, reduce="sum", include_self=True)
        maximum = torch.full_like(summed, -3.4028234663852886e38)
        maximum = maximum.scatter_reduce(0, dst_index, message, reduce="amax", include_self=True)
        incoming = torch.zeros(num_nodes, 1, dtype=message.dtype, device=message.device)
        incoming = incoming.scatter_reduce(0, dst.unsqueeze(1), torch.ones(message.shape[0], 1, dtype=message.dtype, device=message.device), reduce="sum", include_self=True)
        maximum = torch.where(incoming > 0, maximum, torch.zeros_like(maximum))
        return self.norm_drop(self.U(torch.cat([node_feat, summed, maximum], dim=-1)) * torch.rsqrt(torch.sum(torch.ones_like(node_feat[:, :1]))))


class NodeMPNNTensor(nn.Module):
    def __init__(self, node_dim, edge_dim, delta, mlp_ratio=4, drop=0.0, drop_path=0.0):
        super().__init__()
        self.norm1 = nn.LayerNorm(node_dim)
        self.conv = PNAConvTowerTensor(node_dim, node_dim, delta, edge_dim, drop)
        self.drop_path1 = DropPath(drop_path) if drop_path else nn.Identity()
        self.layer_scale1, self.res_scale1 = Scale(dim=node_dim), Scale(dim=node_dim)
        self.norm2 = nn.LayerNorm(node_dim)
        self.mlp = MLP(2, node_dim, node_dim * mlp_ratio, node_dim, nn.LayerNorm, nn.Mish)
        self.drop_path2 = DropPath(drop_path) if drop_path else nn.Identity()
        self.layer_scale2, self.res_scale2 = Scale(dim=node_dim), Scale(dim=node_dim)

    def forward(self, node_feat, edge_feat, src, dst):
        node_feat = self.res_scale1(node_feat) + self.layer_scale1(self.drop_path1(self.conv(self.norm1(node_feat), edge_feat, src, dst)))
        return self.res_scale2(node_feat) + self.layer_scale2(self.drop_path2(self.mlp(self.norm2(node_feat))))


class AAGNetGraphEncoderTensor(nn.Module):
    def __init__(self, node_dim, edge_dim, num_layers, delta, mlp_ratio=4, drop=0.0, drop_path=0.0):
        super().__init__()
        self.num_layers = num_layers
        self.node_convs = nn.ModuleList([NodeMPNNTensor(node_dim, edge_dim, delta, mlp_ratio, drop, drop_path) for _ in range(2)])
        self.post_norm = nn.LayerNorm(node_dim)
        self.linear = MLP(1, node_dim, 0, node_dim, nn.LayerNorm, True)

    def forward(self, node_feat, edge_feat, src, dst):
        node_feat = self.node_convs[0](node_feat, edge_feat, src, dst)
        for _ in range(self.num_layers - 1):
            node_feat = self.node_convs[1](node_feat, edge_feat, src, dst)
        local = self.post_norm(node_feat)
        return local, self.linear(local.mean(dim=0, keepdim=True))


class InnerProductDecoderTensor(nn.Module):
    def __init__(self, query, key):
        super().__init__()
        self.Wq, self.Wk = query, key

    def forward(self, node_feat):
        query, key = self.Wq(node_feat.unsqueeze(0)), self.Wk(node_feat.unsqueeze(0))
        return torch.bmm(query, key.transpose(1, 2))


class AAGNetTensorSegmentor(nn.Module):
    """Single-graph tensor-only counterpart of the DGL AAGNet segmentor."""
    def __init__(self, num_classes, edge_attr_dim, node_attr_dim, edge_attr_emb, node_attr_emb,
                 node_grid_dim, node_grid_emb, num_layers, delta, mlp_ratio=4, drop=0.0,
                 drop_path=0.0, head_hidden_dim=256):
        super().__init__()
        self.node_attr_encoder = nn.Sequential(nn.Linear(node_attr_dim, node_attr_emb), nn.LayerNorm(node_attr_emb))
        self.node_grid_encoder = nn.Sequential(
            nn.Conv2d(node_grid_dim, node_grid_emb // 4, 3, 1, 1), nn.BatchNorm2d(node_grid_emb // 4), nn.Mish(),
            nn.Conv2d(node_grid_emb // 4, node_grid_emb // 2, 3, 1, 1), nn.BatchNorm2d(node_grid_emb // 2), nn.Mish(),
            nn.Conv2d(node_grid_emb // 2, node_grid_emb, 3, 1, 1), nn.BatchNorm2d(node_grid_emb), nn.Mish(),
            nn.AdaptiveAvgPool2d(1), nn.Flatten(1),
        )
        self.edge_attr_encoder = nn.Sequential(nn.Linear(edge_attr_dim, edge_attr_emb), nn.LayerNorm(edge_attr_emb))
        node_dim = node_attr_emb + node_grid_emb
        self.graph_encoder = AAGNetGraphEncoderTensor(node_dim, edge_attr_emb, num_layers, delta, mlp_ratio, drop, drop_path)
        output_dim = 2 * node_dim
        self.seg_head = MLP(2, output_dim, head_hidden_dim, num_classes, nn.LayerNorm, act=nn.Mish)
        self.inst_head = InnerProductDecoderTensor(
            MLP(2, output_dim, head_hidden_dim, head_hidden_dim, nn.LayerNorm, last_norm=True, act=nn.Mish),
            MLP(2, output_dim, head_hidden_dim, head_hidden_dim, nn.LayerNorm, last_norm=True, act=nn.Mish),
        )
        self.bottom_head = MLP(2, output_dim, head_hidden_dim, 1, nn.LayerNorm, act=nn.Mish)

    def forward(self, node_attr, node_grid, edge_attr, src, dst):
        node_feat = torch.cat([self.node_attr_encoder(node_attr), self.node_grid_encoder(node_grid)], dim=1)
        local, global_feat = self.graph_encoder(node_feat, self.edge_attr_encoder(edge_attr), src, dst)
        features = torch.cat([local, global_feat.repeat(local.shape[0], 1)], dim=1)
        return self.seg_head(features), self.inst_head(features), self.bottom_head(features)
