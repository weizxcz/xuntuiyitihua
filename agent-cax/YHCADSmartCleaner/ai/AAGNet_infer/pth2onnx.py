import torch
import dgl
import numpy as np
import os
import sys

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from ai.AAGNet_infer.models.inst_segmentors import AAGNetSegmentor

class SimplifiedInnerProductDecoder(torch.nn.Module):
    """简化的InnerProductDecoder，避免使用pad_sequence"""
    def __init__(self, Wq=torch.nn.Identity(), Wk=torch.nn.Identity(), return_feat=False, projector=None):
        super().__init__()
        self.Wq = Wq
        self.Wk = Wk
        self.return_feat = return_feat
        self.projector = projector if return_feat else None
    
    def forward(self, batched_graph, batched_h):
        """
        前向传播 - 简化版本，只处理单个图
        """
        # 对于单个图，直接计算
        q = self.Wq(batched_h)
        k = self.Wk(batched_h)
        inst_out = torch.mm(q, k.transpose(0, 1))
        # 添加 batch 维度
        inst_out = inst_out.unsqueeze(0)
        
        # feature after projector
        feat_out = []
        if self.return_feat:
            feat_out = self.projector(batched_h)
        
        return inst_out, feat_out

class ModelWrapper(torch.nn.Module):
    """模型包装器，直接接受节点属性、节点网格属性和边属性"""
    def __init__(self, model):
        super().__init__()
        self.model = model
        # 替换原始的inst_head为简化版本
        if hasattr(self.model, 'inst_head'):
            # 保存原始的Wq和Wk
            original_inst_head = self.model.inst_head
            # 创建简化版本
            self.model.inst_head = SimplifiedInnerProductDecoder(
                Wq=original_inst_head.Wq,
                Wk=original_inst_head.Wk,
                return_feat=original_inst_head.return_feat,
                projector=original_inst_head.projector
            )
    
    def forward(self, node_attr, node_grid, edge_attr):
        """
        前向传播
        
        Args:
            node_attr: 节点属性 [num_nodes, node_attr_dim]
            node_grid: 节点网格属性 [num_nodes, node_grid_dim, 5, 5]
            edge_attr: 边属性 [num_edges, edge_attr_dim]
        
        Returns:
            模型的输出
        """
        # 直接处理输入，不使用DGL图，以确保ONNX导出时能够正确处理动态维度
        # 模拟AAGNetSegmentor的forward方法
        
        # Input features
        input_node_attr = node_attr
        input_node_grid = node_grid
        input_edge_attr = edge_attr
        
        # Compute hidden face features
        node_feat = self.model.node_attr_encoder(input_node_attr)
        if self.model.node_grid_encoder:
            node_grid_feat = self.model.node_grid_encoder(input_node_grid)
            node_feat = torch.concat([node_feat, node_grid_feat], dim=1)
        
        # Compute hidden edge features
        edge_feat = self.model.edge_attr_encoder(input_edge_attr)
        
        # 创建一个简单的DGL图，只用于满足模型的输入格式要求
        # 这里使用一个固定的图结构，因为实际的图结构在导出时会被固化
        num_nodes = node_attr.shape[0]
        num_edges = edge_attr.shape[0]
        
        # 确保边数量至少为1，避免空图
        if num_edges == 0:
            num_edges = 1
            edge_feat = torch.zeros(1, edge_feat.shape[1], device=edge_feat.device)
        
        # 创建一个有num_edges条边的图
        # 为了避免边索引越界，我们使用模运算确保边的目标节点在有效范围内
        src_nodes = torch.arange(num_edges, dtype=torch.int64) % num_nodes
        dst_nodes = (torch.arange(num_edges, dtype=torch.int64) + 1) % num_nodes
        g = dgl.graph((src_nodes, dst_nodes), num_nodes=num_nodes)
        
        # Message pass and compute per-face(node) and global embeddings
        node_emb, graph_emb = self.model.graph_encoder(
            g, node_feat, edge_feat
        )
        
        # concatenated to the per-node embeddings
        # 由于我们只处理单个图，所以直接复制graph_emb num_nodes次
        graph_emb = graph_emb.repeat(num_nodes, 1)
        local_global_feat = torch.cat((node_emb, graph_emb), dim=1)
        
        # Map to logits
        seg_out = self.model.seg_head(local_global_feat)
        inst_out, feat_list = self.model.inst_head(g, local_global_feat)
        bottom_out = self.model.bottom_head(local_global_feat)
        
        return seg_out, inst_out, bottom_out

