import time

from utils.b_face_classify import is_bspline_fit_plane_by_points, is_bspline_fit_plane_by_normal, \
    is_bspline_fit_plane_by_points_and_normal
from utils.sampler import get_face_sample


def _find_planes(doc, plane_check_func, check_func_args=None):
    """
    查找平面的通用辅助函数
    
    Args:
        doc: 文档对象
        plane_check_func: 判断平面的函数
        check_func_args: 传递给判断函数的额外参数

    Returns:
        tuple: (平面面ID列表, 对应的对象名称列表)
    """
    try:
        # 获取所有对象名称
        all_names = doc.AllNames()
        if not all_names:
            print("未找到对象")
            return [], []
        
        # 获取第一个对象的所有面
        first_obj_name = all_names[0]
        face_id_list = doc.FindAllFaces(first_obj_name)
        
        if not face_id_list:
            print(f"对象 {first_obj_name} 没有找到面")
            return [], []
        
        # 过滤出平面的面ID
        filtered_cell_ids = []
        for index, face_id in enumerate(face_id_list):
            if check_func_args:
                is_plane = plane_check_func(*[arg[index] for arg in check_func_args])
            else:
                is_plane = plane_check_func(face_id, index)
            
            if is_plane:
                filtered_cell_ids.append(face_id)
        
        # 创建对应的对象名称列表
        obj_names = [first_obj_name] * len(filtered_cell_ids)
        
        return filtered_cell_ids, obj_names
        
    except Exception as e:
        print(f"查找平面时发生错误: {str(e)}")
        return [], []


def _initialize_doc(doc):
    """
    初始化文档设置
    
    Args:
        doc: 文档对象
    """
    doc.SetCreateGeGeom(1)
    doc.ResetCaseResult()


def _check_selection(sel):
    """
    检查是否有对象被选择
    
    Args:
        sel: 选择管理器
    
    Returns:
        bool: 是否有对象被选择
    """
    if len(sel.ObjectNames) == 0:
        print("请先选择对象")
        return False
    return True


def find_plane_by_points(ncti, doc):
    """
    根据点集查找平面
    
    Args:
        ncti: NCTI接口
        doc: 文档对象
    
    Returns:
        tuple: (平面面ID列表, 对应的对象名称列表)
    """
    # 初始化设置
    _initialize_doc(doc)
    
    # 检查选择
    sel = ncti.SelectionManager(doc)
    if not _check_selection(sel):
        return [], []
    
    # 获取点集
    all_names = doc.AllNames()
    first_obj_name = all_names[0]
    face_id_list = doc.FindAllFaces(first_obj_name)
    obj_names = [first_obj_name] * len(face_id_list)
    face_points, _ = get_face_sample(doc, obj_names, face_id_list)
    
    # 使用辅助函数查找平面
    return _find_planes(doc, is_bspline_fit_plane_by_points, [face_points])


def find_plane_by_normals(ncti, doc):
    """
    根据法线查找平面
    
    Args:
        ncti: NCTI接口
        doc: 文档对象
    
    Returns:
        tuple: (平面面ID列表, 对应的对象名称列表)
    """
    # 初始化设置
    _initialize_doc(doc)
    
    # 检查选择
    sel = ncti.SelectionManager(doc)
    if not _check_selection(sel):
        return [], []
    
    # 获取法线
    all_names = doc.AllNames()
    first_obj_name = all_names[0]
    face_id_list = doc.FindAllFaces(first_obj_name)
    obj_names = [first_obj_name] * len(face_id_list)
    _, face_normals = get_face_sample(doc, obj_names, face_id_list)

    # 使用辅助函数查找平面
    result = _find_planes(doc, is_bspline_fit_plane_by_normal, [face_normals])
    return result


def find_plane_by_points_and_normals(ncti, doc):
    """
    根据点集和法线查找平面
    
    Args:
        ncti: NCTI接口
        doc: 文档对象
    
    Returns:
        tuple: (平面面ID列表, 对应的对象名称列表)
    """
    # 初始化设置
    _initialize_doc(doc)
    
    # 检查选择
    sel = ncti.SelectionManager(doc)
    if not _check_selection(sel):
        return [], []
    
    # 获取点集和法线
    all_names = doc.AllNames()
    first_obj_name = all_names[0]
    face_id_list = doc.FindAllFaces(first_obj_name)
    obj_names = [first_obj_name] * len(face_id_list)
    face_points, face_normals = get_face_sample(doc, obj_names, face_id_list)
    
    # 使用辅助函数查找平面
    return _find_planes(doc, is_bspline_fit_plane_by_points_and_normal,
                        [face_points, face_normals])

def find_plane_by_ncti(ncti, doc):
    """
    使用NCTI的AI函数查找平面
    
    Args:
        ncti: NCTI接口
        doc: 文档对象
    
    Returns:
        tuple: (平面面ID列表, 对应的对象名称列表)
    """
    # 初始化设置
    _initialize_doc(doc)
    
    # 检查选择
    sel = ncti.SelectionManager(doc)
    if not _check_selection(sel):
        return [], []
    
    try:
        # 获取所有对象名称
        all_names = doc.AllNames()
        if not all_names:
            print("未找到对象")
            return [], []
        
        # 获取第一个对象的所有面
        first_obj_name = all_names[0]
        face_id_list = doc.FindAllFaces(first_obj_name)
        
        if not face_id_list:
            print(f"对象 {first_obj_name} 没有找到面")
            return [], []
        
        # 使用AI函数判断平面
        ai_func = ncti.AiFunction()
        face_type = ai_func.GetFacesPlanar(first_obj_name, face_id_list)
        
        # 过滤出平面的面ID
        filtered_cell_ids = [face_id for index, face_id in enumerate(face_id_list) if face_type[index]]
        
        # 创建对应的对象名称列表
        obj_names = [first_obj_name] * len(filtered_cell_ids)
        
        print(f"find_plane_by_ncti: {filtered_cell_ids}")
        return filtered_cell_ids, obj_names
        
    except Exception as e:
        print(f"查找平面时发生错误: {str(e)}")
        return [], []
