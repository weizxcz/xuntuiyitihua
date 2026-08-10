import numpy as np

from ai.brep_mfr.extractor_ncti import ExtractorNCTI

class BrepMFRExtractor:
    def __init__(self, ncti):
        self.NCTI = ncti

    def _get_empty_graph_structure(self):
        """返回空的图结构"""
        return {
            "graph": {"num_nodes": 0, "num_edges": 0, "src_nodes": [], "dst_nodes": []},
            "node_data": {"x": [], "a": [], "y": [], "z": [], "l": [], "f": []},
            "edge_data": {"x": [], "l": [], "t": [], "a": [], "c": []},
            "graph_labels": {"angle_distance": [], "d2_distance": [], "spatial_pos": [], "edges_path": []}
        }

    def _extract_edge_info_from_graph(self, nx_graph):
        """从NetworkX图中提取边信息"""
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

    def extract_face_point_grid(self, FacePoints, FaceNormals, FaceMask):
        """
        从AAGNet复制的UV网格提取方法，与base_utils.py中的实现完全相同
        返回7维特征（3坐标+3法线+1掩码），格式为 [面数, 5, 5, 7]

        Args:
            FacePoints: 面的点坐标列表
            FaceNormals: 面的法向量列表
            FaceMask: 面的掩码列表

        Returns:
            list: 每个面的UV网格特征列表，格式为 [面数, 5, 5, 7]
        """
        graph_face_grid = []
        for points, normals, mask in zip(FacePoints, FaceNormals, FaceMask):
            points_arr = np.array(points, dtype=np.float32).reshape((5, 5, 3))
            normals_arr = np.array(normals, dtype=np.float32).reshape((5, 5, 3))
            mask_arr = np.array(mask, dtype=np.float32).reshape((5, 5, 1))
            single_grid = np.concatenate([points_arr, normals_arr, mask_arr], axis=2)
            # 移除转置操作，保持格式为 [5, 5, 7]
            graph_face_grid.append(single_grid.tolist())
        return graph_face_grid

    def extract_edge_point_grid(self, EdgePoints, EdgeTangents, dihedral_angles):
        """
        提取边的网格点特征，格式为 [边数, 5, 7]
        其中7维为：3坐标+3切线+1二面角

        Args:
            EdgePoints: 边的点坐标列表，格式为 [边数, 15] (5点×3坐标)
            EdgeTangents: 边的切线方向列表，格式为 [边数, 15] (5点×3切线)
            dihedral_angles: 每条边的二面角值列表，格式为 [边数]

        Returns:
            list: 每个边的网格特征列表
        """
        graph_edge_grid = []
        for i, (points, tangents) in enumerate(zip(EdgePoints, EdgeTangents)):
            # 直接使用5个点的数据，无需提取
            # 提取坐标
            points_arr = np.array(points, dtype=np.float32).reshape((5, 3))

            # 提取切线
            tangents_arr = np.array(tangents, dtype=np.float32).reshape((5, 3))

            # 获取当前边的二面角值
            dihedral_angle = dihedral_angles[i] if i < len(dihedral_angles) else 0.0
            # 创建第七维，使用二面角值
            seventh_dim = np.full((5, 1), dihedral_angle, dtype=np.float32)
            # 组合数据：3坐标 + 3切线 + 1二面角 = 7维
            single_grid = np.concatenate([points_arr, tangents_arr, seventh_dim], axis=1)

            graph_edge_grid.append(single_grid.tolist())
        return graph_edge_grid

    def _get_face_geo_type(self, face_attr):
        """根据面属性确定几何类型: 0:平面, 1:圆柱, 2:圆锥, 3:球面, 4:环面"""
        if len(face_attr) <= 4:
            return 0
        if face_attr[0]: return 0
        if face_attr[1]: return 1
        if face_attr[2]: return 2
        if face_attr[3]: return 3
        if face_attr[4]: return 4
        return 0

    def _extract_node_data(self, ai, face_ids, feature_labels=None):
        """
        提取节点（面）数据

        Args:
            ai: NCTI.AiModel实例
            face_ids: 面ID列表
            feature_labels (list, optional): 特征标签列表，None表示使用默认值0

        Returns:
            dict: 节点数据字典，包含x、a、y、z、l、f字段
        """
        # 如果没有提供标签，使用默认值0
        if feature_labels is None:
            feature_labels = [0] * len(face_ids)

        # 批量获取所有面属性
        graph_face_attr = ai.FaceAttr
        FacePoints = ai.FacePoints
        FaceNormals = ai.FaceNormals
        FaceMask = ai.FaceMask

        # 提取UV网格
        graph_face_grid = self.extract_face_point_grid(FacePoints, FaceNormals, FaceMask)

        # 初始化节点数据
        node_data = {"x": [], "a": [], "y": [], "z": [], "l": [], "f": []}

        for i, face_id in enumerate(face_ids):
            face_attr = graph_face_attr[i] if i < len(graph_face_attr) else []

            # 提取面属性
            adjacent_count = int(face_attr[11]) if len(face_attr) > 11 else 0
            loops_count = int(face_attr[10]) if len(face_attr) > 10 else 0
            area = float(np.float32(face_attr[5])) if len(face_attr) > 5 else 0.0

            # 确定面几何类型
            geo_type = self._get_face_geo_type(face_attr)

            # 添加到节点数据
            node_data["x"].append(graph_face_grid[i] if i < len(graph_face_grid) else [])
            node_data["a"].append(adjacent_count)
            node_data["y"].append(area)
            node_data["z"].append(geo_type)
            node_data["l"].append(loops_count)
            node_data["f"].append(feature_labels[i] if i < len(feature_labels) else 0)

        return node_data

    def _extract_edge_data(self, ai, edge_ids, new_edge_id_to_original_idx):
        """
        提取边数据

        Args:
            ai: NCTI.AiModel实例
            edge_ids: 新的边ID列表（从0开始的连续值）
            new_edge_id_to_original_idx: 从新边ID到原始边数据索引的映射字典

        Returns:
            dict: 边数据字典，包含x、l、t、a、c字段
        """
        edge_data = {
            "x": [],  # 边的网格特征
            "l": [],  # 边长
            "t": [],  # 边的曲线类型
            "a": [],  # 法线夹角（二面角）
            "c": []  # 边的凹凸类型
        }

        # 批量获取所有边属性（与AAGExtractor相同方式）
        original_graph_edge_attr = ai.EdgeAttr

        # 获取边的点坐标和切线方向
        EdgePoints = ai.EdgePoints
        EdgeTangents = ai.EdgeTangents

        # 获取所有边的原始EdgeID列表
        edge_ids_all = ai.EdgeID if hasattr(ai, 'EdgeID') else []

        # 计算所有边的二面角（基于原始边数据索引）
        dihedral_angles = []
        try:
            # 检查ai是否有leftNormal和rightNormal属性
            if hasattr(ai, 'leftNormal') and hasattr(ai, 'rightNormal'):
                left_normals = ai.leftNormal
                right_normals = ai.rightNormal

                # 确保索引有效
                if isinstance(left_normals, list) and isinstance(right_normals, list):
                    # 为所有原始边计算二面角
                    for i, original_edge_id in enumerate(edge_ids_all):
                        # 计算二面角
                        dihedral_angle = 0.0
                        try:
                            if i < len(left_normals) and i < len(right_normals):
                                # 获取对应的法线向量
                                left_normal = left_normals[i]
                                right_normal = right_normals[i]

                                # 计算二面角
                                if left_normal and right_normal:
                                    n1 = np.array(left_normal)
                                    n2 = np.array(right_normal)

                                    # 计算点积
                                    dot = np.dot(n1, n2)

                                    # 计算向量模长
                                    mag1 = np.linalg.norm(n1)
                                    mag2 = np.linalg.norm(n2)

                                    if mag1 * mag2 != 0:
                                        # 计算夹角（弧度制）
                                        cos_theta = max(min(dot / (mag1 * mag2), 1.0), -1.0)
                                        angle = np.arccos(cos_theta)
                                        dihedral_angle = float(np.float32(angle))  # 转换为32位浮点数
                        except Exception as e:
                            # 只在出错时打印，避免过多输出
                            # print(f"Error calculating dihedral angle for edge {original_edge_id}: {e}")
                            pass
                        dihedral_angles.append(dihedral_angle)
            else:
                # 如果没有leftNormal和rightNormal属性，使用默认值0.0
                dihedral_angles = [0.0] * len(EdgePoints)
        except Exception as e:
            # 如果出错，使用默认值0.0
            print(f"Error calculating dihedral angles: {e}")
            dihedral_angles = [0.0] * len(EdgePoints)

        # 提取边的网格特征（基于原始边数据索引）
        edge_grids = self.extract_edge_point_grid(EdgePoints, EdgeTangents, dihedral_angles)

        # 对于每个新的边ID，使用映射找到对应的原始边数据索引
        for new_edge_id in edge_ids:
            # 获取对应的原始边数据索引
            original_idx = new_edge_id_to_original_idx.get(new_edge_id, None)

            if original_idx is None:
                # 如果找不到映射，使用默认值
                print(f"Warning: No mapping found for new edge ID {new_edge_id}, using default values")
                edge_data["x"].append([])
                edge_data["l"].append(0.0)
                edge_data["t"].append(0)
                edge_data["a"].append(0.0)
                edge_data["c"].append(0)
                continue

            # 获取边属性
            edge_attr = original_graph_edge_attr[original_idx] if original_idx < len(original_graph_edge_attr) else []

            # 提取边属性数据
            # graph_edge_attr: [是否为凹边, 是否为凸边, 是否为光滑边, 边长, 是否为圆弧边, 是否为封闭边, 是否为椭圆边, 是否为非有理b样条, 是否为有理b样条, 是否为直线边]
            length = edge_attr[3] if len(edge_attr) > 3 else 0.0  # 边长（第3列）
            length = float(np.float32(length))  # 转换为32位浮点数

            # 确定边的曲线类型
            # 0: 直线边, 1: 圆弧边, 2: 椭圆边, 3: 非有理b样条, 4: 有理b样条, 其他: 0
            curve_type = 0
            if len(edge_attr) > 9:
                if edge_attr[9]:  # 是否为直线边
                    curve_type = 0
                elif edge_attr[4]:  # 是否为圆弧边
                    curve_type = 1
                elif edge_attr[6]:  # 是否为椭圆边
                    curve_type = 2
                elif edge_attr[7]:  # 是否为非有理b样条
                    curve_type = 3
                elif edge_attr[8]:  # 是否为有理b样条
                    curve_type = 4

            # 获取边的网格特征
            edge_grid = edge_grids[original_idx] if original_idx < len(edge_grids) else []

            # 获取当前边的二面角值
            dihedral_angle = dihedral_angles[original_idx] if original_idx < len(dihedral_angles) else 0.0

            # 计算凹凸类型
            # 0: 平滑边, 1: 凸边, 2: 凹边
            convexity = 0  # 默认平滑边
            if len(edge_attr) > 1 and edge_attr[1]:  # 检查是否为凸边
                convexity = 1
            elif len(edge_attr) > 0 and edge_attr[0]:  # 检查是否为凹边
                convexity = 2

            # 添加到边数据
            edge_data["x"].append(edge_grid)
            edge_data["l"].append(length)
            edge_data["t"].append(curve_type)
            edge_data["a"].append(dihedral_angle)
            edge_data["c"].append(convexity)

        return edge_data

    def process_core(self, doc, ai_object, object_name, face_ids, feature_labels=None):
        if not face_ids or len(face_ids) == 0:
            print("Warning: No faces found, returning empty graph structure")
            return self._get_empty_graph_structure()

        extractor = ExtractorNCTI(self.NCTI, doc, object_name)
        extractor.get_face_info()
        nx_graph, num_faces, face_ids = extractor._build_graph()

        # 提取边信息
        src_nodes, dst_nodes, edge_ids = self._extract_edge_info_from_graph(nx_graph)
        num_edges = len(src_nodes)

        # 获取边ID映射
        new_edge_id_to_original_idx = nx_graph.graph.get('new_edge_id_to_original_idx', {})

        # 提取节点和边数据
        node_data = self._extract_node_data(ai_object, face_ids, feature_labels)
        edge_data = self._extract_edge_data(ai_object, edge_ids, new_edge_id_to_original_idx)

        # 计算距离矩阵
        spatial_pos = extractor.cal_spatial_pos()
        edge_path, _ = extractor.cal_edge_path()
        d2_distance = extractor.cal_d2_distance()
        a3_distance = extractor.cal_a3_distance()

        # 转换距离矩阵为32位浮点数
        if isinstance(d2_distance, np.ndarray):
            d2_distance = d2_distance.astype(np.float32)
        if isinstance(a3_distance, np.ndarray):
            a3_distance = a3_distance.astype(np.float32)

        # 构建并返回最终JSON结构
        return {
            "graph": {
                "num_nodes": num_faces,
                "num_edges": num_edges,
                "src_nodes": src_nodes,
                "dst_nodes": dst_nodes
            },
            "node_data": node_data,
            "edge_data": edge_data,
            "graph_labels": {
                "angle_distance": a3_distance.tolist(),
                "d2_distance": d2_distance.tolist(),
                "spatial_pos": spatial_pos.tolist(),
                "edges_path": edge_path.tolist()
            }
        }


