import numpy as np
import os
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
import dgl
import torch
from .models.inst_segmentors import AAGNetSegmentor
import json

class AAGNetInference():
    def __init__(self, weight_path:str="weight.pth", stat_path:str="attr_stat.json"):
        self.inst_thres = 0.5
        self.bottom_thres = 0.5
        # inference parameters
        self.eps = 1e-6  # small number

        self.weight_path = weight_path
        print(f"加载的模型为:{self.weight_path}")
        print(f"加载的统计数据为：{stat_path}")
        self.model_type = 'full'  # ''tiny' or 'full'
        self.device = 'cpu'
        self.init_recognizer()
        self.stat = self.load_statistics(stat_path)

    def load_json_or_pkl(self,pathname):
        # try to load dataset from pickel first
        pkl_path = str(pathname).split('.')[0] + '.pkl'
        if os.path.exists(pkl_path):
            return torch.load(pkl_path)
        else:  # if no pkl exists, load from json
            with open(pathname, "r") as fp:
                return json.load(fp)

    def load_statistics(self,stat_path):
        stat = self.load_json_or_pkl(stat_path)
        mean_face_attr = np.array(stat['mean_face_attr'])
        std_face_attr = np.array(stat['std_face_attr'])
        mean_edge_attr = np.array(stat['mean_edge_attr'])
        std_edge_attr = np.array(stat['std_edge_attr'])
        stat['mean_face_attr'] = torch.from_numpy(mean_face_attr)
        stat['std_face_attr'] = torch.from_numpy(std_face_attr)
        stat['mean_edge_attr'] = torch.from_numpy(mean_edge_attr)
        stat['std_edge_attr'] = torch.from_numpy(std_edge_attr)
        # if the std is 0, we set the std to 1
        eps = 1e-8
        stat['std_face_attr'][stat['std_face_attr'] < eps] = 1.
        stat['std_edge_attr'][stat['std_edge_attr'] < eps] = 1.
        return stat

    def standardization(self,data, stat):
        data.ndata["x"] -= stat['mean_face_attr']
        data.ndata["x"] /= stat['std_face_attr']
        data.edata["x"] -= stat['mean_edge_attr']
        data.edata["x"] /= stat['std_edge_attr']
        return data

    def load_one_graph(self, data):
        # Create the graph using the edges and number of nodes
        edges = tuple(data['graph']['edges'])
        num_nodes = data['graph']['num_nodes']
        dgl_graph = dgl.graph(edges, num_nodes=num_nodes)

        # Convert node attributes to PyTorch tensors and add them to the graph
        node_attributes = data['graph_face_attr']
        node_attributes = np.array(node_attributes)
        node_attributes = torch.from_numpy(node_attributes).type(torch.float32)
        dgl_graph.ndata["x"] = node_attributes

        # Convert and add node grid attributes if they are present
        node_grid_attributes = data['graph_face_grid']
        if len(node_grid_attributes) > 0:
            node_grid_attributes = np.array(node_grid_attributes)
            node_grid_attributes = torch.from_numpy(node_grid_attributes).type(torch.float32)
            dgl_graph.ndata["grid"] = node_grid_attributes

        # Convert edge attributes to PyTorch tensors and add them to the graph
        edge_attributes = data['graph_edge_attr']
        edge_attributes = np.array(edge_attributes)
        edge_attributes = torch.from_numpy(edge_attributes).type(torch.float32)
        dgl_graph.edata["x"] = edge_attributes

        # Convert and add edge grid attributes if they are present
        edge_grid_attributes = data['graph_edge_grid']
        if len(edge_grid_attributes) > 0:
            edge_grid_attributes = np.array(edge_grid_attributes)
            edge_grid_attributes = torch.from_numpy(edge_grid_attributes).type(torch.float32)
            dgl_graph.edata["grid"] = edge_grid_attributes
        return dgl_graph


    def extract_face_point_grid(self, FacePoints, FaceNormals, FaceMask):
        graph_face_grid = []
        for points, normals, mask in zip(FacePoints, FaceNormals, FaceMask):
            points_arr = np.array(points).reshape((5, 5, 3))
            normals_arr = np.array(normals).reshape((5, 5, 3))
            mask_arr = np.array(mask).reshape((5, 5, 1))
            single_grid = np.concatenate([points_arr, normals_arr, mask_arr], axis=2)
            single_grid = np.transpose(single_grid, (2, 0, 1))
            graph_face_grid.append(single_grid.tolist())
        return graph_face_grid

    def resort_face(self,faceid,face_attr):
        face_attr_dict = {x: y for x, y in zip(faceid, face_attr)}
        face_attr_sort_dict = dict(sorted(face_attr_dict.items(), key=lambda x: x[0]))
        graph_face_attr = list(face_attr_sort_dict.values())
        return graph_face_attr

    def get_aag_data(self, face_id,face_fid,face_eid,face_points,face_normals,face_mask,graph_edge_attr,graph_face_attr):
        graph = {'edges': (face_fid, face_eid), 'num_nodes': len(face_id)}
        graph_face_grid = self.extract_face_point_grid(face_points, face_normals, face_mask)
        graph_face_attr = self.resort_face(face_id, graph_face_attr)
        graph_face_grid = self.resort_face(face_id, graph_face_grid)
        agg_data = {
            'graph': graph,
            'graph_face_attr': graph_face_attr,
            'graph_face_grid': graph_face_grid,
            'graph_edge_attr': graph_edge_attr,
            'graph_edge_grid':[]
        }
        return agg_data

    def init_recognizer(self):
        # 先加载权重文件，获取节点和边的属性维度
        model_param = torch.load(self.weight_path, map_location='cpu')
        
        # 从权重文件中获取 node_attr_dim 和 edge_attr_dim
        self.node_attr_dim = model_param['node_attr_encoder.0.weight'].shape[1]
        self.edge_attr_dim = model_param['edge_attr_encoder.0.weight'].shape[1]
        
        print(f"从权重文件中获取的 node_attr_dim: {self.node_attr_dim}")
        print(f"从权重文件中获取的 edge_attr_dim: {self.edge_attr_dim}")
        
        # 使用获取的维度初始化模型
        self.recognizer = AAGNetSegmentor(arch='AAGNetGraphEncoder',
                                           num_classes=2,
                                           edge_attr_dim=self.edge_attr_dim, node_attr_dim=self.node_attr_dim,
                                           edge_attr_emb=64, node_attr_emb=64,
                                           edge_grid_dim=0, node_grid_dim=7,
                                           edge_grid_emb=0, node_grid_emb=64,
                                           num_layers=4, delta=2, mlp_ratio=4,
                                           drop=0., drop_path=0.,
                                           head_hidden_dim=256,
                                           conv_on_edge=False)
        
        self.recognizer.load_state_dict(model_param)
        self.recognizer = self.recognizer.to(self.device)
        self.recognizer.eval()

    def ai_model_inference(self, face_id,face_fid,face_eid,face_points,face_normals,face_mask,graph_edge_attr,graph_face_attr):
        agg_data = self.get_aag_data(face_id, face_fid, face_eid, face_points, face_normals, face_mask, graph_edge_attr,
                                     graph_face_attr)
        sample = self.load_one_graph(agg_data)
        one_graph = self.standardization(sample, self.stat)
        one_graph = one_graph.to(self.device)
        # dgl.save_graphs("graph_data.dgl", one_graph)
        with torch.no_grad():
            seg_out, inst_out, bottom_out = self.recognizer(one_graph)
        return seg_out,inst_out,bottom_out

    def postprocess(self, seg_out, inst_out, bottom_out):
        seg_out = seg_out.sigmoid()
        seg_out = seg_out > 0.5
        face_logits = seg_out.cpu().numpy()

        inst_out = inst_out[0]  # inst_out is a list
        inst_out = inst_out.sigmoid()
        adj = inst_out > self.inst_thres
        adj = adj.cpu().numpy().astype('int32')

        # Identify individual proposals of each feature
        proposals = set()  # use to delete repeat proposals
        # record whether the face belongs to a instance
        used_flags = np.zeros(adj.shape[0], dtype=np.bool8)
        for row_idx, row in enumerate(adj):
            if used_flags[row_idx]:
                # the face has been assigned to a instance
                continue
            if np.sum(row) <= self.eps:
                # stock face, no linked face, so the sum of the column is 0
                continue
            # non-stock face
            proposal = set()  # use to delete repeat faces
            for col_idx, item in enumerate(row):
                if used_flags[col_idx]:
                    # the face has been assigned to a proposal
                    continue
                if item:  # have connections with currect face
                    proposal.add(col_idx)
                    used_flags[col_idx] = True
            if len(proposal) > 0:
                proposals.add(frozenset(proposal))  # frozenset is a hashable set
        # proposals = set()
        result_dict = {}
        for i,instance in enumerate(proposals):
            instance = list(instance)
            # sum voting for the class of the instance
            class_all = 0
            for face in instance:
                class_result = face_logits[face][0]
                if class_result == True:
                    class_all = 1
                    break
            if class_all == 0:
                continue
            result_dict[i] = {'instance': instance, 'inst_name': 'round', 'bottom_faces': []}
        return result_dict
    
    def statistic_prob(self, prob_list):
        """
        统计概率值分布并找到最佳阈值
        
        该方法结合多种策略来智能选择阈值：
        1. 直方图分析：找到概率分布的峰值和谷值
        2. Otsu 方法：最大化类间方差来找到最优阈值
        3. 梯度分析：找到概率分布中的"断层"点
        4. 频率分析：结合数值大小和出现频率综合判断
        
        参数:
            prob_list: 概率值列表，每个值表示对应面预测为 1 的概率
            
        返回:
            threshold: 自动计算的最佳阈值
        """
        if not prob_list or len(prob_list) == 0:
            return 0.5  # 默认阈值
        
        probs = np.array(prob_list)
        n = len(probs)
        
        # 过滤掉 NaN 和 Inf 值
        valid_mask = np.isfinite(probs)
        probs = probs[valid_mask]
        if len(probs) == 0:
            return 0.5
        
        # 方法 1: Otsu 方法 - 最大化类间方差
        def otsu_threshold(probs):
            """使用 Otsu 方法找到最优阈值"""
            sorted_probs = np.sort(probs)
            n_total = len(sorted_probs)
            
            # 计算累积和
            cum_sum = np.cumsum(sorted_probs)
            total_sum = cum_sum[-1]
            
            best_variance = 0
            best_threshold = 0.5
            
            # 遍历所有可能的阈值点
            for i in range(1, n_total):
                # 避免在相同值处分割
                if sorted_probs[i] == sorted_probs[i-1]:
                    continue
                
                w0 = i / n_total
                w1 = 1 - w0
                
                if w0 == 0 or w1 == 0:
                    continue
                
                mean0 = cum_sum[i-1] / i if i > 0 else 0
                mean1 = (total_sum - cum_sum[i-1]) / (n_total - i) if i < n_total else 0
                
                # 类间方差
                between_variance = w0 * w1 * (mean0 - mean1) ** 2
                
                if between_variance > best_variance:
                    best_variance = between_variance
                    best_threshold = (sorted_probs[i] + sorted_probs[i-1]) / 2
            
            return best_threshold
        
        # 方法 2: 直方图谷值检测
        def histogram_valley_threshold(probs, n_bins=100):
            """通过直方图找到分布的谷值"""
            hist, bin_edges = np.histogram(probs, bins=n_bins, range=(0, 1))
            
            # 找到直方图的峰值
            peaks = []
            for i in range(1, len(hist) - 1):
                if hist[i] > hist[i-1] and hist[i] > hist[i+1] and hist[i] > np.mean(hist):
                    peaks.append(i)
            
            if len(peaks) < 2:
                # 如果峰值不足，返回中位数
                return np.median(probs)
            
            # 在峰值之间找到谷值
            valleys = []
            for i in range(len(peaks) - 1):
                peak_start = peaks[i]
                peak_end = peaks[i + 1]
                valley_region = hist[peak_start:peak_end]
                if len(valley_region) > 0:
                    valley_idx = np.argmin(valley_region)
                    valley_pos = peak_start + valley_idx
                    valleys.append((bin_edges[valley_pos] + bin_edges[valley_pos + 1]) / 2)
            
            if valleys:
                # 选择最大的谷值（区分前景和背景）
                return max(valleys)
            
            return np.median(probs)
        
        # 方法 3: 梯度分析 - 找到概率分布的断层
        def gradient_gap_threshold(probs):
            """分析概率值的梯度变化，找到断层"""
            sorted_probs = np.sort(probs)
            
            # 计算相邻值的差值
            diffs = np.diff(sorted_probs)
            
            # 找到大的跳跃点
            # 使用相对跳跃来检测断层
            relative_diffs = np.zeros(len(diffs))
            for i in range(len(diffs)):
                if sorted_probs[i] > 1e-6:
                    relative_diffs[i] = diffs[i] / sorted_probs[i]
                else:
                    relative_diffs[i] = diffs[i]
            
            # 找到相对跳跃最大的点
            if len(relative_diffs) == 0:
                return 0.5
            
            # 使用百分位数来找到显著的跳跃
            threshold_percentile = 90  # 考虑前 10% 的大跳跃
            if len(relative_diffs) > 10:
                jump_threshold = np.percentile(relative_diffs, threshold_percentile)
                significant_jumps = np.where(relative_diffs > jump_threshold)[0]
                
                if len(significant_jumps) > 0:
                    # 选择最大的跳跃点
                    max_jump_idx = significant_jumps[np.argmax(relative_diffs[significant_jumps])]
                    return (sorted_probs[max_jump_idx] + sorted_probs[max_jump_idx + 1]) / 2
            
            return np.median(probs)
        
        # 方法 4: 双峰检测 - 找到自然分界点
        def bimodal_threshold(probs):
            """检测双峰分布并找到分界点"""
            # 将概率值分成多个区间，统计每个区间的频率
            n_bins = 50
            hist, bin_edges = np.histogram(probs, bins=n_bins, range=(0, 1))
            
            # 找到两个主要的峰值区域
            # 低概率区域（背景）和高概率区域（前景）
            low_region = hist[:n_bins//3]  # 0-0.33
            mid_region = hist[n_bins//3:2*n_bins//3]  # 0.33-0.66
            high_region = hist[2*n_bins//3:]  # 0.66-1.0
            
            low_sum = np.sum(low_region)
            mid_sum = np.sum(mid_region)
            high_sum = np.sum(high_region)
            
            total = low_sum + mid_sum + high_sum
            
            # 如果存在明显的双峰分布
            if total > 0:
                low_ratio = low_sum / total
                high_ratio = high_sum / total
                
                # 如果背景和前景都有显著的比例
                if low_ratio > 0.1 and high_ratio > 0.05:
                    # 找到低概率区域和高概率区域之间的边界
                    # 使用累积分布找到 50% 分位点
                    cum_hist = np.cumsum(hist)
                    half_total = cum_hist[-1] / 2
                    threshold_idx = np.searchsorted(cum_hist, half_total)
                    return (bin_edges[threshold_idx] + bin_edges[threshold_idx + 1]) / 2
            
            return np.median(probs)
        
        # 方法 5: 基于密度的阈值选择
        def density_based_threshold(probs):
            """基于概率密度选择阈值"""
            # 使用核密度估计的思想，找到密度最低的区域
            n_bins = 100
            hist, bin_centers = np.histogram(probs, bins=n_bins, range=(0, 1))
            
            # 归一化直方图
            hist_norm = hist / (np.sum(hist) + 1e-10)
            
            # 平滑直方图
            kernel_size = 3
            smoothed_hist = np.convolve(hist_norm, np.ones(kernel_size)/kernel_size, mode='same')
            
            # 找到密度最低的区域（在两个峰值之间）
            # 从中间向两边搜索
            mid_idx = n_bins // 2
            
            # 找到左侧峰值
            left_peak_idx = 0
            left_max = 0
            for i in range(mid_idx):
                if smoothed_hist[i] > left_max:
                    left_max = smoothed_hist[i]
                    left_peak_idx = i
            
            # 找到右侧峰值
            right_peak_idx = n_bins - 1
            right_max = 0
            for i in range(mid_idx, n_bins):
                if smoothed_hist[i] > right_max:
                    right_max = smoothed_hist[i]
                    right_peak_idx = i
            
            # 在两个峰值之间找到最小值
            if left_peak_idx < right_peak_idx:
                valley_region = smoothed_hist[left_peak_idx:right_peak_idx + 1]
                if len(valley_region) > 0:
                    valley_idx = np.argmin(valley_region)
                    actual_idx = left_peak_idx + valley_idx
                    return bin_centers[actual_idx]
            
            return np.median(probs)
        
        # 综合所有方法的结果
        otsu_th = otsu_threshold(probs)
        histogram_th = histogram_valley_threshold(probs)
        gradient_th = gradient_gap_threshold(probs)
        bimodal_th = bimodal_threshold(probs)
        density_th = density_based_threshold(probs)
        
        # 收集所有阈值
        thresholds = [otsu_th, histogram_th, gradient_th, bimodal_th, density_th]
        
        # 过滤掉异常值
        valid_thresholds = [t for t in thresholds if 0 <= t <= 1]
        
        if len(valid_thresholds) == 0:
            return 0.5
        
        # 使用中位数作为最终阈值（更稳健）
        final_threshold = np.median(valid_thresholds)
        
        # 确保阈值在合理范围内
        final_threshold = np.clip(final_threshold, 0.01, 0.99)
        
        return float(final_threshold)
    
    def optimize_seg_predict_face(self, seg_predict_face, adj_true, min_faces_num=2, max_faces_num=5):
        """
        优化 seg_predict_face 的 index
        
        根据邻接矩阵和面数量阈值，对预测的面进行优化：
        - 如果某个面的邻接面数量小于 min_faces_num，则将其邻接面也加入
        - 如果某个面的邻接面数量大于 max_faces_num，则将其从结果中移除（误识别）
        
        参数:
            seg_predict_face: list，预测的面 index 列表
            adj_true: numpy.ndarray，真实的邻接矩阵
            min_faces_num: int，最小组成面数量
            max_faces_num: int，最多组成面数量
            
        返回:
            optimized_faces: list，优化后的面 index 列表
        """
        if not seg_predict_face or len(seg_predict_face) == 0:
            return []
        
        seg_predict_face = set(seg_predict_face)
        n = adj_true.shape[0]
        
        # 使用布尔数组加速查找
        face_mask = np.zeros(n, dtype=np.bool_)
        face_mask[list(seg_predict_face)] = True
        
        # 找出需要补充的面（邻接面数量小于最小值）
        to_add = set()
        for face_idx in seg_predict_face:
            # 计算该面在预测集合中的邻接面数量
            neighbors_in_pred = np.sum(adj_true[face_idx, list(seg_predict_face)])
            if neighbors_in_pred < min_faces_num:
                # 将该面的所有邻接面加入
                all_neighbors = np.where(adj_true[face_idx] > 0)[0]
                to_add.update(all_neighbors)
        
        # 合并原始集合和需要补充的面
        seg_predict_face.update(to_add)

        # 计算每个预测面在预测集合中的邻接面数量
        neighbor_counts = np.sum(adj_true[list(seg_predict_face)], axis=1)
        # 找出需要移除的面（邻接面数量超过最大值）
        to_remove = set()
        for i, count in enumerate(neighbor_counts):
            if count > max_faces_num:
                to_remove.add(list(seg_predict_face)[i])
        
        # 从集合中移除误识别的面
        seg_predict_face -= to_remove
        if not seg_predict_face:
            return []
        seg_predict_face = sorted(list(seg_predict_face))
        return np.array(seg_predict_face).tolist()
    
    def group_connected_faces(self, seg_predict_face, adj_true):
        """
        对 seg_predict_face 进行分组，将有连接关系的面放在一组
        
        使用并查集算法高效地找到连通分量
        
        参数:
            seg_predict_face: list，面 index 列表
            adj_true: numpy.ndarray，真实的邻接矩阵
            
        返回:
            groups: list of list，每个子列表包含一组连通的面 index
        """
        if not seg_predict_face or len(seg_predict_face) == 0:
            return []
        
        seg_predict_face = sorted(set(seg_predict_face))
        n = len(seg_predict_face)
        
        if n == 1:
            return [seg_predict_face]
        
        # 创建面 index 到局部索引的映射
        face_to_idx = {face: i for i, face in enumerate(seg_predict_face)}
        
        # 并查集实现
        parent = list(range(n))
        
        def find(x):
            if parent[x] != x:
                parent[x] = find(parent[x])  # 路径压缩
            return parent[x]
        
        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py
        
        # 遍历邻接矩阵，连接连通的面
        for i, face_i in enumerate(seg_predict_face):
            # 找到所有在 seg_predict_face 中的邻接面
            neighbors = np.where(adj_true[face_i] > 0)[0]
            for neighbor in neighbors:
                if neighbor in face_to_idx:
                    union(i, face_to_idx[neighbor])
        
        # 按根节点分组
        groups_dict = {}
        for i in range(n):
            root = find(i)
            if root not in groups_dict:
                groups_dict[root] = []
            groups_dict[root].append(seg_predict_face[i])
        
        return list(groups_dict.values())
    
    def postprocess_feature(self, seg_out, inst_out, bottom_out, adj_true, 
                            min_faces_num=0, max_faces_num=5, feature_name='round'):
        """
        后处理特征识别结果
        
        参数:
            seg_out: 分割输出张量
            inst_out: 实例分割输出张量
            bottom_out: 底部面输出张量
            adj_true: numpy.ndarray，真实的邻接矩阵
            min_faces_num: int，最小组成面数量
            max_faces_num: int，最多组成面数量
            feature_name: 特征名称
            
        返回:
            result_dict: 识别结果字典
        """
        seg_act_predict = seg_out[:, 1].sigmoid()
        seg_act_predict_np = seg_act_predict.cpu().numpy()
        seg_act_predict_list = seg_act_predict_np.tolist()
        threshold = self.statistic_prob(seg_act_predict_list)
        seg_predict = seg_act_predict > threshold
        seg_predict = seg_predict.cpu().numpy().astype('int32')
        seg_predict_face = np.where(seg_predict == 1)[0].tolist()
        
        # 优化 seg_predict_face
        optimized_faces = self.optimize_seg_predict_face(
            seg_predict_face, adj_true, min_faces_num, max_faces_num
        )
        # 对优化后的面进行分组
        groups = self.group_connected_faces(optimized_faces, adj_true)
        
        face_logits = seg_out.cpu().numpy()
        bottom_out = bottom_out.sigmoid()
        bottom_logits = bottom_out > self.bottom_thres
        bottom_logits = bottom_logits.cpu().numpy()
        result_dict = {
            0: {
                'instance': optimized_faces,
                'inst_name': feature_name,
                'bottom_faces': [],
                'groups': groups
            }
        }
        return result_dict
