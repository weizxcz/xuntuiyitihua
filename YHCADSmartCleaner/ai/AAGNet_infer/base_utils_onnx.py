import numpy as np
import os
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
import dgl
import json
import onnxruntime as ort

class AGGNetInferenceONNX():
    def __init__(self, weight_path:str="weight_round.onnx", stat_path:str="attr_stat.json"):
        self.inst_thres = 0.5
        self.bottom_thres = 0.5
        # inference parameters
        self.eps = 1e-6  # small number

        self.onnx_path = weight_path
        print(f"加载的模型为:{self.onnx_path}")
        print(f"加载的统计数据为：{stat_path}")
        self.model_type = 'full'  # ''tiny' or 'full'
        self.init_recognizer()
        self.stat = self.load_statistics(stat_path)

    def load_json_or_pkl(self,pathname):
        # try to load dataset from pickel first
        pkl_path = str(pathname).split('.')[0] + '.pkl'
        if os.path.exists(pkl_path):
            import torch
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
        # 保持为numpy数组，因为ONNX模型使用numpy输入
        stat['mean_face_attr'] = mean_face_attr
        stat['std_face_attr'] = std_face_attr
        stat['mean_edge_attr'] = mean_edge_attr
        stat['std_edge_attr'] = std_edge_attr
        # if the std is 0, we set the std to 1
        eps = 1e-8
        stat['std_face_attr'][stat['std_face_attr'] < eps] = 1.
        stat['std_edge_attr'][stat['std_edge_attr'] < eps] = 1.
        return stat

    def standardization(self,data, stat):
        """标准化数据"""
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
        import torch
        node_attributes = data['graph_face_attr']
        node_attributes = np.array(node_attributes, dtype=np.float32)
        dgl_graph.ndata["x"] = torch.from_numpy(node_attributes)

        # Convert and add node grid attributes if they are present
        node_grid_attributes = data['graph_face_grid']
        if len(node_grid_attributes) > 0:
            node_grid_attributes = np.array(node_grid_attributes, dtype=np.float32)
            dgl_graph.ndata["grid"] = torch.from_numpy(node_grid_attributes)

        # Convert edge attributes to PyTorch tensors and add them to the graph
        edge_attributes = data['graph_edge_attr']
        edge_attributes = np.array(edge_attributes, dtype=np.float32)
        dgl_graph.edata["x"] = torch.from_numpy(edge_attributes)

        # Convert and add edge grid attributes if they are present
        edge_grid_attributes = data['graph_edge_grid']
        if len(edge_grid_attributes) > 0:
            edge_grid_attributes = np.array(edge_grid_attributes, dtype=np.float32)
            dgl_graph.edata["grid"] = torch.from_numpy(edge_grid_attributes)
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

    def get_agg_data(self, face_id,face_fid,face_eid,face_points,face_normals,face_mask,graph_edge_attr,graph_face_attr):
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
        """初始化ONNX模型"""
        # 确保ONNX模型路径存在
        if not os.path.exists(self.onnx_path):
            raise FileNotFoundError(f"ONNX模型文件不存在: {self.onnx_path}")
        
        # 加载ONNX模型
        self.sess = ort.InferenceSession(self.onnx_path)
        print(f"成功加载ONNX模型: {self.onnx_path}")

    def prepare_onnx_input(self, dgl_graph):
        """从DGL图中提取ONNX模型所需的输入"""
        # 提取节点属性
        node_attr = dgl_graph.ndata["x"].cpu().numpy().astype(np.float32)
        
        # 提取节点网格属性
        node_grid = dgl_graph.ndata["grid"].cpu().numpy().astype(np.float32)
        
        # 提取边属性
        edge_attr = dgl_graph.edata["x"].cpu().numpy().astype(np.float32)
        
        # 准备ONNX模型输入（只提供模型实际需要的3个输入）
        onnx_input = {
            'node_attr': node_attr,
            'node_grid': node_grid,
            'edge_attr': edge_attr
        }
        
        return onnx_input

    def ai_model_inference(self, face_id,face_fid,face_eid,face_points,face_normals,face_mask,graph_edge_attr,graph_face_attr):
        """使用ONNX模型进行推理"""
        agg_data = self.get_agg_data(face_id, face_fid, face_eid, face_points, face_normals, face_mask, graph_edge_attr, graph_face_attr)
        sample = self.load_one_graph(agg_data)
        one_graph = self.standardization(sample, self.stat)
        
        # 准备ONNX模型输入
        onnx_input = self.prepare_onnx_input(one_graph)
        
        # 使用ONNX模型进行推理
        outputs = self.sess.run(None, onnx_input)
        
        # 解析输出
        seg_out = outputs[0]
        inst_out = outputs[1]
        bottom_out = outputs[2]
        
        # 转换为与原模型相同的格式
        import torch
        seg_out = torch.from_numpy(seg_out)
        inst_out = [torch.from_numpy(inst_out)]  # 原模型返回的是列表
        bottom_out = torch.from_numpy(bottom_out)
        
        return seg_out, inst_out, bottom_out

    def postprocess(self, seg_out, inst_out, bottom_out):
        """后处理，与原方法相同"""
        import torch
        seg_out = torch.sigmoid(seg_out)
        seg_out = seg_out > 0.5
        face_logits = seg_out.cpu().numpy()

        inst_out = inst_out[0]  # inst_out is a list
        inst_out = torch.sigmoid(inst_out)
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

    def postprocess_round(self, seg_out, inst_out, bottom_out):
        """后处理，与原方法相同"""
        import torch
        face_logits = seg_out.cpu().numpy()
        inst_out = inst_out[0]
        inst_out = torch.sigmoid(inst_out)
        adj = inst_out > self.inst_thres
        adj = adj.cpu().numpy().astype('int32')
        bottom_out = torch.sigmoid(bottom_out)
        bottom_logits = bottom_out > self.bottom_thres
        bottom_logits = bottom_logits.cpu().numpy()
        proposals = set()
        used_flags = np.zeros(adj.shape[0], dtype=np.bool_)
        for row_idx, row in enumerate(adj):
            if used_flags[row_idx]:
                continue
            if np.sum(row) <= self.eps:
                continue
            proposal = set()
            for col_idx, item in enumerate(row):
                if used_flags[col_idx]:
                    continue
                if item:
                    proposal.add(col_idx)
                    used_flags[col_idx] = True
            if len(proposal) > 0:
                proposals.add(frozenset(proposal))
        all_faces = []
        for instance in proposals:
            all_faces.extend(list(instance))
        all_faces = list(sorted(set(all_faces)))
        if not all_faces:
            return {}
        sum_inst_logit = 0
        for face in all_faces:
            sum_inst_logit += face_logits[face]
        inst_logit = np.argmax(sum_inst_logit)
        if inst_logit == 0:
            return {}
        bottom_faces = []
        for face_idx in all_faces:
            if bottom_logits[face_idx]:
                bottom_faces.append(face_idx)
        result_dict = {
            0: {
                'instance': all_faces,
                'inst_name': "round",
                'bottom_faces': []
            }
        }
        return result_dict
