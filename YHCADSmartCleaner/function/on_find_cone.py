from function.on_find_plane import _initialize_doc, _check_selection, _find_planes
from utils.b_face_classify import is_bspline_fit_cone_by_points_and_normals
from utils.sampler import get_face_sample


def find_cone_by_points(ncti, doc):
    """
    使用NCTI的AI函数查找圆锥面
    Args:
        ncti: NCTI接口
        doc: 文档对象
    Returns:
        tuple: (圆锥面ID列表, 对应的对象名称列表)
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
    
    # 使用辅助函数查找圆锥面
    return _find_planes(doc, is_bspline_fit_cone_by_points_and_normals,
                        [face_points, face_normals])
