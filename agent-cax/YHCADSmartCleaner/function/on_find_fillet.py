from dialog.find_fillet import find_fillet_dialog
from function.on_find_plane import _initialize_doc, _check_selection, _find_planes
from utils.round_recongnizer import is_constant_radius_fillet_by_points_and_normals
from utils.sampler import get_face_sample


def find_fillet_with_dialog(NCTI, doc, scale_factor:float=1):
    doc.ResetCaseResult()
    fillet_types = ['全部', '凸圆角', '凹圆角']
    res = find_fillet_dialog(None, "选项", scale_factor)
    if len(res) > 0:
        min_radius = res[0]
        max_radius = res[1]
        fillet_type = fillet_types.index(res[2][0])
        sel = NCTI.SelectionManager(doc)
        fillets = doc.FindFillets(sel.ObjectNames, min_radius, max_radius, fillet_type)
        obj_names = []
        cell_ids = []
        if fillets is not None:
            for key, value in fillets.items():
                for cell_id in value:
                    obj_names.append(key)
                    cell_ids.append(cell_id)
            return cell_ids, obj_names
        return [], []
    return [], []

def find_fillet_compound(NCTI, doc, min_radius, max_radius, fillet_type):
    sel = NCTI.SelectionManager(doc)
    fillets = doc.FindFillets(sel.ObjectNames, min_radius, max_radius, fillet_type)
    obj_names = []
    cell_ids = []
    if fillets is not None:
        for key, value in fillets.items():
            for cell_id in value:
                obj_names.append(key)
                cell_ids.append(cell_id)
        sel.ObjectNames = obj_names
        sel.CellIDs = cell_ids
        return sel
    return None

def find_fillet_by_geo(ncti, doc):
    _initialize_doc(doc)
    sel = ncti.SelectionManager(doc)
    if not _check_selection(sel):
        return [], []

    # 获取点集和法线
    all_names = doc.AllNames()
    first_obj_name = all_names[0]
    face_id_list = doc.FindAllFaces(first_obj_name)
    obj_names = [first_obj_name] * len(face_id_list)
    face_points, face_normals = get_face_sample(doc, obj_names, face_id_list)
    filtered_cell_ids = []
    for index, face_id in enumerate(face_id_list):
        is_round, info = is_constant_radius_fillet_by_points_and_normals(face_points[index], face_normals[index])
        if is_round:
            filtered_cell_ids.append(face_id)
    obj_names = [first_obj_name] * len(filtered_cell_ids)
    # return _find_planes(doc, is_constant_radius_fillet_by_points_and_normals,
    #                     [face_points, face_normals])
    return filtered_cell_ids, obj_names