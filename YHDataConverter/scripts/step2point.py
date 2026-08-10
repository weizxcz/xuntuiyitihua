import sys
import ctypes
import importlib
import os
import numpy as np
import open3d as o3d

def get_env():
    dllpath = r"D:\软件\biaozhuruanjian"
    Ncti_api_path = os.path.join(dllpath, "OCC")
    os.add_dll_directory(Ncti_api_path)
    sys.path.insert(0, dllpath)
    ctypes.CDLL(dllpath + "/ncti_command.dll")
    ctypes.CDLL(dllpath + "/ncti_occ_plugin.dll")
    ctypes.CDLL(dllpath + "/ncti_render_vulkan.dll")
    NCTI = importlib.import_module("ncti_python")
    NCTI.Init(dllpath)
    return NCTI
def load_doc(NCTI):
    doc = NCTI.Document()
    doc.New("OCC", "DCM", "GMSH")
    doc.SetImportAssemelFile(1)
    return doc

def merge_meshes(mesh_list):
    """
    合并多个TriangleMesh到一个新网格
    :param mesh_list: 包含所有待合并网格的列表
    :return: 合并后的新TriangleMesh
    """
    merged_mesh = o3d.geometry.TriangleMesh()
    # 初始化顶点、三角形列表
    all_vertices = []
    all_triangles = []
    vertex_count = 0  # 累计顶点偏移量
    for mesh in mesh_list:
        # 1. 收集顶点
        verts = np.asarray(mesh.vertices)
        all_vertices.append(verts)

        # 2. 调整三角形索引并收集
        tris = np.asarray(mesh.triangles) + vertex_count
        all_triangles.append(tris)
        # 更新顶点偏移量
        vertex_count += len(verts)
    # 合并数据
    merged_mesh.vertices = o3d.utility.Vector3dVector(np.vstack(all_vertices))
    merged_mesh.triangles = o3d.utility.Vector3iVector(np.vstack(all_triangles))
    return merged_mesh
def stp2point_ncti(step_file,NCTI):
    doc = load_doc(NCTI)
    doc.RunCommand("cmd_ncti_import_file", step_file, 2)
    group = NCTI.RootGroup(doc)
    main_root_group = group.GetCurSubGroup()
    sub_solid_list = group.GetCurSubObject(main_root_group[0])
    mesh_list = []
    for solid in sub_solid_list:
        mesh_data = doc.GetMesh(solid)
        if len(mesh_data) in (0, 2):
            continue
        points = np.array(mesh_data[0]).reshape(-1, 3)
        triangles = np.array(mesh_data[1]).reshape(-1, 3)
        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(points)
        mesh.triangles = o3d.utility.Vector3iVector(triangles)
        mesh_list.append(mesh)
    merged_mesh = merge_meshes(mesh_list)
    sampled_pcd = merged_mesh.sample_points_uniformly(number_of_points=20000)
    group_point_array = np.array(sampled_pcd.points)
    doc.Delete()
    return group_point_array



def stp2point(step_file,NCTI):
    parent_file_path,file_path = os.path.split(step_file)
    file_name = '_'.join(file_path.split('.')[:-1])
    second_parent_file_path,model_name = os.path.split(parent_file_path)
    third_parent_file_path,train_or_test = os.path.split(second_parent_file_path)
    forth_parent_file_path = os.path.dirname(third_parent_file_path)
    obj_file = os.path.join(forth_parent_file_path,'obj_data',train_or_test,model_name)
    if not os.path.exists(obj_file):
        os.makedirs(obj_file)
    txt_file = os.path.join(forth_parent_file_path,'point_cloud_data',train_or_test,model_name)
    if not os.path.exists(txt_file):
        os.makedirs(txt_file)
    coords = stp2point_ncti(step_file,NCTI)
    if file_name==model_name:
        pcd_name_file = os.path.join(txt_file,file_name+'.txt')
    else:
        if not os.path.exists(os.path.join(txt_file,'Annotations')):
            os.makedirs(os.path.join(txt_file,'Annotations'))
        pcd_name_file = os.path.join(txt_file,'Annotations',file_name+'.txt')
    np.savetxt(pcd_name_file,coords,delimiter=',')


def pcd2txt(folder_path,NCTI):
    model_data_list = os.listdir(folder_path)
    for model in model_data_list:
        model_path = os.path.join(folder_path,model)
        model_file_list = os.listdir(model_path)
        for step_file in model_file_list:
            step_file_path = os.path.join(model_path,step_file)
            stp2point(step_file_path,NCTI)

def step2pc(NCTI):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ROOT_DIR = os.path.dirname(BASE_DIR)
    train_file_path = os.path.join(ROOT_DIR, 'data', 'step_data','train')
    pcd2txt(train_file_path,NCTI)
    test_file_path = os.path.join(ROOT_DIR, 'data', 'step_data', 'test')
    pcd2txt(test_file_path,NCTI)

if __name__ == '__main__':
    NCTI = get_env()
    step2pc(NCTI)