import time

import dgl
import torch

from ai.brep_mfr.collator import collator
from ai.brep_mfr.models.brepseg_model import BrepSeg
from ai.brep_mfr.extractor import BrepMFRExtractor

# 人为输入参数
MANUAL_PARAMS = {
    "fillet_class": 1  # 圆角类别索引
}

def extract_graph_structure(ncti, doc, ai_object, objcet_name, face_ids):
    """从AI模型中提取图结构数据

    Args:
        ai: NCTI.AiModel实例
        face_ids: 面ID列表（此参数保留用于向后兼容，实际不再使用）

    Returns:
        dict: 符合BrepMFR格式的图结构JSON数据
    """
    extractor = BrepMFRExtractor(ncti=ncti)
    return extractor.process_core(doc=doc, ai_object=ai_object, object_name=objcet_name, face_ids=face_ids)
    # try:
    #     # 导入并使用BrepMFRExtractor
    #     # from data.BrepMFR_json_to_graph_ncti import BrepMFRExtractor
    #
    #     # 创建提取器实例，传入已初始化的NCTI
    #     extractor = BrepMFRExtractor(config=CONFIG, ncti=self.NCTI)
    #
    #     # 使用process_from_doc方法处理已有的文档
    #     return extractor.process_from_doc(self.doc, self.name, ai)
    #
    # except Exception as e:
    #     print(f"Error extracting graph structure: {e}")
    #     import traceback
    #     traceback.print_exc()
    #     raise
