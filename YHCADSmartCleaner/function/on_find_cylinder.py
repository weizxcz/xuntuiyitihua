import time

import numpy as np

from utils.b_face_classify import is_bspline_fit_cylinder_by_normal, is_bspline_fit_cylinder_by_points_and_normals
from utils.sampler import get_face_sample


def find_cylinder_by_points(ncti, doc):
    doc.SetCreateGeGeom(1)
    doc.ResetCaseResult()
    sel = ncti.SelectionManager(doc)

    if len(sel.ObjectNames) == 0:
        print(f"请先选择对象")
        return {}, []

    ai_obj = ncti.AiModel(doc, sel.ObjectNames[0])
    face_points = np.array(ai_obj.FacePoints)

    face_id_list = ai_obj.FaceID

    face_cylinder_id = []
    for index, face_id in enumerate(face_id_list):
        is_cylinder = is_bspline_fit_cylinder_by_normal(face_points[index])
        if is_cylinder:
            face_cylinder_id.append(face_id)

    obj_names = [ai_obj.objName for i in range(len(face_cylinder_id))]
    return face_cylinder_id, obj_names

def find_cylinder_by_normals(ncti, doc):
    doc.SetCreateGeGeom(1)
    doc.ResetCaseResult()
    sel = ncti.SelectionManager(doc)

    if len(sel.ObjectNames) == 0:
        print(f"请先选择对象")
        return {}, []

    all_names = doc.AllNames()
    face_id_list = doc.FindAllFaces(all_names[0])
    obj_names = [all_names[0] for i in range(len(face_id_list))]
    face_points, face_normals = get_face_sample(doc, obj_names, face_id_list)

    face_cylinder_list = []
    t1 = time.time()
    for index, face_id in enumerate(face_id_list):
        is_cylinder = is_bspline_fit_cylinder_by_normal(face_normals[index])
        if is_cylinder:
            face_cylinder_list.append(face_id)
    print(f"cylinder by normal cost:{round(time.time() - t1, 4)}")
    obj_names = [all_names[0] for i in range(len(face_cylinder_list))]
    return face_cylinder_list, obj_names

def find_cylinder_by_points_and_normals(ncti, doc):
    doc.SetCreateGeGeom(1)
    doc.ResetCaseResult()
    sel = ncti.SelectionManager(doc)

    if len(sel.ObjectNames) == 0:
        print(f"请先选择对象")
        return {}, []

    all_names = doc.AllNames()
    face_id_list = doc.FindAllFaces(all_names[0])
    obj_names = [all_names[0] for i in range(len(face_id_list))]
    face_points, face_normals = get_face_sample(doc, obj_names, face_id_list)

    face_cylinder_list = []
    for index, face_id in enumerate(face_id_list):
        is_cylinder = is_bspline_fit_cylinder_by_points_and_normals(face_points[index], face_normals[index])
        if is_cylinder:
            face_cylinder_list.append(face_id)

    obj_names = [all_names[0] for i in range(len(face_cylinder_list))]
    return face_cylinder_list, obj_names
