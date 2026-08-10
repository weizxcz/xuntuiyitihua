"""
BrepMFR 模型的 step 转 graph 模块。
将 STEP 文件转换为符合 BrepMFR 模型要求的图结构 JSON 格式。
整合自 BrepMFR-main/data/BrepMFR_json_to_graph_ncti.py
"""
import os
import gc
import json
import logging
import numpy as np
from itertools import repeat
from multiprocessing.pool import Pool
from pathlib import Path
from tqdm import tqdm

from src.utils.base_functions import (
    load_config_basic,
    save_json_data,
    load_json,
    init_ncti,
)
from src.utils.extractor_mfr_ncti import ExtractorNCTI
from src.data_utils.processors.divide_train_val_test import get_train_val_test_info

# 多进程时由 initializer 设置
_mfr_extractor = None


def _get_mfr_paths(config):
    """获取 MFR 相关路径（支持相对/绝对路径）"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config['data_path_infos']['use_absolute_path']

    label_dir = config['data_path_infos']['processed_label_data']
    output_dir = config['data_path_infos']['mfr_data_infos']['graphs_mfr_json']
    if not use_absolute:
        label_dir = os.path.join(base_dir, label_dir)
        output_dir = os.path.join(base_dir, output_dir)
    return label_dir, output_dir


def _mfr_initializer():
    """多进程初始化：为每个子进程创建 BrepMFRExtractor"""
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    global _mfr_extractor
    config = load_config_basic()
    ncti = init_ncti()
    mfr_config = _build_mfr_extractor_config(config)
    _mfr_extractor = BrepMFRExtractor(config=mfr_config, ncti=ncti)


def _build_mfr_extractor_config(config):
    """构建 BrepMFRExtractor 所需的 config 字典"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config['data_path_infos']['use_absolute_path']

    label_dir = config['data_path_infos']['processed_label_data']
    if not use_absolute:
        label_dir = os.path.join(base_dir, label_dir)

    mfr_graph_config = config.get('mfr_step2graph_infos', {})
    return {
        'label_dir': label_dir,
        'ai_u_count': mfr_graph_config.get('ai_u_count', 5),
        'ai_v_count': mfr_graph_config.get('ai_v_count', 5),
        'ai_edge_count': mfr_graph_config.get('ai_edge_count', 5),
    }


