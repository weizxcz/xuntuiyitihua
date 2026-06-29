import numpy as np
import random
import math
import networkx as nx
import os


class ExtractorNCTI:
    def __init__(self, NCTI, doc, name):
        """
        初始化ExtractorNCTI类，设置缓存变量
        
        Args:
            NCTI: NCTI内核对象
            doc: 文档对象
            name: 模型名称
        """
        self.NCTI = NCTI
        self.doc = doc
        self.name = name
        
        self.max_distance = 1  # 最大直线距离，应为包围盒两个边界点距离
        self.sample_num = 512  # 采样个数
        self.dstb_cap = 64  # 分布裁切份数
        
        # 缓存变量
        self._graph_cache = {}
        self._point_sample_cache = {}  # 点采样缓存
        
        # 数据存储
        self.face_samples = []  # 采样缓存，n*self.sample_num*3，数值是坐标，取值R
        self.angle_samples = []  # 采样缓存，n*self.sample_num的一半*3，数值是坐标，取值R
        self.face_ids = []  # 面ID信息，n，数值0~(n-1)
        self.face_adj = []  # 邻接矩阵，n*n，数值0或1
        self.d2_distance = []  # d2距离，n*n*self.dstb_cap，数值0~1
        self.a3_distance = []  # a3距离, n*n*self.dstb_cap，数值0~1
        
    # 获取两点之间的绝对直线距离
    def get_dis(self, point1, point2):
        x_dis = point1[0] - point2[0]
        y_dis = point1[1] - point2[1]
        z_dis = point1[2] - point2[2]
        return math.sqrt(x_dis**2 + y_dis**2 + z_dis**2)
    
    # 获取两个点和一个顶点形成的夹角
    def get_angle(self, point1, point2, vertex):
        vector1 = [vertex[0] - point1[0], vertex[1] - point1[1], vertex[2] - point1[2]]
        vector2 = [vertex[0] - point2[0], vertex[1] - point2[1], vertex[2] - point2[2]]
        mod1 = math.sqrt(vector1[0]**2 + vector1[1]**2 + vector1[2]**2)
        mod2 = math.sqrt(vector2[0]**2 + vector2[1]**2 + vector2[2]**2)
        if mod1 < 1e-6 or mod2 < 1e-6:  # 规避point和vertex重复情况
            return 0
        dot = vector1[0]*vector2[0] + vector1[1]*vector2[1] + vector1[2]*vector2[2]
        cos_value = dot / (mod1 * mod2)  # 余弦值
        cos_value = max(-1.0, min(1.0, cos_value))  # 处理浮点精度误差
        angle_arc = math.acos(cos_value)
        return angle_arc / math.pi  # 获取的弧度值取值范围为0-pi，这里做一下归一化
    
    # 获取模型的全部面，并且提前计算包围盒边界计、采样点，防止重复计算
    def get_face_info(self):
        sel = self.NCTI.SelectionManager(self.doc)
        sel.ObjectNames = self.doc.AllNames()
        self.face_ids = self.doc.FindAllFaces(sel.ObjectNames[0])
        bd = self.doc.GetBoundingBox(sel.ObjectNames)
        bd_pt1 = (bd[0], bd[1], bd[2])
        bd_pt2 = (bd[3], bd[4], bd[5])
        self.max_distance = self.get_dis(bd_pt1, bd_pt2)  # 获取包围盒边界值以计算最大距离，用于距离值归一化

        self.face_samples = []  # 初始化一下，防止有重复录入
        for i in self.face_ids:
            self.face_samples.append(self.get_face_sample(i, self.sample_num))
            self.angle_samples.append(self.get_face_sample(i, self.sample_num//2))
    
    # 返回这个面上的num个随机点，每个点的存在形式是三维坐标
    def get_face_sample(self, face_id, num):
        # 检查缓存
        cache_key = (face_id, num)
        if cache_key in self._point_sample_cache:
            return self._point_sample_cache[cache_key]
            
        points = []
        while len(points) < num:
            uv = [random.random(), random.random()]
            pt = self.doc.GetFacePointFromUV(self.name, face_id, uv[0], uv[1])
            points.append([pt.X, pt.Y, pt.Z])
        
        # 缓存结果
        self._point_sample_cache[cache_key] = points
        return points
    
    def _build_graph(self):
        # 检查缓存是否存在
        cache_key = self.name
        if cache_key in self._graph_cache:
            return self._graph_cache[cache_key]
        
        # 1. 获取所有面
        if len(self.face_ids) == 0:
            self.get_face_info()
        
        face_ids = self.face_ids
        num_faces = len(face_ids)
        
        # 2. 使用新的NCTI AiModel edge APIs获取边ID和邻接面ID
        ai = self.NCTI.AiModel(self.doc, self.name)
        edge_ids_list = ai.EdgeID  # 一维边ID列表（含重复）
        face_eids_list = ai.FaceEID  # 边的左侧邻面ID
        face_fids_list = ai.FaceFID  # 边的右侧邻面ID
        
        # 获取边属性，用于获取边长
        edge_attrs_list = ai.EdgeAttr  # 边属性列表
        
        # 添加打印语句，验证原始数据
        print(f"DEBUG: num_faces={num_faces}, max_face_id={max(face_ids) if face_ids else 0}, edge_ids_list length={len(edge_ids_list)}")
        
        # 3. 构建面ID到索引的映射
        face_id_to_idx = {face_id: idx for idx, face_id in enumerate(face_ids)}
        
        # 4. 构建邻接图
        nx_graph = nx.DiGraph()  # 使用有向图来支持双向边的不同ID
        nx_graph.add_nodes_from(range(num_faces))
        
        # 5. 新的边ID分配策略：
        #    - 找到所有唯一的边对（基于FaceEID和FaceFID的组合，不考虑方向）
        #    - FaceEID < FaceFID 的边分配偶数ID（0, 2, 4, 6...）
        #    - FaceEID > FaceFID 的边分配奇数ID（1, 3, 5, 7...）
        #    - 0与1对应一条双向边，2与3对应一条双向边
        
        # 存储原始EdgeID到新边ID的映射（用于后续边数据提取）
        # key: (FaceEID, FaceFID) 或 (FaceFID, FaceEID)，value: 新边ID
        edge_id_mapping = {}
        
        # 存储唯一的边对（用于分配偶数ID）
        # key: (min_face_id, max_face_id)，value: (FaceEID, FaceFID, length, original_edge_id, original_idx)
        unique_edge_pairs = {}
        
        # 第一步：收集所有唯一的边对，并记录对应的原始EdgeID和原始索引
        for i, (original_eid, feid, ffid) in enumerate(zip(edge_ids_list, face_eids_list, face_fids_list)):
            # 检查两个面是否都在face_ids列表中
            if feid not in face_id_to_idx or ffid not in face_id_to_idx:
                continue
            
            # 获取边长
            length = 0.0
            if edge_attrs_list and i < len(edge_attrs_list):
                edge_attr = edge_attrs_list[i]
                if len(edge_attr) > 3:
                    length = edge_attr[3]
            
            # 创建唯一的边对键（不考虑方向）
            min_face_id = min(feid, ffid)
            max_face_id = max(feid, ffid)
            edge_pair_key = (min_face_id, max_face_id)
            
            # 如果边对不存在，或存在但当前边更长，则更新
            if edge_pair_key not in unique_edge_pairs:
                unique_edge_pairs[edge_pair_key] = (feid, ffid, length, original_eid, i)
            else:
                # 比较边长，保留最长边
                current_length = unique_edge_pairs[edge_pair_key][2]
                if length > current_length:
                    unique_edge_pairs[edge_pair_key] = (feid, ffid, length, original_eid, i)
        
        # 第二步：创建从(FaceEID, FaceFID)到原始边数据索引的映射
        # 这个映射基于unique_edge_pairs中选择的边，确保一致性
        # 注意：对于双向边，两个方向使用相同的原始索引（因为它们代表同一条边）
        face_pair_to_original_idx = {}
        for edge_pair_key, (feid, ffid, length, original_eid, original_idx) in unique_edge_pairs.items():
            # 使用(FaceEID, FaceFID)作为键，存储原始索引
            face_pair_key = (feid, ffid)
            face_pair_to_original_idx[face_pair_key] = original_idx
            # 同时存储反向边的映射（使用相同的原始索引）
            reverse_pair_key = (ffid, feid)
            face_pair_to_original_idx[reverse_pair_key] = original_idx
        
        # 第三步：为每条唯一的边对分配偶数ID，并创建映射
        new_edge_id_even = 0  # 偶数ID从0开始
        
        # 创建从新边ID到原始边数据索引的映射
        new_edge_id_to_original_idx = {}
        
        for edge_pair_key, (feid, ffid, length, original_eid, original_idx) in unique_edge_pairs.items():
            # 为这条边对分配偶数ID
            even_id = new_edge_id_even
            odd_id = new_edge_id_even + 1
            
            # 创建映射：FaceEID < FaceFID 的边使用偶数ID，FaceEID > FaceFID 的边使用奇数ID
            if feid < ffid:
                # 原始方向：FaceEID -> FaceFID，使用偶数ID
                edge_id_mapping[(feid, ffid)] = even_id
                # 反向：FaceFID -> FaceEID，使用奇数ID
                edge_id_mapping[(ffid, feid)] = odd_id
                
                # 创建从新边ID到原始边数据索引的映射
                if (feid, ffid) in face_pair_to_original_idx:
                    new_edge_id_to_original_idx[even_id] = face_pair_to_original_idx[(feid, ffid)]
                if (ffid, feid) in face_pair_to_original_idx:
                    new_edge_id_to_original_idx[odd_id] = face_pair_to_original_idx[(ffid, feid)]
            else:
                # 原始方向：FaceEID -> FaceFID，使用奇数ID
                edge_id_mapping[(feid, ffid)] = odd_id
                # 反向：FaceFID -> FaceEID，使用偶数ID
                edge_id_mapping[(ffid, feid)] = even_id
                
                # 创建从新边ID到原始边数据索引的映射
                if (feid, ffid) in face_pair_to_original_idx:
                    new_edge_id_to_original_idx[odd_id] = face_pair_to_original_idx[(feid, ffid)]
                if (ffid, feid) in face_pair_to_original_idx:
                    new_edge_id_to_original_idx[even_id] = face_pair_to_original_idx[(ffid, feid)]
            
            new_edge_id_even += 2  # 每次增加2，为下一条双向边预留空间
        
        # 第四步：创建有序的边列表，按照边ID的顺序存储
        # 格式：[(edge_id, u, v, length, original_eid), ...]
        ordered_edges = []
        
        # 按照边ID的顺序添加边
        for edge_pair_key, (feid, ffid, length, original_eid, original_idx) in unique_edge_pairs.items():
            try:
                # 获取面索引
                u = face_id_to_idx[feid]
                v = face_id_to_idx[ffid]
                
                # 获取新的边ID
                new_edge_id_uv = edge_id_mapping[(feid, ffid)]
                new_edge_id_vu = edge_id_mapping[(ffid, feid)]
                
                # 按照边ID的顺序添加到有序列表
                # 先添加FaceEID < FaceFID的边（偶数ID），再添加反向边（奇数ID）
                if feid < ffid:
                    ordered_edges.append((new_edge_id_uv, u, v, length, original_eid))
                    ordered_edges.append((new_edge_id_vu, v, u, length, original_eid))
                else:
                    ordered_edges.append((new_edge_id_vu, v, u, length, original_eid))
                    ordered_edges.append((new_edge_id_uv, u, v, length, original_eid))
                
                # 添加有向边u->v（使用新的边ID）
                nx_graph.add_edge(u, v, edge_idx=new_edge_id_uv, length=length, original_eid=original_eid)
                
                # 添加有向边v->u（使用新的边ID）
                nx_graph.add_edge(v, u, edge_idx=new_edge_id_vu, length=length, original_eid=original_eid)
                
            except Exception as e:
                print(f"Error processing edge pair {edge_pair_key}: {e}")
                continue
        
        # 按照边ID排序
        ordered_edges.sort(key=lambda x: x[0])
        
        # 将边ID映射和有序边列表存储到图中，以便后续使用
        nx_graph.graph['edge_id_mapping'] = edge_id_mapping
        nx_graph.graph['new_edge_id_to_original_idx'] = new_edge_id_to_original_idx
        nx_graph.graph['ordered_edges'] = ordered_edges
        
        # 添加打印语句，验证最终的边ID范围
        all_edge_ids = []
        for u, v, data in nx_graph.edges(data=True):
            all_edge_ids.append(data['edge_idx'])
        if all_edge_ids:
            print(f"DEBUG: All edge IDs range from {min(all_edge_ids)} to {max(all_edge_ids)}, num_edges={len(all_edge_ids)}, unique_edge_pairs={len(unique_edge_pairs)}")
        
        # 缓存结果
        result = (nx_graph, num_faces, face_ids)
        self._graph_cache[cache_key] = result
        
        return result
    
    def cal_spatial_pos(self):
        """
        计算所有面之间的空间位置矩阵
        
        Returns:
            spatial_pos: 空间位置矩阵，形状为(num_faces, num_faces)
        """
        # 1. 构建邻接图
        nx_graph, num_faces, _ = self._build_graph()
        
        # 2. 计算spatial_pos
        path_lengths = nx.floyd_warshall_numpy(nx_graph, weight=None)
        path_lengths = path_lengths.astype(np.int32)
        
        # 3. 限制路径长度在0-62之间，避免索引越界
        # 注意：collator.py中的pad_spatial_pos_unsqueeze函数会对spatial_pos加1，
        # 所以这里需要限制在0-62，加1后变成1-63，符合模型的索引范围
        path_lengths = np.clip(path_lengths, 0, 62)

        return path_lengths
    
    def cal_edge_path(self):
        """
        计算所有面之间的边路径矩阵
        
        Returns:
            edge_path: 边路径矩阵，形状为(num_faces, num_faces, max_distance)
            spatial_pos: 空间位置矩阵，形状为(num_faces, num_faces)
        """
        # 1. 构建邻接图
        nx_graph, num_faces, _ = self._build_graph()
        
        # 2. 计算spatial_pos和max_distance
        path_lengths = nx.floyd_warshall_numpy(nx_graph, weight=None)
        path_lengths = path_lengths.astype(np.int32)
        max_distance = int(np.max(path_lengths))
        
        # 3. 计算edge_path
        # edge_path是三维矩阵，形状为[num_faces, num_faces, max_distance]
        # 第m个二维矩阵的第n行表示节点m到节点n的边链索引
        # 不足max_distance的用-1填充，自己到自己也是-1
        edge_path = -np.ones((num_faces, num_faces, max_distance), dtype=np.int32)
        
        # 使用nx.shortest_path获取所有节点对之间的最短路径
        for m in range(num_faces):  # m: 源节点（第m个二维矩阵）
            for n in range(num_faces):  # n: 目标节点（第n行）
                # 自己到自己用-1填充，不需要计算路径
                if m == n:
                    continue
                    
                try:
                    # 获取节点m到节点n的最短路径
                    path = nx.shortest_path(nx_graph, source=m, target=n)
                    path_len = len(path) - 1  # 路径包含path_len条边
                    
                    # 只填充实际需要的边链步骤
                    if path_len > 0 and path_len <= max_distance:
                        for step in range(path_len):
                            # 获取路径中的相邻节点对
                            u = path[step]
                            v = path[step + 1]
                            # 获取边的ID
                            edge_idx = nx_graph[u][v]['edge_idx']
                            # 填充到edge_path[m][n][step]位置
                            edge_path[m, n, step] = edge_idx
                    # 超出max_distance的情况已经用-1填充，无需处理
                except nx.NetworkXNoPath:
                    # 如果没有路径，保持为-1
                    continue
        
        return edge_path, path_lengths
    
    def cal_d2_distance(self):
        """
        计算所有面之间的d2距离矩阵
        
        Returns:
            d2_distance: d2距离矩阵，形状为(num_faces, num_faces, 64)
        """
        if len(self.face_ids) == 0:
            self.get_face_info()
        
        n = len(self.face_ids)
        self.d2_distance = np.zeros((n, n, self.dstb_cap), dtype=np.float32)
        
        for i in range(n):
            for j in range(n):
                sample1 = self.face_samples[i]
                sample2 = self.face_samples[j]
                distribution = np.zeros((self.dstb_cap), dtype=int)
                arr_shuffled = random.sample(range(self.sample_num), self.sample_num)
                for k in range(self.sample_num):
                    distance = self.get_dis(sample1[k], sample2[arr_shuffled[k]]) / self.max_distance
                    index = math.floor(distance * self.dstb_cap)
                    index = min(index, self.dstb_cap - 1)  # 边界检查
                    distribution[index] += 1
                hist_ratio = distribution / self.sample_num
                self.d2_distance[i][j] = hist_ratio
        
        return self.d2_distance
    
    def cal_a3_distance(self):
        """
        计算所有面之间的a3距离矩阵
        
        Returns:
            a3_distance: a3距离矩阵，形状为(num_faces, num_faces, 64)
        """
        if len(self.face_ids) == 0:
            self.get_face_info()
        
        n = len(self.face_ids)
        self.a3_distance = np.zeros((n, n, self.dstb_cap), dtype=np.float32)
        
        for i in range(n):
            for j in range(n):
                sample1 = self.face_samples[i]
                sample2 = self.face_samples[j]
                vertexes = self.angle_samples[i] + self.angle_samples[j]
                arr_shuffled_face = random.sample(range(self.sample_num), self.sample_num)
                arr_shuffled_vertex = random.sample(range(len(vertexes)), self.sample_num)
                distribution = np.zeros((self.dstb_cap), dtype=int)
                for k in range(self.sample_num):
                    angle = self.get_angle(sample1[k], sample2[arr_shuffled_face[k]], vertexes[arr_shuffled_vertex[k]])
                    index = math.floor(angle * self.dstb_cap)
                    index = min(index, self.dstb_cap - 1)  # 边界检查
                    distribution[index] += 1
                hist_ratio = distribution / self.sample_num
                self.a3_distance[i][j] = hist_ratio
        
        return self.a3_distance
    
    def save_to_json(self, output_path):
        """
        将所有四个矩阵保存到JSON文件
        
        Args:
            output_path: 输出JSON文件路径
        """
        import json
        
        # 计算所有矩阵
        spatial_pos = self.cal_spatial_pos()
        edge_path, _ = self.cal_edge_path()
        d2_distance = self.cal_d2_distance()
        a3_distance = self.cal_a3_distance()
        
        # 准备数据
        data = {
            "spatial_pos": spatial_pos.tolist(),
            "edge_path": edge_path.tolist(),
            "d2_distance": d2_distance.tolist(),
            "a3_distance": a3_distance.tolist(),
            "face_count": len(self.face_ids)
        }
        
        # 保存到JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"所有矩阵已保存到 {output_path}")