def preprocess_graph(graph_data):
    """预处理图数据，转换为模型输入格式"""

    # 从graph_data中提取数据
    num_nodes = graph_data["graph"]["num_nodes"]
    num_edges = graph_data["graph"]["num_edges"]
    src_nodes = graph_data["graph"]["src_nodes"]
    dst_nodes = graph_data["graph"]["dst_nodes"]

    # 创建DGL图
    graph = dgl.graph((src_nodes, dst_nodes), num_nodes=num_nodes)

    # 添加节点特征
    # 从graph_data中提取实际的节点特征
    node_data = graph_data.get("node_data", {})

    # 添加UV网格特征 (x)
    # 格式: [num_nodes, 5, 5, 7]
    if "x" in node_data and node_data["x"]:
        # 转换为张量
        graph.ndata["x"] = torch.tensor(node_data["x"], dtype=torch.float32)
    else:
        # 如果没有x特征，使用默认值
        graph.ndata["x"] = torch.zeros(num_nodes, 5, 5, 7, dtype=torch.float32)

    # 添加面面积 (y)
    if "y" in node_data and node_data["y"]:
        graph.ndata["y"] = torch.tensor(node_data["y"], dtype=torch.float32)
    else:
        graph.ndata["y"] = torch.zeros(num_nodes, dtype=torch.float32)

    # 添加面类型 (z)
    # 面几何类型: 0: 平面, 1: 圆柱面, 2: 圆锥面, 3: 球面, 4: 环面
    if "z" in node_data and node_data["z"]:
        graph.ndata["z"] = torch.tensor(node_data["z"], dtype=torch.long)
    else:
        graph.ndata["z"] = torch.zeros(num_nodes, dtype=torch.long)

    # 添加环数量 (l)
    if "l" in node_data and node_data["l"]:
        graph.ndata["l"] = torch.tensor(node_data["l"], dtype=torch.long)
    else:
        graph.ndata["l"] = torch.zeros(num_nodes, dtype=torch.long)

    # 添加邻接面数量 (a)
    if "a" in node_data and node_data["a"]:
        graph.ndata["a"] = torch.tensor(node_data["a"], dtype=torch.long)
    else:
        graph.ndata["a"] = torch.zeros(num_nodes, dtype=torch.long)

    # 添加面特征标签 (f)
    if "f" in node_data and node_data["f"]:
        graph.ndata["f"] = torch.tensor(node_data["f"], dtype=torch.long)
    else:
        graph.ndata["f"] = torch.zeros(num_nodes, dtype=torch.long)

    # 添加边特征
    edge_data = graph_data.get("edge_data", {})

    # 添加边的网格特征 (x)
    # 格式: [num_edges, 5, 7]
    if "x" in edge_data and edge_data["x"]:
        graph.edata["x"] = torch.tensor(edge_data["x"], dtype=torch.float32)
    else:
        graph.edata["x"] = torch.zeros(num_edges, 5, 7, dtype=torch.float32)

    # 添加边长度 (l)
    if "l" in edge_data and edge_data["l"]:
        graph.edata["l"] = torch.tensor(edge_data["l"], dtype=torch.float32)
    else:
        graph.edata["l"] = torch.zeros(num_edges, dtype=torch.float32)

    # 添加边类型 (t)
    if "t" in edge_data and edge_data["t"]:
        graph.edata["t"] = torch.tensor(edge_data["t"], dtype=torch.long)
    else:
        graph.edata["t"] = torch.zeros(num_edges, dtype=torch.long)

    # 添加边角度 (a)
    if "a" in edge_data and edge_data["a"]:
        graph.edata["a"] = torch.tensor(edge_data["a"], dtype=torch.float32)
    else:
        graph.edata["a"] = torch.zeros(num_edges, dtype=torch.float32)

    # 添加边连接信息 (c)
    if "c" in edge_data and edge_data["c"]:
        graph.edata["c"] = torch.tensor(edge_data["c"], dtype=torch.long)
    else:
        graph.edata["c"] = torch.zeros(num_edges, dtype=torch.long)

    # 创建PyG图对象
    class PYGGraph:
        def __init__(self):
            self.graph = graph
            self.node_data = graph.ndata["x"]
            self.face_area = graph.ndata["y"]
            self.face_type = graph.ndata["z"]
            self.face_loop = graph.ndata["l"]
            self.face_adj = graph.ndata["a"]
            self.edge_data = graph.edata["x"]
            self.edge_type = graph.edata["t"]
            self.edge_len = graph.edata["l"]
            self.edge_ang = graph.edata["a"]
            self.edge_conv = graph.edata["c"]
            self.node_degree = torch.zeros(num_nodes, dtype=torch.long)
            self.attn_bias = torch.zeros([num_nodes + 1, num_nodes + 1], dtype=torch.float)

            # 从graph_data中提取其他必要的特征
            graph_labels = graph_data.get("graph_labels", {})

            # 添加空间位置特征
            if "spatial_pos" in graph_labels and graph_labels["spatial_pos"]:
                self.spatial_pos = torch.tensor(graph_labels["spatial_pos"], dtype=torch.long)
            else:
                self.spatial_pos = torch.zeros([num_nodes, num_nodes], dtype=torch.long)

            # 添加d2距离特征
            if "d2_distance" in graph_labels and graph_labels["d2_distance"]:
                self.d2_distance = torch.tensor(graph_labels["d2_distance"], dtype=torch.float32)
            else:
                self.d2_distance = torch.zeros([num_nodes, num_nodes, 64], dtype=torch.float32)

            # 添加角度距离特征
            if "angle_distance" in graph_labels and graph_labels["angle_distance"]:
                self.angle_distance = torch.tensor(graph_labels["angle_distance"], dtype=torch.float32)
            else:
                self.angle_distance = torch.zeros([num_nodes, num_nodes, 64], dtype=torch.float32)

            # 添加边路径特征
            if "edges_path" in graph_labels and graph_labels["edges_path"]:
                self.edge_path = torch.tensor(graph_labels["edges_path"], dtype=torch.long)
            else:
                self.edge_path = torch.zeros([num_nodes, num_nodes, 16], dtype=torch.long)

            self.label_feature = graph.ndata["f"]
            self.data_id = 0

    pyg_graph = PYGGraph()

    # 使用collator函数对数据进行预处理
    # 由于collator函数需要处理批量数据，这里需要将单个图数据转换为批量数据
    items = [pyg_graph]
    batch_data = collator(items, multi_hop_max_dist=16, spatial_pos_max=64)

    return batch_data

