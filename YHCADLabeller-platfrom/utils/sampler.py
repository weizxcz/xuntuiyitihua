import numpy as np

SAMPLE_NUMBER = 100

def get_face_sample(doc, obj_name_list, cell_id_list):
    """
    从指定的CAD模型面中采样点和法线

    Args:
        doc: CAD文档对象
        obj_name_list: 对象名称列表
        cell_id_list: 面ID列表

    Returns:
        tuple: (points, normals) - 每个面的采样点集和法线集
    """
    points = []
    normals = []

    for index, cell_id in enumerate(cell_id_list):
        # 为当前面生成SAMPLE_NUMBER个采样点
        points_in_face = []
        normals_in_face = []

        # 批量生成随机UV坐标，提高效率
        # 使用numpy批量生成随机数，减少循环次数
        uv_list = np.random.rand(SAMPLE_NUMBER, 2)

        # 批量处理每个UV坐标
        for uv in uv_list:
            # 获取点坐标
            pt = doc.GetFacePointFromUV(obj_name_list[index], cell_id, uv[0], uv[1])
            points_in_face.append([pt.X, pt.Y, pt.Z])

            # 获取法线
            vec = doc.GetNormalByUV(obj_name_list[index], cell_id, uv[0], uv[1])
            normals_in_face.append([vec.X, vec.Y, vec.Z])

        # 转换为numpy数组并添加到结果列表
        points.append(np.array(points_in_face))
        normals.append(np.array(normals_in_face))
    return points, normals