class BrepMFRExtractor:
    """BrepMFR 图提取器，使用 NCTI 内核处理 STEP 文件并生成图结构"""

    def __init__(self, config=None, ncti=None):
        if ncti is None:
            raise ValueError("BrepMFRExtractor 需要传入已初始化的 NCTI 实例")
        self.NCTI = ncti
        self.config = config or {}

    def process(self, step_file):
        """
        处理STEP文件，生成BrepMFR图结构。
        主要流程：
        1. 初始化CAD文档对象并导入STEP文件。
        2. 通过NCTI.AiModel()导入NCTI数据处理模块，提取面ID等信息。
        3. 提取面特征标签。
        4. 调用核心处理方法生成图结构。
        5. 清理文档并返回结果。
        """
        doc = None
        try:
            doc = self.NCTI.Document()
            doc.New("OCC", "DCM", 0)
            import_result = doc.RunCommand("cmd_ncti_import_file", str(step_file), "testbox")
            if not import_result:
                raise Exception("Failed to import STEP file")

            ai_u = self.config.get("ai_u_count", 5)
            ai_v = self.config.get("ai_v_count", 5)
            ai_edge = self.config.get("ai_edge_count", 5)
            ai = self.NCTI.AiModel(doc, "testbox", ai_u, ai_v, ai_edge)

            face_ids = ai.FaceID
            feature_labels = self._extract_feature_labels(str(step_file), len(face_ids)) if face_ids else None
            if feature_labels is None:
                logging.info(f"跳过 {step_file}：未找到标签文件")
                doc.Clear()
                return None

            json_data = self._process_core(doc, "testbox", ai, feature_labels)
            doc.Clear()
            return json_data
        except Exception as e:
            logging.error(f"处理 {step_file} 失败: {e}")
            if doc:
                try:
                    doc.Clear()
                except Exception:
                    pass
            raise

    def process_from_doc(self, doc, object_name, ai):
        """
        处理已有CAD文档对象，生成BrepMFR图结构。
        主要流程：
        1. 获取面ID。
        2. 构造默认特征标签。
        3. 调用核心处理方法生成图结构。
        参数:
            doc: NCTI.Document实例
            object_name: 对象名称
            ai: NCTI.AiModel实例
            
        Returns:
            dict: 符合BrepMFR格式的图结构JSON数据
        """
        try:
            # 直接使用已有的ai模型获取面ID
            face_ids = ai.FaceID
            if not face_ids or len(face_ids) == 0:
                return self._get_empty_graph_structure()
            
            # 由于是直接处理已有的文档，不需要标签文件
            feature_labels = [0] * len(face_ids)
            
            # 调用核心处理方法
            json_data = self._process_core(doc, object_name, ai, feature_labels)
            return json_data
        except Exception as e:
            logging.error(f"处理文档失败: {e}")
            raise

    def _process_core(self, doc, object_name, ai, feature_labels=None):
        """
        核心处理方法：将CAD文件转换为图结构表示
        该方法是数据处理的核心流程，负责从CAD对象中提取拓扑和几何信息，
        构建网络图结构及其相关的节点和边的特征数据。
        参数:
            doc: CAD文档对象，包含完整的CAD模型数据
            object_name (str): 要处理的对象名称，用于定位具体的CAD对象
            ai: CAD对象的接口，包含FaceID等拓扑信息
            feature_labels (optional): 节点特征标签，用于标注各个面的特征类型
        返回:
            dict: 包含以下键值对的字典：
                - graph: 图的拓扑结构，包含：
                    num_nodes: 图中的节点数（面的数量）
                    num_edges: 图中的边数
                    src_nodes: 边的源节点列表
                    dst_nodes: 边的目标节点列表
                - node_data: 节点特征数据，包含每个面的属性信息
                - edge_data: 边特征数据，包含每条边的属性信息
                - graph_labels: 图级别的几何拓扑属性信息，包含：
                    angle_distance: 三维角度距离矩阵
                    d2_distance: 二维距离矩阵
                    spatial_pos: 各个面的空间位置坐标
                    edges_path: 边的路径信息
        处理流程:
            1. 验证输入的FaceID是否有效，若为空则返回空图结构
            2. 创建NCTI提取器，获取面的几何信息
            3. 构建NetworkX图，提取节点和边的拓扑关系
            4. 提取节点和边的特征数据
            5. 计算空间位置、距离和路径等几何拓扑属性信息
            6. 将所有数据整合为标准格式返回
        """
        # 获取所有面的ID
        face_ids = ai.FaceID  # ai对象中包含所有面的ID列表
        if not face_ids or len(face_ids) == 0:
            # 如果没有面，直接返回空图结构
            return self._get_empty_graph_structure()
        
        # 创建NCTI提取器，用于几何和拓扑信息提取
        extractor = ExtractorNCTI(self.NCTI, doc, object_name)
        # 提取所有面的几何信息（如采样点、法向量等）
        extractor.get_face_info()
        # 构建NetworkX图，返回图对象、面数量、面ID列表
        nx_graph, num_faces, face_ids = extractor._build_graph()

        # 从图结构中提取边信息（源节点、目标节点、边ID）
        src_nodes, dst_nodes, edge_ids = self._extract_edge_info_from_graph(nx_graph)
        # 计算边数量
        num_edges = len(src_nodes)
        # 获取新边ID到原始索引的映射
        new_edge_id_to_original_idx = nx_graph.graph.get('new_edge_id_to_original_idx', {})

        # 提取所有节点（面）的特征数据
        node_data = self._extract_node_data(ai, face_ids, feature_labels)
        # 提取所有边的特征数据
        edge_data = self._extract_edge_data(ai, edge_ids, new_edge_id_to_original_idx)

        # 计算所有面的空间位置坐标
        spatial_pos = extractor.cal_spatial_pos()
        # 计算所有边的路径信息
        edge_path, _ = extractor.cal_edge_path()
        
        # 计算二维距离矩阵
        d2_distance = extractor.cal_d2_distance()
        a3_distance = extractor.cal_a3_distance()
        # 整合所有数据为标准字典格式
        return {
            "graph": {
                "num_nodes": int(num_faces),  # 节点数
                "num_edges": int(num_edges),  # 边数
                "src_nodes": src_nodes,  # 源节点列表
                "dst_nodes": dst_nodes   # 目标节点列表
            },
            "node_data": node_data,      # 节点特征数据
            "edge_data": edge_data,      # 边特征数据
            "graph_labels": {
                "angle_distance": a3_distance.tolist(),  # 三维角度距离
                "d2_distance": d2_distance.tolist(),      # 二维距离
                "spatial_pos": spatial_pos.tolist(),      # 空间位置
                "edges_path": edge_path.tolist()          # 边路径
            }
        }

    def _extract_edge_info_from_graph(self, nx_graph):
        """
        从NetworkX图结构中提取边的源节点、目标节点和边ID。
        """
        ordered_edges = nx_graph.graph.get('ordered_edges', [])
        if ordered_edges:
            src_nodes = [edge[1] for edge in ordered_edges]
            dst_nodes = [edge[2] for edge in ordered_edges]
            edge_ids = [edge[0] for edge in ordered_edges]
        else:
            src_nodes, dst_nodes, edge_ids = [], [], []
            for u, v, data in nx_graph.edges(data=True):
                src_nodes.append(u)
                dst_nodes.append(v)
                edge_ids.append(data['edge_idx'])
        return src_nodes, dst_nodes, edge_ids

    def _get_empty_graph_structure(self):
        """
        返回一个空的图结构字典。
        """
        return {
            "graph": {"num_nodes": 0, "num_edges": 0, "src_nodes": [], "dst_nodes": []},
            "node_data": {"x": [], "a": [], "y": [], "z": [], "l": [], "f": []},
            "edge_data": {"x": [], "l": [], "t": [], "a": [], "c": []},
            "graph_labels": {"angle_distance": [], "d2_distance": [], "spatial_pos": [], "edges_path": []}
        }

    def _extract_node_data(self, ai, face_ids, feature_labels=None):
        """
        提取所有节点（面）的特征数据，包括几何属性、邻接数、环数、类型等。
        """
        if feature_labels is None:
            feature_labels = [0] * len(face_ids)

        graph_face_attr = ai.FaceAttr
        FacePoints = ai.FacePoints
        FaceNormals = ai.FaceNormals
        FaceMask = ai.FaceMask
        graph_face_grid = self._extract_face_point_grid(FacePoints, FaceNormals, FaceMask)

        node_data = {"x": [], "a": [], "y": [], "z": [], "l": [], "f": []}
        for i, face_id in enumerate(face_ids):
            face_attr = graph_face_attr[i] if i < len(graph_face_attr) else []
            adjacent_count = int(face_attr[11]) if len(face_attr) > 11 else 0
            loops_count = int(face_attr[10]) if len(face_attr) > 10 else 0
            geo_type = self._get_face_geo_type(face_attr)

            node_data["x"].append(graph_face_grid[i] if i < len(graph_face_grid) else [])
            node_data["a"].append(adjacent_count)
            node_data["y"].append(float(face_attr[5]) if len(face_attr) > 5 else 0.0)
            node_data["z"].append(geo_type)
            node_data["l"].append(loops_count)
            node_data["f"].append(int(feature_labels[i]) if i < len(feature_labels) else 0)
        return node_data

    def _get_face_geo_type(self, face_attr):
        """
        判断面的几何类型：0-平面，1-圆柱，2-圆锥，3-球面，4-环面，5-Nurbs曲面。
        """

        if len(face_attr) <= 4:
            return 0
        if 1 in face_attr[:5]:
            return face_attr[:5].index(1)
        if len(face_attr) > 6 and face_attr[6] == 1:
            return 5
        return 0

    def _extract_feature_labels(self, step_file, num_faces):
        """
        从标签文件中提取每个面的特征标签。
        """
        part_id = os.path.splitext(os.path.basename(step_file))[0]
        label_dir = self.config.get("label_dir", "")
        label_file = os.path.join(label_dir, f"{part_id}.json")
        if not os.path.exists(label_file):
            return None

        feature_labels = np.zeros(num_faces, dtype=int)
        try:
            with open(label_file, 'r', encoding='utf-8') as f:
                label_data = json.load(f)
            if label_data and len(label_data) > 0:
                part_info = label_data[0]
                if len(part_info) > 1 and "seg" in part_info[1]:
                    seg_data = part_info[1]["seg"]
                    keys = np.array(list(seg_data.keys()), dtype=int)
                    values = np.array(list(seg_data.values()), dtype=int)
                    valid_mask = (keys >= 0) & (keys < num_faces)
                    valid_keys = keys[valid_mask]
                    valid_values = values[valid_mask]
                    # 批量赋值（无 Python 循环）
                    feature_labels[valid_keys] = valid_values
        except Exception as e:
            logging.error(f"读取标签文件 {label_file} 失败: {e}")
            return None
        return list(feature_labels)

    def _extract_face_point_grid(self, FacePoints, FaceNormals, FaceMask):
        """
        组合面采样点、法向量和mask为统一的网格特征（向量化实现）。
        """
        n = len(FacePoints)
        # 从第一个面推断网格维度：q（行数），m（每行点数）
        q = len(FacePoints[0])                     # 面内行数
        m = len(FacePoints[0][0]) // 3             # 每行的点数（坐标三元组数）
        # 将嵌套列表转换为 NumPy 数组并重塑为统一形状 (n, q, m, 3) 或 (n, q, m, 1)
        points_arr = np.array(FacePoints, dtype=float).reshape(n, q, m, 3)
        normals_arr = np.array(FaceNormals, dtype=float).reshape(n, q, m, 3)
        mask_arr = np.array(FaceMask, dtype=float).reshape(n, q, m, 1)
        # 沿最后一维拼接，得到 (n, q, m, 7)
        graph_face_grid = np.concatenate([points_arr, normals_arr, mask_arr], axis=3)
        # 转换回 Python 列表（保持与原函数输出格式一致）
        return graph_face_grid.tolist()

    def _extract_edge_point_grid(self, EdgePoints, EdgeTangents, dihedral_angles):
        """
        组合边采样点、切向量和二面角为统一的网格特征（向量化实现）。
        """
        n = len(EdgePoints)                      # 边的数量
        # 从第一个边推断每条边的采样点数 m
        m = len(EdgePoints[0]) // 3               # 假设所有边点数相同且能被3整除
        # 将 EdgePoints 和 EdgeTangents 转换为 (n, m, 3) 的数组
        points_arr = np.array(EdgePoints, dtype=float).reshape(n, m, 3)
        tangents_arr = np.array(EdgeTangents, dtype=float).reshape(n, m, 3)
        # 将 dihedral_angles 扩展为 (n, m, 1)，以便与 points 和 tangents 拼接
        dihedral_angles = np.array(dihedral_angles, dtype=float)  # (n,)
        dihedral_expanded = dihedral_angles[:, np.newaxis, np.newaxis]  # (n, 1, 1)
        dihedral_expanded = np.repeat(dihedral_expanded, m, axis=1)  # (n, m, 1)
        # 沿最后一维拼接，得到 (n, m, 7)
        combined = np.concatenate([points_arr, tangents_arr, dihedral_expanded], axis=2)
        # 转换为 Python 列表的列表（兼容原函数输出格式）
        graph_edge_grid = combined.tolist()
        return graph_edge_grid
    
    def _extract_edge_data(self, ai, edge_ids, new_edge_id_to_original_idx):
        """
        提取所有边的特征数据，包括长度、类型、二面角、凸性等。
        """
        edge_data = {"x": [], "l": [], "t": [], "a": [], "c": []}
        original_graph_edge_attr = ai.EdgeAttr
        EdgePoints = ai.EdgePoints
        EdgeTangents = ai.EdgeTangents
        try:
            if hasattr(ai, 'leftNormal') and hasattr(ai, 'rightNormal'):
                # 将列表转换为NumPy数组，形状为 (N, 3)
                left = np.array(ai.leftNormal, dtype=float)
                right = np.array(ai.rightNormal, dtype=float)
                # 批量计算点积和模长
                dots = np.sum(left * right, axis=1)                     # shape (N,)
                norms_left = np.linalg.norm(left, axis=1)               # shape (N,)
                norms_right = np.linalg.norm(right, axis=1)             # shape (N,)
                # 计算余弦值，处理除零情况
                with np.errstate(divide='ignore', invalid='ignore'):
                    cos_theta = dots / (norms_left * norms_right)
                    cos_theta = np.clip(cos_theta, -1.0, 1.0)           # 确保在[-1, 1]内
                # 计算角度
                angles = np.arccos(cos_theta)
                # 将模长为0的边对应的角度设为0（与原代码异常处理一致）
                invalid_mask = (norms_left == 0) | (norms_right == 0)
                angles[invalid_mask] = 0.0
                # 将可能出现的NaN也设为0
                angles = np.nan_to_num(angles, nan=0.0)
                # 转换为Python列表
                dihedral_angles = angles.tolist()
        except Exception:
            dihedral_angles = [0.0] * len(EdgePoints)
        edge_grids = self._extract_edge_point_grid(EdgePoints, EdgeTangents, dihedral_angles)
        for new_edge_id in edge_ids:
            original_idx = new_edge_id_to_original_idx.get(new_edge_id, None)
            if original_idx is None:
                edge_data["x"].append([])
                edge_data["l"].append(0.0)
                edge_data["t"].append(0)
                edge_data["a"].append(0.0)
                edge_data["c"].append(0)
                continue

            edge_attr = original_graph_edge_attr[original_idx] if original_idx < len(original_graph_edge_attr) else []
            length = float(edge_attr[3]) if len(edge_attr) > 3 else 0.0
            curve_type_list = [edge_attr[i] for i in [9,4,6,7,8]]
            try:
                curve_type = curve_type_list.index(1)
            except:
                curve_type = 0

            edge_grid = edge_grids[original_idx] if original_idx < len(edge_grids) else []
            dihedral_angle = dihedral_angles[original_idx] if original_idx < len(dihedral_angles) else 0.0

            convexity = 0
            if len(edge_attr) > 1 and edge_attr[1]:
                convexity = 1
            elif len(edge_attr) > 0 and edge_attr[0]:
                convexity = 2

            edge_data["x"].append(edge_grid)
            edge_data["l"].append(length)
            edge_data["t"].append(curve_type)
            edge_data["a"].append(dihedral_angle)
            edge_data["c"].append(convexity)
        return edge_data


