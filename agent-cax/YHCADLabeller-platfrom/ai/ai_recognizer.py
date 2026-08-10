from __future__ import annotations

import time

import numpy as np

from ai.utils.index_mapper import IndexMapper, IndexFilter
from ai.utils.normalize_points import normalize, scale, scale_to_unit_box

# 注意：AAGNetInference（间接 import dgl/torch）故意不放在模块顶层导入。
# 本机默认运行环境没有装 dgl，如果这里在模块加载时就 import，
# 会导致任何 import ai.ai_recognizer 的地方（包括预标注功能的
# infer_via_subprocess，它本身并不需要 dgl）在启动时直接崩溃。
# 改成在用到的函数体内延迟 import，配合上面的 `from __future__ import
# annotations`（让函数签名里的类型标注不在加载时求值），可以让本模块
# 在没有 dgl 的环境下也能正常被导入；真正调用 infer() 时该崩不崩、
# 崩溃时机没有变化。

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

    # 使用 coo_matrix 风格的构建方式
    rows = np.concatenate([face_f_id, face_e_id])
    cols = np.concatenate([face_e_id, face_f_id])
    data = np.ones(len(rows), dtype=np.int32)

    # 使用 np.add.at 处理重复边
    adj = np.zeros((num_nodes, num_nodes), dtype=np.int32)
    np.add.at(adj, (rows, cols), data)

    # 将大于 1 的值设为 1（处理多重边）
    adj = (adj > 0).astype(np.int32)

    return adj


def infer(doc, ncti, aag_net, min_faces_num=0, max_faces_num=5, feature_name='round'):
    """使用 AI 模型进行几何特征识别

    Args:
        doc: 文档对象
        ncti: NCTI 对象
        aag_net: AGGNetInference 模型对象

    Returns:
        tuple: (face_list, obj_names, face_type_dict, filtered_face_points, filtered_face_normals)
            - face_list: 识别出的面 ID 列表
            - obj_names: 对象名称列表
            - face_type_dict: 面类型字典
            - filtered_face_points: 过滤后的面点列表
            - filtered_face_normals: 过滤后的面法线列表
    """
    # 初始化选择管理器和工具类
    sel = ncti.SelectionManager(doc)
    is_selected_part = False
    mapper = IndexMapper()
    index_filter = IndexFilter()

    # 检查是否选择了对象
    if not sel.ObjectNames:
        return [], [], {}, [], []

    selected_cell_ids = sel.CellIDs
    if selected_cell_ids:
        is_selected_part = True
        ai = ncti.AiModel(doc, sel.ObjectNames[0], selected_cell_ids, False)
        # 获取面和边的 ID 信息
        face_id = ai.FaceID
        face_f_id = ai.FaceFID
        face_e_id = ai.FaceEID
        edge_id = ai.EdgeID

        # 过滤出与选中面相邻的边和选中的面本身
        filtered_cell_ids = index_filter.filter_by_neighbor(
            selected_cell_ids,
            face_ids=face_id,
            fids=face_f_id,
            eids=face_e_id,
            edge_ids=edge_id
        )

        ai = ncti.AiModel(doc, sel.ObjectNames[0], filtered_cell_ids, False, [5, 5, 10])

        original_face_id = ai.FaceID
        original_face_fid = ai.FaceFID
        original_face_eid = ai.FaceEID
        face_id = mapper.compress(original_face_id)
        face_f_id = mapper.convert(original_face_fid)
        face_e_id = mapper.convert(original_face_eid)
    else:
        ai = ncti.AiModel(doc, sel.ObjectNames[0], [], True)
        face_id = ai.FaceID
        face_f_id = ai.FaceFID
        face_e_id = ai.FaceEID
    adj_true = build_adjacency_matrix_sparse(face_f_id, face_e_id)
    face_points = ai.FacePoints
    if is_selected_part:
        centroid, scale_ratio, face_points = normalize(face_points)
    face_normals = ai.FaceNormals
    face_mask = ai.FaceMask

    original_graph_edge_attr = ai.EdgeAttr
    original_graph_face_attr = ai.FaceAttr

    # 截取相应数量的属性（根据模型维度）
    graph_face_attr = [sublist[:aag_net.node_attr_dim] for sublist in original_graph_face_attr]
    if is_selected_part:
        graph_face_attr = scale_to_unit_box(graph_face_attr, centroid, scale_ratio)
    graph_edge_attr = [sublist[:aag_net.edge_attr_dim] for sublist in original_graph_edge_attr]
    if is_selected_part:
        graph_edge_attr = scale(graph_edge_attr, scale_ratio)

    # 使用 AI 模型进行推理
    seg_out, inst_out, bottom_out = aag_net.ai_model_inference(
        face_id, face_f_id, face_e_id, face_points, face_normals,
        face_mask, graph_edge_attr, graph_face_attr
    )

    # 后处理结果
    postprocess_kwargs = {
        "min_faces_num": min_faces_num,
        "max_faces_num": max_faces_num,
        "feature_name": feature_name,
    }
    if getattr(aag_net, "maps_output_indices_to_face_ids", False):
        postprocess_kwargs["face_ids"] = face_id
    result_dict = aag_net.postprocess_feature(seg_out, inst_out, bottom_out, adj_true, **postprocess_kwargs)
    face_list = result_dict.get(0, {}).get("instance", [])

    # 如果是部分选择，解压 ID
    if is_selected_part:
        face_list = mapper.decompress(face_list)

    # 创建对象名称列表
    obj_names = [ai.objName for _ in range(len(face_list))]

    # 过滤面点和法线
    face_point_np = np.array(face_points)
    face_normals_np = np.array(face_normals)
    filtered_face_points = []
    filtered_face_normals = []

    for cell_id in face_list:
        try:
            # index = face_id.index(cell_id)
            if is_selected_part:
                index = original_face_id.index(cell_id)
            else:
                index = face_id.index(cell_id)
            filtered_face_points.append(face_point_np[index])
            filtered_face_normals.append(face_normals_np[index])
        except ValueError:
            # 如果找不到 ID，跳过
            print(f"警告：找不到面 ID {cell_id} 的索引")
            continue

    # 解析面属性
    face_type_dict = parse_face_attr(graph_face_attr, face_id)

    return face_list, obj_names, face_type_dict, filtered_face_points, filtered_face_normals

