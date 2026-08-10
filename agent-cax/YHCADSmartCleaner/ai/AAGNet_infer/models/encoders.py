
import dgl
from torch import nn

from .layers import MLP
from .layers import NodeMPNN, EdgeMPNN


class AAGNetGraphEncoder(nn.Module):
    def __init__(
        self,
        node_dim,
        edge_dim,
        num_layers,
        delta,
        mlp_ratio=4,
        drop=0.,
        drop_path=0.,
        conv_on_edge=True
    ):
        """

        Args:
            input_dim (int): [description]
            input_edge_dim (int): [description]
            output_dim (int): [description]
            num_layers (int, optional): [description].
        """
        super(AAGNetGraphEncoder, self).__init__()
        self.num_layers = num_layers
        self.conv_on_edge = conv_on_edge
        self.node_convs = nn.ModuleList()
        self.edge_convs = nn.ModuleList()        
        # since 2nd layer, the subsequent layers are share-weight
        for _ in range(2):
            if self.conv_on_edge:
                self.edge_convs.append(
                    EdgeMPNN(node_dim, edge_dim, mlp_ratio, drop, drop_path))
            self.node_convs.append(
                NodeMPNN(node_dim, edge_dim, delta, mlp_ratio, drop, drop_path))

        self.post_norm = nn.LayerNorm(node_dim)
        # linear functions for graph average poolings of output
        self.pool = dgl.nn.AvgPooling()
        self.linear = MLP(1, node_dim, 0, node_dim, nn.LayerNorm, True)
    
    def forward(self, g, h, he):
        # first layer
        if self.conv_on_edge:
            he = self.edge_convs[0](g, h, he)
        h = self.node_convs[0](g, h, he)
        
        # subsequent share-weight layer
        for i in range(self.num_layers-1):
            if self.conv_on_edge:
                he = self.edge_convs[1](g, h, he)
            h = self.node_convs[1](g, h, he)
        
        local_feat = self.post_norm(h)
        # perform graph sum pooling over all nodes
        global_feat = self.linear(self.pool(g, local_feat))
        return local_feat, global_feat