def _process_one_mfr_file(args):
    """处理单个 step 文件，生成 MFR 格式 JSON"""
    global _mfr_extractor
    step_path, dataset_name = args
    config = load_config_basic()
    _, output_dir = _get_mfr_paths(config)
    os.makedirs(output_dir, exist_ok=True)
    json_filename = f"{step_path.stem}.json"
    json_path = os.path.join(output_dir, json_filename)

    if os.path.exists(json_path):
        logging.info(f"跳过 [{dataset_name}] {json_filename}：已存在")
        return (str(step_path.stem), True)

    try:
        json_data = _mfr_extractor.process(step_path)
        if json_data is None:
            return (str(step_path.stem), False)
        save_json_data(json_path, json_data)
        return (str(step_path.stem), True)
    except Exception as e:
        logging.error(f"处理 {step_path.stem} 失败: {e}")
        return (str(step_path.stem), False)


def _load_all_mfr_dataset_files(train_val_test_info_list, step_path_list):
    """加载所有数据集的 step 文件路径"""
    all_filtered_files = {}
    all_step_filenames = set()
    for step_dir in step_path_list:
        all_step_filenames.update({sf.stem for sf in Path(step_dir).glob("*.st*p")})

    for dataset in train_val_test_info_list:
        ds_name = dataset["name"]
        ds_txt_path = dataset["file_list_path"]
        ds_txt_files = set()
        if os.path.exists(ds_txt_path):
            with open(ds_txt_path, "r", encoding="utf-8") as f:
                for line in f:
                    fn = line.strip()
                    if fn:
                        ds_txt_files.add(fn)
        else:
            logging.warning(f"{ds_name} 的 txt 文件 {ds_txt_path} 不存在")
            continue

        ds_exist_files = ds_txt_files & all_step_filenames
        ds_step_files = []
        for step_dir in step_path_list:
            ds_step_files.extend([sf for sf in Path(step_dir).glob("*.st*p") if sf.stem in ds_exist_files])
        all_filtered_files[ds_name] = ds_step_files
        logging.info(f"{ds_name}: txt 中 {len(ds_txt_files)} 个，实际存在 {len(ds_exist_files)} 个 step")

    return all_filtered_files