def infer_via_subprocess(doc, ncti, weight_path, stat_path, python_exe=None,
                         min_faces_num=0, max_faces_num=9, feature_name='ai_feature',
                         obj_name=None):
    """整机推理（不支持局部选择），模型前向计算在独立子进程（yhcad_env）中完成。

    用于预标注功能：主进程只负责通过 NCTI 取几何数据，真正需要 torch/dgl 的
    模型推理部分交给 ai/infer_worker.py 在子进程里跑，绕开本机默认环境没有
    dgl 的限制。

    Args:
        obj_name: 指定要推理的对象名。为 None 时走 SelectionManager 取当前选中
            对象（GUI 主文档场景，依赖已有选中状态）。批量预标注用的后台文档
            没有视图、不会有选中状态，必须显式传入（通常是 doc.AllNames()[0]）。

    Returns:
        tuple: (face_list, obj_names, groups, all_face_id)
            - face_list: 识别出的面 ID 列表
            - obj_names: 对象名称列表（与 face_list 等长）
            - groups: 按连通性分组后的面 ID 列表的列表
            - all_face_id: 整机的全部面 ID 列表（用于确定零件真实总面数）
    """
    from .infer_client import run_inference_subprocess

    # 与 find_feature_by_ai 里的既定顺序一致：调用 AiModel/推理前必须先
    # SetCreateGeGeom(1) + ResetCaseResult()，否则同一文档上连续多次预标注
    # 可能带着上一次推理的残留 case 状态。
    doc.SetCreateGeGeom(1)
    doc.ResetCaseResult()

    if obj_name is None:
        sel = ncti.SelectionManager(doc)
        if not sel.ObjectNames:
            return [], [], [], []
        obj_name = sel.ObjectNames[0]

    ai = ncti.AiModel(doc, obj_name, [], True)
    face_id = ai.FaceID
    face_f_id = ai.FaceFID
    face_e_id = ai.FaceEID
    adj_true = build_adjacency_matrix_sparse(face_f_id, face_e_id)
    face_points = ai.FacePoints
    face_normals = ai.FaceNormals
    face_mask = ai.FaceMask
    graph_edge_attr = ai.EdgeAttr
    graph_face_attr = ai.FaceAttr

    face_list, groups = run_inference_subprocess(
        weight_path, stat_path,
        face_id, face_f_id, face_e_id, face_points, face_normals, face_mask,
        graph_edge_attr, graph_face_attr, adj_true.tolist(),
        min_faces_num=min_faces_num, max_faces_num=max_faces_num, feature_name=feature_name,
        python_exe=python_exe,
    )
    obj_names = [ai.objName for _ in range(len(face_list))]
    return face_list, obj_names, groups, face_id


def parse_face_attr(graph_face_attr, face_id):
    """
    将面属性从浮点数表示转换为字符串表示，并与 face_id 绑定为字典

    Args:
        graph_face_attr (list): 嵌套列表，每个子列表包含面的属性
        face_id (list): 面 ID 列表

    Returns:
        dict: 键为 face_id 值，值为面类型字符串的字典
    """
    # 定义面类型映射关系
    face_type_map = [
        "平面",
        "圆柱面",
        "圆锥面",
        "球面",
        "环面"
    ]

    result = {}

    # 遍历每个面
    for i, (face_attr, fid) in enumerate(zip(graph_face_attr, face_id)):
        face_type = "未知"

        # 先检查前 5 个属性（平面到环面）
        for j in range(5):
            if face_attr[j] == 1.0:
                face_type = face_type_map[j]
                break

        # 如果不是前 5 种类型，检查是否为有理 nurbs 面
        if face_type == "未知" and face_attr[6] == 1.0:
            face_type = "有理 nurbs 面"

        if face_type == "未知":
            face_type = "平面"

        # 添加到结果字典
        result[fid] = face_type

    return result
