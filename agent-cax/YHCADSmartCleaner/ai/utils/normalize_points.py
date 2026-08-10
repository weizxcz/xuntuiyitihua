import numpy as np


def normalize(points):
    """
    对多个面上的点云进行归一化处理
    
    Args:
        points: 输入的点云数据，形状为(n, 5, 15)，其中n是面的数量，每个面有25个点
    
    Returns:
        centroid: 质心坐标，形状为(3,)
        scale: 缩放比例
        normalized_points: 归一化后的点云，保持原始形状
    """
    # 确保输入是numpy数组
    points_array = np.asarray(points)  # shape:(n, 5, 15)
    
    # 直接在原始数组上操作，避免不必要的内存复制
    # 使用reshape(-1, 3)视图而不是副本
    original_shape = points_array.shape
    flattened_view = points_array.reshape(-1, 3)
    
    # 单次遍历计算所有统计量，使用更高效的方法
    # 使用np.ptp (peak-to-peak) 计算范围，比max-min更高效
    centroid = np.mean(flattened_view, axis=0)
    coord_range = np.ptp(flattened_view, axis=0)  # 等价于 max - min，但更高效
    max_range = np.max(coord_range)
    
    # 处理边界情况，避免除零错误
    scale_ratio = 1.0 / max_range if max_range > 1e-12 else 1.0
    
    # 直接在输出数组上进行归一化，避免中间变量
    normalized_points = ((flattened_view - centroid) * scale_ratio).reshape(original_shape)
    
    return centroid, scale_ratio, normalized_points

def scale(edge_attr, scale_ratio: float):
    """
    对边缘属性中的边长进行缩放
    
    Args:
        edge_attr: 嵌套列表，形状为(n, 10)，其中每个内层列表的第四个元素（索引3）是边长
        scale_ratio: 缩放比例
    
    Returns:
        缩放后的边缘属性，保持原始形状
    """
    # 将输入转换为numpy数组
    edge_attr_array = np.array(edge_attr)  # shape:(n, 10)
    
    # 对所有边长进行缩放（第四个元素，索引为3）
    edge_attr_array[:, 3] *= scale_ratio
    
    # 返回缩放后的结果
    return edge_attr_array

def scale_to_unit_box(face_attr, centroid, scale_ratio):
    """
    对面属性中的面积和质心坐标进行平移和缩放
    
    Args:
        face_attr: 嵌套列表，形状为(n, 10)，其中每个内层列表的最后三个元素是面质心坐标
        centroid: 全局质心坐标，形状为(3,)
        scale_ratio: 缩放比例
    
    Returns:
        处理后的面属性，保持原始形状
    """
    # 将输入转换为numpy数组
    face_attr_array = np.array(face_attr)

    face_attr_array[:, 5] *= scale_ratio
    
    # 对面质心坐标（最后三个元素）进行平移和缩放
    face_attr_array[:, 7:10] = (face_attr_array[:, 7:10] - centroid) * scale_ratio
    
    # 返回处理后的结果
    return face_attr_array