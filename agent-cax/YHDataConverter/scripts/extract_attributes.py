import os
import sys
import json
import argparse
import pandas as pd

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


class AttributeExtractor:
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
        
    def extract_face_attr(self):
        """提取face属性，返回DataFrame格式"""
        FaceID = self.ai_data_info.FaceID
        FaceAttr = self.ai_data_info.FaceAttr
        
        face_attr_dict = {int(x): y for x, y in zip(FaceID, FaceAttr)}
        face_attr_sort_dict = dict(sorted(face_attr_dict.items(), key=lambda x: x[0]))
        
        data = []
        for faceid, attrs in face_attr_sort_dict.items():
            row = [faceid] + attrs
            data.append(row)
        
        df = pd.DataFrame(data)
        
        face_columns = [
            'faceid', 
            'plane', 
            'cylinder', 
            'cone', 
            'SphereFaceAttribute', 
            'TorusFaceAttribute', 
            'FaceAreaAttribute', 
            'RationalNurbsFaceAttribute', 
            'FaceCentroidAttribute_x', 
            'FaceCentroidAttribute_y', 
            'FaceCentroidAttribute_z', 
            'lopps', 
            'degree'
        ]
        
        if data:
            actual_cols = min(len(face_columns), len(data[0]))
            df.columns = face_columns[:actual_cols]
        else:
            df.columns = ['faceid']
        
        return df
    
    def extract_edge_attr(self):
        """提取edge属性，返回DataFrame格式"""
        FaceFID = self.ai_data_info.FaceFID
        FaceEID = self.ai_data_info.FaceEID
        EdgeAttr = self.ai_data_info.EdgeAttr
        
        data = []
        for idx, (fid, eid) in enumerate(zip(FaceFID, FaceEID)):
            edge_attr = EdgeAttr[idx][:10] if len(EdgeAttr) > idx else []
            row = [int(fid), int(eid)] + edge_attr
            data.append(row)
        
        df = pd.DataFrame(data)
        
        edge_columns = [
            'fid', 
            'eid', 
            'concave', 
            'convex', 
            'smooth', 
            'length', 
            'circular edge attr', 
            'closed edge attr', 
            'elliptical edge attr', 
            'nonrational b spline edge attr', 
            'rational b spline edge attr', 
            'straight edge attr'
        ]
        
        if data:
            actual_cols = min(len(edge_columns), len(data[0]))
            df.columns = edge_columns[:actual_cols]
        else:
            df.columns = ['fid', 'eid']
        
        return df
    
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
    parser = argparse.ArgumentParser(description='提取属性数据')
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
    extractor = AttributeExtractor(NCTI, args.step_path)
    
    try:
        extractor.import_step()
        
        print("提取face属性...")
        df_face = extractor.extract_face_attr()
        
        print("提取edge属性...")
        df_edge = extractor.extract_edge_attr()
        
        result = {
            'face': json.loads(df_face.to_json(orient='split')),
            'edge': json.loads(df_edge.to_json(orient='split'))
        }
        
        if args.output:
            output_path = args.output
            if not output_path.endswith('.json'):
                output_path += '.json'
        else:
            output_path = os.path.splitext(args.step_path)[0] + '_attributes.json'
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=4)
        
        print(f"属性数据已保存到: {output_path}")
        
        print("\nFace属性预览:")
        print(df_face.head())
        print("\nEdge属性预览:")
        print(df_edge.head())
        
    finally:
        extractor.cleanup()


if __name__ == "__main__":
    main()