def step2graph_mfr_batch():
    """
    MFR 批量 step 转 graph
    
    处理流程图：
    
    ┌─────────────────────────────────────────────────────────────┐
    │ step2graph_mfr_batch                                       │
    │  ↓                                                        │
    │ 加载配置(load_config_basic)                                │
    │  ↓                                                        │
    │ 获取训练/验证/测试集文件信息(get_train_val_test_info)      │
    │  ↓                                                        │
    │ 构建step文件路径列表                                       │
    │  ↓                                                        │
    │ 加载所有step文件(_load_all_mfr_dataset_files)              │
    │  ↓                                                        │
    │ 获取标签/输出路径(_get_mfr_paths)                          │
    │  ↓                                                        │
    │ 遍历每个数据集                                            │
    │  ↓                                                        │
    │   ┌─────────────────────────────────────────────────────┐  │
    │   │ 遍历step文件列表                                    │  │
    │   │  ↓                                                │  │
    │   │   单进程：初始化NCTI和BrepMFRExtractor              │  │
    │   │   多进程：Pool+_mfr_initializer                     │  │
    │   │  ↓                                                │  │
    │   │   处理单个step文件(_process_one_mfr_file)           │  │
    │   │    ↓                                              │  │
    │   │    BrepMFRExtractor.process                        │  │
    │   │      ↓                                            │  │
    │   │      导入STEP文件、构建AI模型、提取面ID             │  │
    │   │      ↓                                            │  │
    │   │      提取面特征标签(_extract_feature_labels)        │  │
    │   │      ↓                                            │  │
    │   │      核心处理(_process_core)                       │  │
    │   │        ↓                                          │  │
    │   │        ExtractorNCTI提取几何/拓扑信息              │  │
    │   │        构建图结构(_build_graph)                    │  │
    │   │        提取节点/边特征、空间/距离/路径属性         │  │
    │   │      ↓                                            │  │
    │   │      返回图结构JSON                                │  │
    │   │      ↓                                            │  │
    │   │      保存JSON(save_json_data)                      │  │
    │   └─────────────────────────────────────────────────────┘  │
    │  ↓                                                        │
    │  统计成功/失败数量                                        │
    └─────────────────────────────────────────────────────────────┘
    
    主要依赖的函数/类：
    - load_config_basic: 加载配置
    - get_train_val_test_info: 获取数据集文件信息
    - _get_mfr_paths: 获取标签/输出路径
    - _load_all_mfr_dataset_files: 加载step文件
    - BrepMFRExtractor: STEP转图结构核心类
    - ExtractorNCTI: 几何/拓扑信息提取
    - save_json_data: 保存结果
    """
    config = load_config_basic()
    train_val_test_info_list = get_train_val_test_info()
    use_public = config['data_path_infos']['use_public_data']
    use_real = config['data_path_infos']['use_real_data']
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    use_absolute = config['data_path_infos']['use_absolute_path']

    step_dirs = []
    if use_public:
        p = config['data_path_infos']['public_data_path_infos']['raw_step_data']
        step_dirs.append(p if use_absolute else os.path.join(base_dir, p))
    if use_real:
        p = config['data_path_infos']['real_data_path_infos']['raw_step_data']
        step_dirs.append(p if use_absolute else os.path.join(base_dir, p))

    if not step_dirs:
        logging.error("未配置任何 step 数据集路径")
        return

    all_filtered_files = _load_all_mfr_dataset_files(train_val_test_info_list, step_dirs)
    label_dir, output_dir = _get_mfr_paths(config)
    os.makedirs(output_dir, exist_ok=True)

    num_workers = config['step2graph_infos']['num_workers']
    success_count = 0
    fail_count = 0

    for dataset in train_val_test_info_list:
        ds_name = dataset["name"]
        ds_step_files = all_filtered_files.get(ds_name, [])
        if not ds_step_files:
            logging.info(f"【{ds_name}】无有效 step 文件，跳过")
            continue

        logging.info(f"【处理 {ds_name}】共 {len(ds_step_files)} 个 step 文件")
        process_args = list(zip(ds_step_files, repeat(ds_name)))

        if num_workers <= 1:
            global _mfr_extractor
            ncti = init_ncti()
            mfr_config = _build_mfr_extractor_config(config)
            _mfr_extractor = BrepMFRExtractor(config=mfr_config, ncti=ncti)
            for args in tqdm(process_args, desc=f"{ds_name} 进度"):
                stem, ok = _process_one_mfr_file(args)
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
        else:
            with Pool(processes=num_workers, initializer=_mfr_initializer) as pool:
                for result in tqdm(
                    pool.imap_unordered(_process_one_mfr_file, process_args),
                    total=len(process_args),
                    desc=f"{ds_name} 进度"
                ):
                    stem, ok = result
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
        gc.collect()

    logging.info(f"MFR 构图完成：成功 {success_count}，失败 {fail_count}")
