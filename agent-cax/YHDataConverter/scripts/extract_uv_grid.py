# - Face网格（维度：5×5×7） ：

# - 7个通道：3个归一化坐标 + 3个法向量 + 1个掩码
# - 注释掉了转置操作 ，如需转置请取消注释第71行
# - Edge网格（维度：5×7） ：

# - 每条边采5个点，每个点7维特征
# - 7个通道：3个坐标 + 3个切向量 + 1个二面角
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


class UVGridExtractor:
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
        
    def extract_face_grid(self):
        """提取面网格，每个面的网格维度为 (5, 5, 7)"""
        FacePoints = self.ai_data_info.FacePoints
        FaceNormals = self.ai_data_info.FaceNormals
        FaceMask = self.ai_data_info.FaceMask
        FaceID = self.ai_data_info.FaceID
        
        face_grid = {}
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

        for idx, (points_arr, normals, mask, face_id) in enumerate(zip(points_arrays, FaceNormals, FaceMask, FaceID)):
            normalized_points = (points_arr - mean_arr) / std_arr
            normals_arr = np.array(normals).reshape((5, 5, 3))
            mask_arr = np.array(mask).reshape((5, 5, 1))
            single_grid = np.concatenate([normalized_points, normals_arr, mask_arr], axis=2)
            # single_grid = np.transpose(single_grid, (2, 0, 1))  # 如需转置取消注释
            face_grid[face_id] = single_grid.tolist()
        
        return face_grid
    
    def extract_edge_grid(self):
        """提取边网格，每条边的网格维度为 (5, 7)"""
        FaceFID = self.ai_data_info.FaceFID
        FaceEID = self.ai_data_info.FaceEID
        EdgePoints = self.ai_data_info.EdgePoints
        EdgeTangents = self.ai_data_info.EdgeTangents
        
        edge_grid = {}
        
        if len(EdgePoints) == 0:
            return edge_grid
        
        n = len(EdgePoints)
        m = len(EdgePoints[0]) // 3
        
        points_arr = np.array(EdgePoints, dtype=float).reshape(n, m, 3)
        tangents_arr = np.array(EdgeTangents, dtype=float).reshape(n, m, 3)
        
        dihedral_angles = []
        try:
            if hasattr(self.ai_data_info, 'leftNormal') and hasattr(self.ai_data_info, 'rightNormal'):
                left = np.array(self.ai_data_info.leftNormal, dtype=float)
                right = np.array(self.ai_data_info.rightNormal, dtype=float)
                dots = np.sum(left * right, axis=1)
                norms_left = np.linalg.norm(left, axis=1)
                norms_right = np.linalg.norm(right, axis=1)
                with np.errstate(divide='ignore', invalid='ignore'):
                    cos_theta = dots / (norms_left * norms_right)
                    cos_theta = np.clip(cos_theta, -1.0, 1.0)
                angles = np.arccos(cos_theta)
                invalid_mask = (norms_left == 0) | (norms_right == 0)
                angles[invalid_mask] = 0.0
                angles = np.nan_to_num(angles, nan=0.0)
                dihedral_angles = angles.tolist()
        except Exception:
            dihedral_angles = [0.0] * len(EdgePoints)
        
        dihedral_angles = np.array(dihedral_angles, dtype=float)
        dihedral_expanded = dihedral_angles[:, np.newaxis, np.newaxis]
        dihedral_expanded = np.repeat(dihedral_expanded, m, axis=1)
        
        combined = np.concatenate([points_arr, tangents_arr, dihedral_expanded], axis=2)
        
        for idx, (fid, eid) in enumerate(zip(FaceFID, FaceEID)):
            key = f"{int(fid)}_{int(eid)}"
            if idx < len(combined):
                edge_grid[key] = combined[idx].tolist()
            else:
                edge_grid[key] = []
        
        return edge_grid
    
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
    parser = argparse.ArgumentParser(description='提取UV网格数据')
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
    extractor = UVGridExtractor(NCTI, args.step_path)
    
    try:
        extractor.import_step()
        
        print("提取face网格...")
        face_grid = extractor.extract_face_grid()
        
        print("提取edge网格...")
        edge_grid = extractor.extract_edge_grid()
        
        result = {
            'face': face_grid,
            'edge': edge_grid
        }
        
        if args.output:
            output_path = args.output
            if not output_path.endswith('.json'):
                output_path += '.json'
        else:
            output_path = os.path.splitext(args.step_path)[0] + '_uv_grid.json'
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
        
        print(f"UV网格数据已保存到: {output_path}")
        
    finally:
        extractor.cleanup()


if __name__ == "__main__":
    main()