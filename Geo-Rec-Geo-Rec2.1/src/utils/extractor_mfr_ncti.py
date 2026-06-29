"""
BrepMFR 图提取器依赖的 ExtractorNCTI 类。
用于计算 d2_distance、a3_distance、spatial_pos、edge_path 等 MFR 图属性。
来源：BrepMFR-main/data/extractor_ncti.py
"""
import numpy as np
import random
import math
import networkx as nx
from concurrent.futures import ThreadPoolExecutor
from collections import deque

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
        self.face_ids = []  # 面ID信息，n，数值0~(n-1)
        self.face_adj = []  # 邻接矩阵，n*n，数值0或1
        self.d2_distance = []  # d2距离，n*n*self.dstb_cap，数值0~1
        self.a3_distance = []  # a3距离, n*n*self.dstb_cap，数值0~1
        self.nx_graph, self.num_faces, _ = self._build_graph()

    def get_dis(self, point1, point2):
        """
        计算两点之间的欧氏距离，作为几何特征基础。
        """
        distance = np.linalg.norm(np.array(point1) - np.array(point2))
        return distance

    def get_angle(self, point1, point2, vertex):
        """
        计算两个点和一个顶点形成的夹角（归一化到[0,1]），用于a3距离分布。
        """
        vector1 = [vertex[0] - point1[0], vertex[1] - point1[1], vertex[2] - point1[2]]
        vector2 = [vertex[0] - point2[0], vertex[1] - point2[1], vertex[2] - point2[2]]
        mod1 = math.sqrt(vector1[0]**2 + vector1[1]**2 + vector1[2]**2)
        mod2 = math.sqrt(vector2[0]**2 + vector2[1]**2 + vector2[2]**2)
        if mod1 < 1e-6 or mod2 < 1e-6:
            return 0
        dot = vector1[0]*vector2[0] + vector1[1]*vector2[1] + vector1[2]*vector2[2]
        cos_value = dot / (mod1 * mod2)
        cos_value = max(-1.0, min(1.0, cos_value))
        angle_arc = math.acos(cos_value)
        return angle_arc / math.pi

    def get_face_info(self):
        """
        获取模型所有面ID，计算包围盒最大距离，并对每个面采样点和角点。
        主要用于后续距离和角度分布计算。
        """
        sel = self.NCTI.SelectionManager(self.doc)
        sel.ObjectNames = self.doc.AllNames()
        self.face_ids = self.doc.FindAllFaces(sel.ObjectNames[0])
        bd = self.doc.GetBoundingBox(sel.ObjectNames)
        bd_pt1 = [bd[0], bd[1], bd[2]]
        bd_pt2 = [bd[3], bd[4], bd[5]]
        self.max_distance = self.get_dis(bd_pt1, bd_pt2)
        self.parallel_sample_threads_simple()  # 使用多进程加速采样

    def get_face_sample(self, face_id, num,sample_type = 'points'):
        """
        在指定面上随机采样num个点，作为距离/角度分布的基础。
        支持缓存避免重复采样。
        """
        cache_key = (face_id, num)
        if cache_key in self._point_sample_cache:
            return self._point_sample_cache[cache_key]
        points = []
        if sample_type == 'points':
            base_seed = 0
        else:
            base_seed = num+1
        while len(points) < num:
            num_points =  len(points)
            rng = random.Random(base_seed+num_points)
            uv = [rng.random(), rng.random()]
            pt = self.doc.GetFacePointFromUV(self.name, face_id, uv[0], uv[1])
            points.append([pt.X, pt.Y, pt.Z])
        self._point_sample_cache[cache_key] = points
        return points

    def process_face_sample(self, face_id): 
        """处理单个面的采样，返回采样点列表"""
        face_samples = self.get_face_sample(face_id, self.sample_num, sample_type='points')
        angle_samples = self.get_face_sample(face_id, self.sample_num//2, sample_type='angles')
        return (face_samples, angle_samples)
    
    def parallel_sample_threads_simple(self):
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(self.process_face_sample, i)
                for i in self.face_ids
            ]
            results = [f.result() for f in futures]  # 保持顺序
        # 按顺序解包
        self.face_samples = [r[0] for r in results]  # 采样缓存，n*self.sample_num*3，数值是坐标，取值R
        self.angle_samples = [r[1] for r in results]  # 采样缓存，n*self.sample_num的一半*3，数值是坐标，取值R

    def _build_graph(self):
        """
        构建面之间的有向邻接图，提取面与面之间的边关系及映射。
        返回：
            nx_graph: NetworkX有向图对象，包含所有面和边的关系及属性
            num_faces: 面的数量
            face_ids: 面ID列表
        主要分为以下几个部分：
        1. 缓存检查与面信息准备
        2. 提取NCTI中抽取的step数据的边、面关系
        3. 构建唯一边对，筛选最长边
        4. 构建新旧边ID映射
        5. 添加有向边到图结构
        6. 排序和存储边信息
        """
        # 1. 缓存检查与面信息准备
        cache_key = self.name
        if cache_key in self._graph_cache:
            return self._graph_cache[cache_key]

        if len(self.face_ids) == 0:
            self.get_face_info()

        face_ids = self.face_ids
        num_faces = len(face_ids)

        # 2. 提取AI模型的边、面关系
        ai = self.NCTI.AiModel(self.doc, self.name)
        edge_ids_list = ai.EdgeID
        face_eids_list = ai.FaceEID
        face_fids_list = ai.FaceFID
        edge_attrs_list = ai.EdgeAttr

        face_id_to_idx = {face_id: idx for idx, face_id in enumerate(face_ids)}
        nx_graph = nx.DiGraph()
        nx_graph.add_nodes_from(range(num_faces))

        # 3. 构建唯一边对，筛选最长边（同一对面只保留最长的边）
        # 遍历所有边，按面对（feid, ffid）分组，只保留每对面之间长度最长的那条边。
        # 这样可以避免同一对面之间有多条边时重复统计，保证图结构简洁。
        unique_edge_pairs = {}
        for i, (original_eid, feid, ffid) in enumerate(zip(edge_ids_list, face_eids_list, face_fids_list)):
            if feid not in face_id_to_idx or ffid not in face_id_to_idx:
                continue

            length = 0.0
            if edge_attrs_list and i < len(edge_attrs_list):
                edge_attr = edge_attrs_list[i]
                if len(edge_attr) > 3:
                    length = edge_attr[3]

            min_face_id = min(feid, ffid)
            max_face_id = max(feid, ffid)
            edge_pair_key = (min_face_id, max_face_id)

            if edge_pair_key not in unique_edge_pairs:
                unique_edge_pairs[edge_pair_key] = (feid, ffid, length, original_eid, i)
            else:
                current_length = unique_edge_pairs[edge_pair_key][2]
                if length > current_length:
                    unique_edge_pairs[edge_pair_key] = (feid, ffid, length, original_eid, i)

        # 4. 构建新旧边ID映射（每对面分配两个新边ID，分别表示两个方向）
        # 对每一对面，分配两个新边ID（even/odd），分别表示两个方向（A->B和B->A）。
        # edge_id_mapping用于查询任意方向的边对应的新ID。
        # new_edge_id_to_original_idx用于新边ID查找原始边属性索引。
        face_pair_to_original_idx = {}
        for edge_pair_key, (feid, ffid, length, original_eid, original_idx) in unique_edge_pairs.items():
            face_pair_to_original_idx[(feid, ffid)] = original_idx
            face_pair_to_original_idx[(ffid, feid)] = original_idx

        new_edge_id_even = 0
        new_edge_id_to_original_idx = {}
        edge_id_mapping = {}

        for edge_pair_key, (feid, ffid, length, original_eid, original_idx) in unique_edge_pairs.items():
            even_id = new_edge_id_even
            odd_id = new_edge_id_even + 1

            if feid < ffid:
                edge_id_mapping[(feid, ffid)] = even_id
                edge_id_mapping[(ffid, feid)] = odd_id
                new_edge_id_to_original_idx[even_id] = face_pair_to_original_idx.get((feid, ffid), original_idx)
                new_edge_id_to_original_idx[odd_id] = face_pair_to_original_idx.get((ffid, feid), original_idx)
            else:
                edge_id_mapping[(feid, ffid)] = odd_id
                edge_id_mapping[(ffid, feid)] = even_id
                new_edge_id_to_original_idx[odd_id] = face_pair_to_original_idx.get((feid, ffid), original_idx)
                new_edge_id_to_original_idx[even_id] = face_pair_to_original_idx.get((ffid, feid), original_idx)

            new_edge_id_even += 2

        # 5. 添加有向边到图结构（每对面双向添加，包含新边ID、长度、原始边ID）
        ordered_edges = []
        for edge_pair_key, (feid, ffid, length, original_eid, original_idx) in unique_edge_pairs.items():
            try:
                u = face_id_to_idx[feid]
                v = face_id_to_idx[ffid]
                new_edge_id_uv = edge_id_mapping[(feid, ffid)]
                new_edge_id_vu = edge_id_mapping[(ffid, feid)]

                if feid < ffid:
                    ordered_edges.append((new_edge_id_uv, u, v, length, original_eid))
                    ordered_edges.append((new_edge_id_vu, v, u, length, original_eid))
                else:
                    ordered_edges.append((new_edge_id_vu, v, u, length, original_eid))
                    ordered_edges.append((new_edge_id_uv, u, v, length, original_eid))

                nx_graph.add_edge(u, v, edge_idx=new_edge_id_uv, length=length, original_eid=original_eid)
                nx_graph.add_edge(v, u, edge_idx=new_edge_id_vu, length=length, original_eid=original_eid)
            except Exception:
                continue

        # 6. 排序和存储边信息（便于后续特征提取）
        ordered_edges.sort(key=lambda x: x[0])
        # 边属性存储说明：
        # edge_id_mapping：{(feid, ffid): new_edge_id}，用于根据面对查找新分配的边ID（方向敏感）。
        nx_graph.graph['edge_id_mapping'] = edge_id_mapping
        # new_edge_id_to_original_idx：{new_edge_id: original_idx}，用于新边ID查找原始边属性索引（如长度、类型等）。
        nx_graph.graph['new_edge_id_to_original_idx'] = new_edge_id_to_original_idx
        # ordered_edges：[(new_edge_id, u, v, length, original_eid), ...]，按新边ID排序的边列表，便于后续特征提取和遍历。
        nx_graph.graph['ordered_edges'] = ordered_edges

        # 返回：
        #   nx_graph: NetworkX有向图对象，包含所有面和边的关系及属性
        #   num_faces: 面的数量
        #   face_ids: 面ID列表
        result = (nx_graph, num_faces, face_ids)
        self._graph_cache[cache_key] = result
        return result

    def cal_spatial_pos(self):
        """
        计算所有面之间的空间位置（最短路径长度），用于图结构空间特征。
        """
        
        path_lengths = nx.floyd_warshall_numpy(self.nx_graph, weight=None)
        path_lengths = path_lengths.astype(int)
        path_lengths = np.clip(path_lengths, 0, 62)
        return path_lengths

    def cal_edge_path(self):
        """
        计算所有面之间的边路径矩阵（优化版）。
        返回：
            edge_path: (num_faces, num_faces, max_distance) 的 int32 数组，路径边ID序列，不足部分填 -1。
            path_lengths: (num_faces, num_faces) 的 int32 数组，最短路径长度（步数），不可达为 -1。
        """
        n = self.num_faces
        graph = self.nx_graph

        # 距离矩阵和前驱矩阵
        # dist[s, t] = 最短路径长度，-1 表示不可达
        # pred[s, t] = 从 s 到 t 的最短路径上 t 的前驱节点，-1 表示无前驱（即 s 本身或不可达）
        dist = -np.ones((n, n), dtype=int)
        pred = -np.ones((n, n), dtype=int)
        max_dist = 0

        # 对每个源点 s 执行 BFS
        for s in range(n):
            visited = [False] * n
            d = [-1] * n
            p = [-1] * n
            q = deque()
            visited[s] = True
            d[s] = 0
            q.append(s)

            while q:
                u = q.popleft()
                for v in graph.neighbors(u):
                    if not visited[v]:
                        visited[v] = True
                        d[v] = d[u] + 1
                        p[v] = u
                        q.append(v)
            # 将结果存入全局矩阵
            for t in range(n):
                dist[s, t] = d[t]
                pred[s, t] = p[t]
                if d[t] > max_dist:
                    max_dist = d[t]
        # 根据前驱矩阵重建每条路径，填充 edge_path
        edge_path = -np.ones((n, n, max_dist), dtype=int)
        for s in range(n):
            for t in range(n):
                if s == t or dist[s, t] == -1:
                    continue
                # 从 t 回溯到 s 得到反向路径节点列表
                path_nodes = []
                cur = t
                while cur != -1:
                    path_nodes.append(cur)
                    cur = pred[s, cur]
                path_nodes.reverse()  # 变为从 s 到 t
                # 将路径上的边索引填入 edge_path
                for step, (u, v) in enumerate(zip(path_nodes[:-1], path_nodes[1:])):
                    # 获取边索引（假设图是无向的，或 u->v 和 v->u 都有相同的 edge_idx）
                    edge_idx = graph[u][v]['edge_idx']
                    edge_path[s, t, step] = edge_idx
        path_lengths = dist  # 距离矩阵直接作为 path_lengths
        return edge_path, path_lengths
    
    def cal_d2_distance(self):
        """
        计算所有面之间的d2距离分布（采样点对之间的归一化距离直方图）。
        使用向量化操作和固定随机种子，保证结果确定且高效。
        """
        if len(self.face_ids) == 0:
            self.get_face_info()
        n = len(self.face_ids)                # 面数量            # 直方图桶数
        # 将采样点列表转换为形状 (n, self.sample_num, 3) 的数组
        points = np.array(self.face_samples, dtype=float)
        # 固定随机种子，为每个面生成独立的采样点重排索引（保证可重复性）
        rng = np.random.RandomState(42)
        perms = np.array([rng.permutation(self.sample_num) for _ in range(n)])  # (n, self.sample_num)
        # 按每个面自己的重排索引重新排列采样点，得到新的点集 B
        # B[j, k, :] = points[j, perms[j, k], :]
        points_shuffled = np.take_along_axis(points, perms[:, :, np.newaxis], axis=1)
        # 初始化直方图数组 (n, n, self.dstb_cap)
        histograms = np.zeros((n, n, self.dstb_cap), dtype=float)
        # 分块处理以控制内存，batch_size 可根据实际内存调整
        batch_size = 64
        for i_start in range(0, n, batch_size):
            i_end = min(i_start + batch_size, n)
            batch_cur = i_end - i_start
            # 当前 batch 的第一个面点集 A_i，形状 (batch,self.sample_num , 3)
            points_i = points[i_start:i_end]
            # 计算当前 batch 与所有 j 的配对距离
            # 广播计算差值: (batch, n, self.sample_num , 3)
            diff = points_i[:, np.newaxis, :, :] - points_shuffled[np.newaxis, :, :, :]
            dist = np.sqrt(np.sum(diff ** 2, axis=-1))          # (batch, n, self.sample_num )
            # 归一化距离并计算直方图索引
            dist_norm = dist / self.max_distance
            indices = np.floor(dist_norm * self.dstb_cap).astype(int)
            np.clip(indices, 0, self.dstb_cap - 1, out=indices)      # 防止边界溢出
            # 生成局部组合索引，用于批量统计直方图
            batch_local = np.arange(batch_cur).reshape(-1, 1, 1)   # (batch, 1, 1)
            j_global = np.arange(n).reshape(1, -1, 1)              # (1, n, 1)
            combined = (batch_local * n + j_global) * self.dstb_cap + indices  # (batch, n, self.sample_num)
            combined_flat = combined.ravel()
            # 统计局部直方图 (batch_cur, n, dstb_cap)
            local_counts = np.bincount(combined_flat,
                                    minlength=batch_cur * n * self.dstb_cap)
            local_hist = local_counts.reshape(batch_cur, n, self.dstb_cap)
            # 累加到全局结果
            histograms[i_start:i_end] += local_hist
        # 归一化：将计数转换为频率
        histograms /= self.sample_num 
        self.d2_distance = histograms
        return self.d2_distance.astype(float)
    def compute_angle_batch(self,p1, p2, p3):
        """
        批量计算以 p3 为顶点的夹角（归一化到 [0,1]）。
        
        参数:
            p1, p2, p3: 形状均为 (batch_size, S, 3) 的数组，
                        表示 batch_size 组点集，每组有 S 个三维点。
        
        返回:
            angles_norm: 形状 (batch_size, S) 的数组，值为归一化角度。
        """
        # 计算从 p3 指向 p1 和 p2 的向量
        v1 = p1 - p3
        v2 = p2 - p3
        # 计算点积和模长
        dot = np.sum(v1 * v2, axis=-1)                # (batch_size, S)
        norm1 = np.linalg.norm(v1, axis=-1)           # (batch_size, S)
        norm2 = np.linalg.norm(v2, axis=-1)           # (batch_size, S)

        # 防止除以零
        denom = norm1 * norm2 + 1e-12
        cos_theta = dot / denom
        cos_theta = np.clip(cos_theta, -1.0, 1.0)     # 数值稳定
        # 计算角度并归一化
        angle_rad = np.arccos(cos_theta)               # (batch_size, S)
        angles_norm = angle_rad / np.pi                 # 归一化到 [0,1]
        return angles_norm


    def cal_a3_distance(self):
        """
        计算所有面之间的a3距离分布（采样点对与角点形成的夹角分布直方图）。
        使用向量化操作和固定随机种子，保证结果确定且高效。
        """
        if len(self.face_ids) == 0:
            self.get_face_info()
        n = len(self.face_ids)               # 面数量
        S_angle = len(self.angle_samples[0])  # 每个面的角点数（256）
        # 转换为numpy数组
        points_face = np.array(self.face_samples, dtype=float)   # (n, self.sample_num, 3)
        points_angle = np.array(self.angle_samples, dtype=float) # (n, S_angle, 3)
        # 固定随机种子，保证可重复性
        rng = np.random.RandomState(42)
        # 初始化结果数组 (n, n, self.dstb_cap)
        self.a3_distance = np.zeros((n, n, self.dstb_cap), dtype=float)
        # 遍历每个 i
        for i in range(n):
            # 当前面的采样点 p1：形状 (self.sample_num, 3)
            p1 = points_face[i]
            # 生成所有 j 对应的随机排列（用于选取 p2 和 p3）
            # 为每个 j 生成一个独立的排列，形状 (n, self.sample_num)
            rand_face = rng.random((n, self.sample_num))
            perms_face = np.argsort(rand_face, axis=1)   # (n, self.sample_num)
            rand_vertex = rng.random((n, self.sample_num))
            perms_vertex = np.argsort(rand_vertex, axis=1)   # (n, self.sample_num)
            # 构建当前 i 下所有 j 的顶点集合 vertexes_i_j：形状 (n, 2*S_angle, 3)
            # 将 points_angle[i] 广播到 (n, S_angle, 3)，再与 points_angle 沿 axis=1 拼接
            p_angle_i = np.broadcast_to(points_angle[i], (n, S_angle, 3))
            vertexes_all = np.concatenate([p_angle_i, points_angle], axis=1)  # (n, 2*S_angle, 3)
            # 根据 perms_vertex 从 vertexes_all 中选取 p3 点
            # vertexes_all 形状 (n, 2*S_angle, 3)，perms_vertex 形状 (n, self.sample_num)
            p3 = np.take_along_axis(vertexes_all, perms_vertex[:, :, np.newaxis], axis=1)  # (n, self.sample_num, 3)
            # 根据 perms_face 从 points_face 中选取 p2 点
            # points_face 形状 (n, S_face, 3)，perms_face 形状 (n, S_face)
            p2 = np.take_along_axis(points_face, perms_face[:, :, np.newaxis], axis=1)     # (n, self.sample_num, 3)
            # 将 p1 广播到与 p2、p3 相同的形状 (n, S_face, 3)
            p1_broadcast = np.broadcast_to(p1, (n, self.sample_num, 3))
            # 批量计算角度
            angles_norm = self.compute_angle_batch(p1_broadcast, p2, p3)   # (n, self.sample_num)
            # 映射到直方图桶索引
            indices = np.floor(angles_norm * self.dstb_cap).astype(int)
            np.clip(indices, 0, self.dstb_cap - 1, out=indices)   # 防止边界溢出
            # 统计直方图：为每个 j 生成计数
            j_indices = np.arange(n).reshape(-1, 1)           # (n, 1)
            combined = j_indices * self.dstb_cap + indices          # (n, self.sample_num)
            combined_flat = combined.ravel()
            counts = np.bincount(combined_flat, minlength=n * self.dstb_cap)
            hist = counts.reshape(n, self.dstb_cap)
            # 归一化并存入结果
            self.a3_distance[i] = hist / self.sample_num
        return self.a3_distance