def infer(doc, ncti, infer_model:BrepSeg):
    sel = ncti.SelectionManager(doc)
    if len(sel.ObjectNames) == 0:
        print(f"请先选择对象")
        return {}

    ai = ncti.AiModel(doc, sel.ObjectNames[0], 5, 5, 5)
    face_ids = ai.FaceID
    if not face_ids:
        print("Warning: No FaceID found in AI model, skipping processing")
        # 返回空的图结构
        graph_data = {
            "graph": {
                "num_nodes": 0,
                "num_edges": 0,
                "src_nodes": [],
                "dst_nodes": []
            },
            "node_data": {
                "x": [],
                "a": [],
                "y": [],
                "z": [],
                "l": [],
                "f": []
            },
            "edge_data": {
                "x": [],
                "l": [],
                "t": [],
                "a": [],
                "c": []
            },
            "graph_labels": {
                "angle_distance": [],
                "d2_distance": [],
                "spatial_pos": [],
                "edges_path": []
            }
        }
    else:
        # 提取图结构数据
        extract_start = time.time()
        graph_data = extract_graph_structure(ncti, doc, ai, sel.ObjectNames[0], face_ids)
        extract_end = time.time()
        print(f"提取图结构数据耗时: {extract_end - extract_start:.6f}秒")

    input_data = preprocess_graph(graph_data)

    device = next(infer_model.parameters()).device
    for key, value in input_data.items():
        if isinstance(value, torch.Tensor):
            input_data[key] = value.to(device)

    with torch.no_grad():
        # 调用模型的brep_encoder获取节点嵌入和图嵌入
        node_emb, graph_emb = infer_model.brep_encoder(input_data, last_state_only=True)

        # 处理节点嵌入
        node_emb = node_emb[0].permute(1, 0, 2)  # node_emb [batch_size, max_node_num+1, dim] with global node dim=0
        node_emb = node_emb[:, 1:, :]  # node_emb [batch_size, max_node_num, dim] without global node
        padding_mask = input_data["padding_mask"]  # [batch_size, max_node_num]
        node_pos = torch.where(padding_mask == False)  # [(batch_size, node_index)]
        node_z = node_emb[node_pos]  # [total_nodes, dim_z]
        padding_mask_ = ~padding_mask
        num_nodes_per_graph = torch.sum(padding_mask_.long(), dim=-1)  # [batch_size]
        graph_z = graph_emb.repeat_interleave(num_nodes_per_graph, dim=0).to(graph_emb.device)

        # 使用注意力机制融合节点嵌入和图嵌入
        z = infer_model.attention([node_z, graph_z])

        # 使用分类器预测每个面的类别
        node_seg = infer_model.classifier(z)  # [total_nodes, num_classes]

        # 获取预测结果
        predictions = torch.argmax(node_seg, dim=-1)  # [total_nodes]
        predictions = predictions.cpu().numpy()

        # 识别圆角（类别1表示圆角，0表示非圆角）
        # 注意：这里可以根据需要修改类别索引
        FILLET_CLASS = MANUAL_PARAMS["fillet_class"]
        fillet_faces = [i for i, pred in enumerate(predictions) if pred == FILLET_CLASS]
        print(f"识别到 {len(fillet_faces)} 个圆角面")

        # 识别圆角（类别1表示圆角，0表示非圆角）
        # 注意：这里可以根据需要修改类别索引
        FILLET_CLASS = MANUAL_PARAMS["fillet_class"]
        fillet_faces = [i for i, pred in enumerate(predictions) if pred == FILLET_CLASS]
        print(f"识别到 {len(fillet_faces)} 个圆角面")
        obj_names = [ai.objName for i in range(len(fillet_faces))]
        return fillet_faces, obj_names