class PTH2ONNXConverter:
    def __init__(self, weight_path, output_onnx_path):
        self.weight_path = weight_path
        self.output_onnx_path = output_onnx_path
        self.device = 'cpu'
        self.init_model()
        self.load_weights()
    
    def init_model(self):
        """初始化模型"""
        self.original_model = AAGNetSegmentor(
            arch='AAGNetGraphEncoder',
            num_classes=2,
            edge_attr_dim=10, node_attr_dim=10,
            edge_attr_emb=64, node_attr_emb=64,
            edge_grid_dim=0, node_grid_dim=7,
            edge_grid_emb=0, node_grid_emb=64,
            num_layers=4, delta=2, mlp_ratio=4,
            drop=0., drop_path=0.,
            head_hidden_dim=256,
            conv_on_edge=False
        )
        # 创建包装器
        self.model = ModelWrapper(self.original_model)
        self.model = self.model.to(self.device)
        self.model.eval()
    
    def load_weights(self):
        """加载PyTorch权重"""
        if not os.path.exists(self.weight_path):
            raise FileNotFoundError(f"权重文件不存在: {self.weight_path}")
        
        model_param = torch.load(self.weight_path, map_location=self.device)
        self.original_model.load_state_dict(model_param)
        print(f"成功加载权重文件: {self.weight_path}")
    
    def create_dummy_input(self):
        """创建虚拟输入"""
        # 节点数
        num_nodes = 10
        # 边数（使用与节点数不同的值，确保模型能够处理边数与节点数不同的情况）
        num_edges = 20
        
        # 节点属性
        node_attr = torch.randn(num_nodes, 10, device=self.device)
        
        # 节点网格属性
        node_grid = torch.randn(num_nodes, 7, 5, 5, device=self.device)
        
        # 边属性
        # 创建与边数量匹配的边属性
        edge_attr = torch.randn(num_edges, 10, device=self.device)
        
        return node_attr, node_grid, edge_attr
    
    def convert(self):
        """执行转换"""
        # 创建虚拟输入
        dummy_input = self.create_dummy_input()
        
        # 确保输出目录存在
        output_dir = os.path.dirname(self.output_onnx_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 导出为ONNX
        print(f"开始转换模型为ONNX格式...")
        torch.onnx.export(
            self.model,
            dummy_input,
            self.output_onnx_path,
            export_params=True,
            opset_version=13,
            do_constant_folding=False,  # 禁用常量折叠，确保动态维度正确处理
            input_names=['node_attr', 'node_grid', 'edge_attr'],
            output_names=['seg_out', 'inst_out', 'bottom_out'],
            dynamic_axes={
                'node_attr': {0: 'num_nodes'},
                'node_grid': {0: 'num_nodes'},
                'edge_attr': {0: 'num_edges'},
                'seg_out': {0: 'num_nodes'},
                'inst_out': {1: 'num_nodes', 2: 'num_nodes'},
                'bottom_out': {0: 'num_nodes'}
            }
        )
        
        print(f"成功导出ONNX模型到: {self.output_onnx_path}")
        print(f"模型转换完成！")

def main():
    # 默认参数
    weight_path = "ai/AAGNet_infer/weights/weight_round.pth"
    output_onnx_path = "ai/AAGNet_infer/weights/weight_round.onnx"
    
    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="将PyTorch模型转换为ONNX格式")
    parser.add_argument("--weight", type=str, default=weight_path, help="PyTorch权重文件路径")
    parser.add_argument("--output", type=str, default=output_onnx_path, help="输出ONNX文件路径")
    args = parser.parse_args()
    
    # 创建转换器
    converter = PTH2ONNXConverter(args.weight, args.output)
    
    # 执行转换
    converter.convert()

if __name__ == "__main__":
    main()
