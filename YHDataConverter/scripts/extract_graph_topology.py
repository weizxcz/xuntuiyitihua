import os
import sys
import json
import argparse
import numpy as np

# 在 Windows 上设置 PATH 环境变量
if os.name == 'nt':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, 'configs', 'configs.yaml')
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        dllpath = config['ncti_path_config']['dllpath']
        os.environ['PATH'] = dllpath + os.pathsep + os.environ.get('PATH', '')
        os.add_dll_directory(dllpath)
    except Exception as e:
        print(f"设置 PATH 环境变量时出错: {e}")

from src.utils.base_functions import load_config_basic, init_ncti


def build_adjacency_matrix_sparse(face_f_id, face_e_id, num_nodes=None):
    """
    使用稀疏方式构建邻接矩阵（适用于大规模图）
    
    参数:
        face_f_id: list/array，每条边的起始面索引列表
        face_e_id: list/array，每条边的终点面索引列表
        num_nodes: int，可选，节点总数
    
    返回:
        adj: numpy.ndarray，对称的邻接矩阵
    """
    face_f_id = np.array(face_f_id, dtype=np.int32)
    face_e_id = np.array(face_e_id, dtype=np.int32)
    
    if num_nodes is None:
        num_nodes = max(face_f_id.max(), face_e_id.max()) + 1
    
    rows = np.concatenate([face_f_id, face_e_id])
    cols = np.concatenate([face_e_id, face_f_id])
    data = np.ones(len(rows), dtype=np.int32)
    
    adj = np.zeros((num_nodes, num_nodes), dtype=np.int32)
    np.add.at(adj, (rows, cols), data)
    
    adj = (adj > 0).astype(np.int32)
    
    return adj


class GraphTopologyExtractor:
    def __init__(self, NCTI, step_path):
        self.NCTI = NCTI
        self.step_path = step_path
        self.doc = None
        self.ai_data_info = None
        
    def import_step(self):
        self.doc = self.NCTI.Document()
        self.doc.New("OCC", "DCM", 0)
        self.doc.RunCommand("cmd_ncti_import_file", str(self.step_path), "testbox")
        self.ai_data_info = self.NCTI.AiModel(self.doc, "testbox")
        
    def get_graph(self):
        """获取graph结构（与AAGGraphExtraToolNcti一致）"""
        FaceFID = self.ai_data_info.FaceFID
        FaceEID = self.ai_data_info.FaceEID
        FaceID = self.ai_data_info.FaceID
        graph = {'edges': (FaceFID, FaceEID), 'num_nodes': len(FaceID)}
        return graph
    
    def get_graph_edge_attr(self):
        """获取边属性"""
        original_graph_edge_attr = self.ai_data_info.EdgeAttr
        graph_edge_attr = [sublist[:10] for sublist in original_graph_edge_attr]
        return graph_edge_attr
    
    def get_graph_face_attr(self):
        """获取面属性"""
        FaceID = self.ai_data_info.FaceID
        graph_face_attr = self.ai_data_info.FaceAttr
        face_attr_dict = {x: y for x, y in zip(FaceID, graph_face_attr)}
        face_attr_sort_dict = dict(sorted(face_attr_dict.items(), key=lambda x: x[0]))
        return list(face_attr_sort_dict.values())
    
    def get_graph_face_grid(self):
        """获取面网格"""
        FacePoints = self.ai_data_info.FacePoints
        FaceNormals = self.ai_data_info.FaceNormals
        FaceMask = self.ai_data_info.FaceMask
        FaceID = self.ai_data_info.FaceID
        
        graph_face_grid = []
        points_arrays = [np.array(points).reshape((5, 5, 3)) for points in FacePoints]
        
        if len(points_arrays) > 0:
            stacked_points = np.stack(points_arrays, axis=0)
            mean_arr = np.mean(stacked_points, axis=(0, 1, 2), keepdims=True)
            std_arr = np.std(stacked_points, axis=(0, 1, 2), keepdims=True)
            mean_arr = mean_arr.reshape((1, 1, 3))
            std_arr = std_arr.reshape((1, 1, 3))
            std_arr = np.where(std_arr < 0.0001, 1.0, std_arr)
        else:
            mean_arr = np.zeros((1, 1, 3), dtype=float)
            std_arr = np.ones((1, 1, 3), dtype=float)

        for points_arr, normals, mask in zip(points_arrays, FaceNormals, FaceMask):
            normalized_points = (points_arr - mean_arr) / std_arr
            normals_arr = np.array(normals).reshape((5, 5, 3))
            mask_arr = np.array(mask).reshape((5, 5, 1))
            single_grid = np.concatenate([normalized_points, normals_arr, mask_arr], axis=2)
            single_grid = np.transpose(single_grid, (2, 0, 1))
            graph_face_grid.append(single_grid.tolist())
        
        face_grid_dict = {x: y for x, y in zip(FaceID, graph_face_grid)}
        face_grid_sort_dict = dict(sorted(face_grid_dict.items(), key=lambda x: x[0]))
        return list(face_grid_sort_dict.values())
    
    def build_adjacency(self):
        """构建邻接矩阵"""
        FaceFID = self.ai_data_info.FaceFID
        FaceEID = self.ai_data_info.FaceEID
        FaceID = self.ai_data_info.FaceID
        
        face_id_to_idx = {face_id: idx for idx, face_id in enumerate(FaceID)}
        
        face_f_idx = [face_id_to_idx.get(fid, 0) for fid in FaceFID]
        face_e_idx = [face_id_to_idx.get(eid, 0) for eid in FaceEID]
        
        num_nodes = len(FaceID)
        adj = build_adjacency_matrix_sparse(face_f_idx, face_e_idx, num_nodes)
        
        return adj.tolist()
    
    def cleanup(self):
        if self.doc:
            self.doc.Delete()


