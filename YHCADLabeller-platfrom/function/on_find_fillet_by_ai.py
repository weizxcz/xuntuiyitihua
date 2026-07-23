from ai.AAGNet_infer.model_cache import get_cached_aag_net
from ai.ai_recognizer import infer
from utils.b_face_classify import is_bspline_fit_plane_by_normal, is_bspline_fit_cylinder_by_normal, \
    is_bspline_fit_cone_by_points_and_normals
from utils.sampler import get_face_sample


def find_feature_by_ai(NCTI, doc, weight_path, stat_path, min_faces_num=2,
                       max_faces_num=5, feature_name='round', use_onnx=False):
    doc.SetCreateGeGeom(1)
    doc.ResetCaseResult()
    aag_net = get_cached_aag_net(weight_path=weight_path, stat_path=stat_path, use_onnx=use_onnx)
    cell_ids, obj_names, face_type_dict, filtered_face_points, filtered_face_normals = infer(doc, NCTI, aag_net,
                                                                                             min_faces_num=min_faces_num,
                                                                                             max_faces_num=max_faces_num,
                                                                                             feature_name=feature_name)
    return cell_ids, obj_names, face_type_dict, filtered_face_points, filtered_face_normals

def filter_by_face_type(cell_ids, obj_names, face_type_dict):
    """
    从face_list的cell id中过滤掉类型为"平面"的项

    Args:
        cell_ids (list): 包含cell id的列表
        obj_names (list): 对象名称列表
        face_type_dict (dict): 键为face_id值，值为面类型字符串的字典

    Returns:
        list: 过滤后的结果，包含所有非平面类型的cell id
    """
    # 遍历cell_ids中的cell id，过滤掉类型为"平面"的项
    filtered_cell_id = []
    filtered_obj_name = []

    # 检查face_list的类型，确保能正确遍历cell id
    for i, cell_id in enumerate(cell_ids):
        if cell_id in face_type_dict:
            if face_type_dict[cell_id] != "平面":
                filtered_cell_id.append(cell_id)
                filtered_obj_name.append(obj_names[i])
    return filtered_cell_id, filtered_obj_name

def filter_by_face_type_ncti(ncti, cell_ids, obj_names):
    if not cell_ids:
        return [], []
    ai_func = ncti.AiFunction()
    face_type = ai_func.GetFacesPlanar(obj_names[0], cell_ids)
    filtered_cell_ids = [face_id for index, face_id in enumerate(cell_ids) if not face_type[index]]
    filtered_obj_name = [obj_names[0]] * len(filtered_cell_ids)
    return filtered_cell_ids, filtered_obj_name

def filter_by_plane(doc, cell_ids, obj_names):
    if not cell_ids:
        return [], []
    filtered_cell_id = []
    filtered_obj_name = []
    face_points, face_normals = get_face_sample(doc, obj_names, cell_ids)
    for index, cell_id in enumerate(cell_ids):
        is_plane = is_bspline_fit_plane_by_normal(face_normals[index])
        if not is_plane:
            filtered_cell_id.append(cell_id)
            filtered_obj_name.append(obj_names[index])
    return filtered_cell_id, filtered_obj_name

def filter_by_cylinder(doc, cell_ids, obj_names):
    if not cell_ids:
        return [], []
    filtered_cell_id = []
    filtered_obj_name = []

    face_points, face_normals = get_face_sample(doc, obj_names, cell_ids)

    for index, face_id in enumerate(cell_ids):
        is_cylinder = is_bspline_fit_cylinder_by_normal(face_normals[index])
        if not is_cylinder:
            filtered_cell_id.append(face_id)
            filtered_obj_name.append(obj_names[index])
    return filtered_cell_id, filtered_obj_name

def filter_by_cone(doc, cell_ids, obj_names):
    filtered_cell_id = []
    filtered_obj_name = []

    face_points, face_normals = get_face_sample(doc, obj_names, cell_ids)
    for index, face_id in enumerate(cell_ids):
        is_cone = is_bspline_fit_cone_by_points_and_normals(face_normals[index], face_normals[index])
        if not is_cone:
            filtered_cell_id.append(face_id)
            filtered_obj_name.append(obj_names[index])
    return filtered_cell_id, filtered_obj_name