def validate_step_file(step_path):
    """验证step文件路径是否有效"""
    if not step_path:
        print("错误：step_path参数不能为空")
        return False
    
    if not os.path.exists(step_path):
        print(f"错误：step文件不存在: {step_path}")
        return False
    
    if os.path.isdir(step_path):
        print(f"错误：step_path是目录，需要提供具体的step文件路径: {step_path}")
        return False
    
    ext = os.path.splitext(step_path)[1].lower()
    if ext not in ('.step', '.stp'):
        print(f"警告：文件扩展名不是.step或.stp，当前扩展名: {ext}")
    
    return True


def main():
    parser = argparse.ArgumentParser(description='提取Graph拓扑结构（与step2graph_ncti.py格式一致）')
    parser.add_argument('--step_path', type=str, required=True, help='step文件路径（必需参数）')
    parser.add_argument('--output', type=str, default=None, help='输出JSON文件路径')
    args = parser.parse_args()
    
    if not validate_step_file(args.step_path):
        return
    
    print("初始化NCTI...")
    NCTI = init_ncti()
    if NCTI is None:
        print("NCTI初始化失败")
        return
    
    print(f"处理step文件: {args.step_path}")
    extractor = GraphTopologyExtractor(NCTI, args.step_path)
    
    try:
        extractor.import_step()
        
        print("提取graph结构...")
        graph = extractor.get_graph()
        
        print("提取graph_edge_attr...")
        graph_edge_attr = extractor.get_graph_edge_attr()
        
        print("提取graph_face_attr...")
        graph_face_attr = extractor.get_graph_face_attr()
        
        print("提取graph_face_grid...")
        graph_face_grid = extractor.get_graph_face_grid()
        
        print("构建邻接矩阵...")
        adj_matrix = extractor.build_adjacency()
        
        result = {
            'graph': graph,
            'graph_face_attr': graph_face_attr,
            'graph_face_grid': graph_face_grid,
            'graph_edge_attr': graph_edge_attr,
            'graph_edge_grid': [],
            'adjacency matrix': adj_matrix
        }
        
        if args.output:
            output_path = args.output
            if not output_path.endswith('.json'):
                output_path += '.json'
        else:
            output_path = os.path.splitext(args.step_path)[0] + '_graph.json'
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
        
        print(f"Graph拓扑数据已保存到: {output_path}")
        
    finally:
        extractor.cleanup()


if __name__ == "__main__":
    main()