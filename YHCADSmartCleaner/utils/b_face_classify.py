import numpy as np

from scipy.linalg import svd
from scipy.optimize import least_squares

def is_bspline_fit_plane_by_points(points:np.ndarray)->bool:
    """
    判断bspline是否拟合平面
    
    Args:
        points: 输入点集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
    
    Returns:
        bool: 如果点集近似平面返回True，否则返回False
    """
    # 预处理点集，确保形状为 [num_points, 3]
    if points.ndim == 3:
        # 处理 [num_u, num_v, 3] 形状的输入
        num_u, num_v, _ = points.shape
        points = points.reshape(-1, 3)
    elif points.ndim == 2:
        # 处理 [num_points, 3] 形状的输入
        if points.shape[1] != 3:
            # 处理特殊情况：每一行包含多个点的坐标
            points = points.reshape(-1, 3)
    
    # 确保点集至少有3个点
    if len(points) < 3:
        return False
    
    # PCA/SVD 拟合平面（对任意朝向的平面都有效，不依赖 z=f(x,y) 假设）
    centroid = np.mean(points, axis=0)
    centered = points - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)

    # 最小特征值对应的特征向量即为平面法向
    normal = eigvecs[:, 0]

    # 每个点到拟合平面的距离
    distances = np.abs(centered @ normal)
    max_distance = np.max(distances)

    # 计算点集的边界框大小
    bbox_size = np.max(np.ptp(points, axis=0))

    # 相对阈值：最大距离小于边界框大小的1%
    relative_threshold = bbox_size * 0.01

    # 绝对阈值：考虑数值精度
    absolute_threshold = 1e-4

    # 使用相对阈值和绝对阈值的最大值作为最终阈值
    threshold = max(relative_threshold, absolute_threshold)

    return max_distance < threshold

def _align_normals_robust(normalized_normals: np.ndarray) -> np.ndarray:
    """用中位数投票对齐法线方向，避免离群法线污染。

    两轮对齐：先用绝对值均值消除180°歧义，再用中位数抵抗离群点。
    """
    # 第一步：用绝对值均值确定粗略轴向（解决180°歧义）
    abs_mean = np.mean(np.abs(normalized_normals), axis=0)
    abs_mean_norm = np.linalg.norm(abs_mean)
    if abs_mean_norm < 1e-6:
        return normalized_normals
    abs_mean = abs_mean / abs_mean_norm

    # 第二步：用粗略轴向对齐所有法线
    dots = normalized_normals @ abs_mean
    roughly_aligned = np.where(
        (dots < 0)[:, np.newaxis],
        -normalized_normals,
        normalized_normals
    )

    # 第三步：用对齐后法线的中位数作为鲁棒参考方向
    median_ref = np.median(roughly_aligned, axis=0)
    median_norm = np.linalg.norm(median_ref)
    if median_norm < 1e-6:
        return roughly_aligned
    median_ref = median_ref / median_norm

    # 第四步：用中位数参考方向重新对齐
    dots = normalized_normals @ median_ref
    adjusted = np.where(
        (dots < 0)[:, np.newaxis],
        -normalized_normals,
        normalized_normals
    )
    return adjusted


def is_bspline_fit_plane_by_normal(face_normals:np.ndarray)->bool:
    """
    判断bspline是否拟合平面
    
    Args:
        face_normals: 输入法线集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
    
    Returns:
        bool: 如果面近似平面返回True，否则返回False
    """
    # 预处理法线集，确保形状为 [num_points, 3]
    if face_normals.ndim == 3:
        # 处理 [num_u, num_v, 3] 形状的输入
        num_u, num_v, _ = face_normals.shape
        normals = face_normals.reshape(-1, 3)
    elif face_normals.ndim == 2:
        # 处理 [num_points, 3] 形状的输入
        if face_normals.shape[1] != 3:
            # 处理特殊情况：每一行包含多个法线的坐标
            normals = face_normals.reshape(-1, 3)
        else:
            normals = face_normals
    
    # 确保法线集至少有3个点
    if len(normals) < 3:
        return False
    
    # 归一化所有法线向量
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 避免除零错误
    normalized_normals = normals / norms
    
    # 使用中位数投票对齐法线方向，避免离群法线污染
    adjusted_normals = _align_normals_robust(normalized_normals)
    
    # 计算平均法线
    mean_normal = np.mean(adjusted_normals, axis=0)
    
    # 归一化平均法线
    mean_normal_norm = np.linalg.norm(mean_normal)
    if mean_normal_norm == 0:
        return False
    mean_normal = mean_normal / mean_normal_norm
    
    # 计算每个法线向量与平均法线向量之间的夹角（弧度）
    # 夹角 = arccos(dot_product)
    dot_products = np.dot(adjusted_normals, mean_normal)
    # 确保dot_product在[-1, 1]范围内，避免数值误差
    dot_products = np.clip(dot_products, -1.0, 1.0)
    angles = np.arccos(dot_products)
    
    # 转换为角度，方便理解
    angles_deg = np.rad2deg(angles)
    
    # 设定阈值，判断所有夹角是否都小于该阈值
    # 对于平面，所有法线应该基本一致，夹角应该很小
    # 调整阈值为3度，提高对真实曲面的容错性
    angle_threshold_deg = 6.0
    
    # 判断是否所有夹角都小于阈值
    max_angle = np.max(angles_deg)
    
    # 添加调试信息
    # print(f"法线数量：{len(adjusted_normals)}")
    # print(f"平均法线：{mean_normal}")
    # print(f"最大夹角（度）：{max_angle:.6f}")
    # print(f"夹角阈值（度）：{angle_threshold_deg}")
    
    return max_angle < angle_threshold_deg

def is_bspline_fit_plane_by_points_and_normal(points:np.ndarray, normals:np.ndarray)->bool:
    """
    判断bspline是否拟合平面
    
    Args:
        points: 输入点集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
        normals: 输入法线集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
    
    Returns:
        bool: 如果面近似平面返回True，否则返回False
    """
    # 预处理点集和法线集
    if points.ndim == 3:
        num_u, num_v, _ = points.shape
        points = points.reshape(-1, 3)
    elif points.ndim == 2:
        if points.shape[1] != 3:
            points = points.reshape(-1, 3)
    
    if normals.ndim == 3:
        num_u, num_v, _ = normals.shape
        normals = normals.reshape(-1, 3)
    elif normals.ndim == 2:
        if normals.shape[1] != 3:
            normals = normals.reshape(-1, 3)
    
    # 确保点集和法线集至少有足够的点数
    if len(points) < 3 or len(normals) < 3:
        return False
    
    # 1. 优先使用法线信息，因为法线对平面的判断更可靠
    # 归一化所有法线
    normals_norm = np.linalg.norm(normals, axis=1, keepdims=True)
    normals_norm[normals_norm == 0] = 1.0  # 避免除零错误
    normalized_normals = normals / normals_norm
    
    # 2. 使用中位数投票对齐法线方向
    adjusted_normals = _align_normals_robust(normalized_normals)

    # 3. 计算平均法线
    mean_normal = np.mean(adjusted_normals, axis=0)
    mean_normal_norm = np.linalg.norm(mean_normal)
    if mean_normal_norm == 0:
        return False
    mean_normal = mean_normal / mean_normal_norm  # 归一化

    # 4. 计算法线之间的一致性
    dot_products = np.dot(adjusted_normals, mean_normal)
    dot_products = np.clip(dot_products, -1.0, 1.0)
    angles = np.arccos(dot_products)
    angles_deg = np.rad2deg(angles)
    max_angle = np.max(angles_deg)

    # 调整法线阈值，使其更适合真实曲面的情况
    angle_threshold_deg = 3.0  # 3度阈值，提高容错性

    # 5. PCA/SVD 计算点集平面度（对任意朝向的平面都有效）
    centroid = np.mean(points, axis=0)
    centered = points - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    point_normal = eigvecs[:, 0]
    point_distances = np.abs(centered @ point_normal)
    
    # 计算点集的边界框大小
    x_min, y_min, z_min = np.min(points, axis=0)
    x_max, y_max, z_max = np.max(points, axis=0)
    bbox_size = np.max([x_max - x_min, y_max - y_min, z_max - z_min])
    
    # 设置点集平面度阈值
    point_distance_threshold = max(bbox_size * 0.05, 1e-4)
    max_point_distance = np.max(point_distances)
    mean_point_distance = np.mean(point_distances)
    
    # 6. 综合判断，给予点集信息和法线信息同等权重
    # 情况1：法线高度一致，直接判定为平面
    is_high_normal_consistency = max_angle < angle_threshold_deg * 0.3
    
    # 情况2：点集非常接近平面，直接判定为平面
    is_very_planar_points = max_point_distance < point_distance_threshold * 0.5
    
    # 情况3：法线基本一致且点集基本在平面上
    is_normal_consistent = max_angle < angle_threshold_deg
    is_planar_points = max_point_distance < point_distance_threshold and mean_point_distance < point_distance_threshold * 0.5
    is_normal_and_planar = is_normal_consistent and is_planar_points
    
    # 情况4：法线有偏差但点集非常接近平面
    is_points_dominant = max_point_distance < point_distance_threshold * 0.3 and max_angle < angle_threshold_deg * 2.0
    
    # 综合所有情况，只要满足其中一种，就判定为平面
    return is_high_normal_consistency or is_very_planar_points or is_normal_and_planar or is_points_dominant

def is_bspline_fit_cone_by_normal(face_normals:np.ndarray)->bool:
    """
    判断bspline是否拟合圆锥面
    
    Args:
        face_normals: 输入法线集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
    
    Returns:
        bool: 如果面近似圆锥面返回True，否则返回False
    """
    # 预处理法线集，确保形状为 [num_points, 3]
    if face_normals.ndim == 3:
        # 处理 [num_u, num_v, 3] 形状的输入
        num_u, num_v, _ = face_normals.shape
        normals = face_normals.reshape(-1, 3)
    elif face_normals.ndim == 2:
        # 处理 [num_points, 3] 形状的输入
        if face_normals.shape[1] != 3:
            # 处理特殊情况：每一行包含多个法线的坐标
            normals = face_normals.reshape(-1, 3)
        else:
            normals = face_normals
    
    # 确保法线集至少有5个点
    if len(normals) < 5:
        return False
    
    # 归一化所有法线向量
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 避免除零错误
    normalized_normals = normals / norms
    
    # 圆锥面的法线特征：所有法线与轴线方向的夹角相同
    
    # 计算法线的平均方向作为圆锥面的轴线方向
    axis_direction = np.mean(normalized_normals, axis=0)
    axis_direction_norm = np.linalg.norm(axis_direction)
    if axis_direction_norm == 0:
        return False
    axis_direction = axis_direction / axis_direction_norm
    
    # 计算每个法线与轴线方向的夹角
    dot_products = np.dot(normalized_normals, axis_direction)
    dot_products = np.clip(dot_products, -1.0, 1.0)
    angles = np.arccos(dot_products)
    angles_deg = np.rad2deg(angles)
    
    # 圆锥面的法线与轴线方向的夹角应该呈现一定的分布
    # 计算夹角的标准差
    angle_std = np.std(angles_deg)
    
    # 设定阈值
    # 圆锥面的法线夹角标准差应该在一定范围内
    angle_std_threshold = 10.0  # 允许10度的偏差
    
    return angle_std < angle_std_threshold

def is_bspline_fit_cylinder_by_normal(face_normals: np.ndarray) -> bool:
    """
    判断bspline是否拟合圆柱面

    Args:
        face_normals: 输入法线集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]

    Returns:
        bool: 如果面近似圆柱面返回True，否则返回False
    """
    # 预处理法线集，确保形状为 [num_points, 3]
    if face_normals.ndim == 3:
        # 处理 [num_u, num_v, 3] 形状的输入
        num_u, num_v, _ = face_normals.shape
        normals = face_normals.reshape(-1, 3)
    elif face_normals.ndim == 2:
        # 处理 [num_points, 3] 形状的输入
        if face_normals.shape[1] != 3:
            # 处理特殊情况：每一行包含多个法线的坐标
            normals = face_normals.reshape(-1, 3)
        else:
            normals = face_normals

    # 确保法线集至少有8个点
    if len(normals) < 8:
        return False

    # 归一化所有法线向量
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 避免除零错误
    normalized_normals = normals / norms

    # 圆柱面的法线特征：
    # 1. 所有法线都在垂直于轴线的平面内
    # 2. 法线方向指向圆柱面的径向

    # 改进的实现：
    # 1. 确定圆柱面的轴线方向
    # 圆柱面的法线应该都垂直于轴线方向
    # 使用PCA分析法线的方向分布
    cov_matrix = np.cov(normalized_normals.T)
    eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)

    # 特征值排序（从大到小）
    sorted_indices = np.argsort(eigenvalues)[::-1]
    sorted_eigenvalues = eigenvalues[sorted_indices]
    sorted_eigenvectors = eigenvectors[:, sorted_indices]

    # 圆柱面法线的特征：法线应该主要分布在两个垂直方向上
    # 第一个特征值应该显著大于第三个特征值
    if sorted_eigenvalues[0] < sorted_eigenvalues[2] * 3.0:
        return False

    # 轴线方向对应法线分布的最小变化方向
    axis_direction = sorted_eigenvectors[:, 2]

    # 2. 检查所有法线是否都近似垂直于轴线方向
    # 计算法线与轴线方向的点积
    dot_products = np.dot(normalized_normals, axis_direction)
    dot_products = np.clip(dot_products, -1.0, 1.0)

    # 计算法线与轴线方向的夹角余弦值的绝对值
    cos_angles = np.abs(dot_products)

    # 圆柱面的法线应该接近垂直于轴线方向
    # 计算平均余弦值
    avg_cos_angle = np.mean(cos_angles)
    max_cos_angle = np.max(cos_angles)

    # 设定更严格的阈值
    avg_cos_threshold = 0.1  # 平均余弦值应该小于0.1（约84度）
    max_cos_threshold = 0.2  # 最大余弦值应该小于0.2（约78度）

    if avg_cos_angle > avg_cos_threshold or max_cos_angle > max_cos_threshold:
        return False

    # 3. 检查法线的分布特性：圆柱面的法线应该呈现放射状分布
    # 计算法线在垂直于轴线平面上的投影
    # 投影矩阵
    axis_matrix = np.outer(axis_direction, axis_direction)
    projection_matrix = np.eye(3) - axis_matrix

    # 投影法线到垂直于轴线的平面
    projected_normals = np.dot(normalized_normals, projection_matrix)

    # 归一化投影后的法线
    projected_norms = np.linalg.norm(projected_normals, axis=1, keepdims=True)
    projected_norms[projected_norms == 0] = 1.0
    projected_normals = projected_normals / projected_norms

    # 计算投影法线的极角
    polar_angles = []
    for normal in projected_normals:
        angle = np.arctan2(normal[1], normal[0])
        polar_angles.append(angle)

    polar_angles = np.array(polar_angles)

    # 圆柱面的法线在极角上应该均匀分布
    # 计算极角的标准差
    angle_std = np.std(polar_angles)

    # 极角标准差应该较大（均匀分布）
    if angle_std < np.pi / 6:  # 小于30度，说明分布不均匀
        return False

    # 4. 额外验证：检查法线是否指向径向
    # 计算法线之间的夹角分布
    # 随机选择一些法线对，计算它们的夹角
    angle_pairs = []
    sample_size = min(50, len(projected_normals))
    for i in range(sample_size):
        for j in range(i + 1, sample_size):
            normal1 = projected_normals[i]
            normal2 = projected_normals[j]
            dot_product = np.dot(normal1, normal2)
            dot_product = np.clip(dot_product, -1.0, 1.0)
            angle = np.arccos(dot_product)
            angle_pairs.append(angle)

    if len(angle_pairs) > 0:
        angle_pairs = np.array(angle_pairs)
        avg_angle = np.mean(angle_pairs)

        # 圆柱面法线之间的平均夹角应该在合理范围内
        if avg_angle < np.pi / 6 or avg_angle > np.pi * 2 / 3:  # 30度到120度之间
            return False

    return True

def is_bspline_fit_cylinder_by_points_and_normals(face_points:np.ndarray, face_normals:np.ndarray)->bool:
    """
    综合点坐标和法线，判定曲面是不是直圆柱面
    直圆柱面不必是完整的，但需要有某一部分的截面为圆形
    
    Args:
        face_points: 输入点集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
        face_normals: 输入法线集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
    
    Returns:
        bool: 如果面近似直圆柱面返回True，否则返回False
    """
    # 预处理点集和法线集，确保形状为 [num_points, 3]
    if face_points.ndim == 3:
        # 处理 [num_u, num_v, 3] 形状的输入
        num_u, num_v, _ = face_points.shape
        points = face_points.reshape(-1, 3)
    elif face_points.ndim == 2:
        # 处理 [num_points, 3] 形状的输入
        if face_points.shape[1] != 3:
            # 处理特殊情况：每一行包含多个点的坐标
            points = face_points.reshape(-1, 3)
        else:
            points = face_points
    else:
        return False
    
    # 预处理法线集
    if face_normals.ndim == 3:
        # 处理 [num_u, num_v, 3] 形状的输入
        normals = face_normals.reshape(-1, 3)
    elif face_normals.ndim == 2:
        # 处理 [num_points, 3] 形状的输入
        if face_normals.shape[1] != 3:
            # 处理特殊情况：每一行包含多个法线的坐标
            normals = face_normals.reshape(-1, 3)
        else:
            normals = face_normals
    else:
        return False
    
    # 确保点集和法线集数量一致
    if len(points) != len(normals):
        return False
    
    # 确保点集数量足够
    # 经验表明，至少需要50个点才能获得稳定的检测结果
    if len(points) < 50:
        return False
    
    # 归一化所有法线向量
    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # 避免除零错误
    normalized_normals = normals / norms
    
    # 简化的直圆柱面判定逻辑，直接利用几何特性
    
    # 增加平面检测：平面的所有法线都是平行的，而圆柱面的法线是径向分布的
    # 检查法线的一致性，判断是否为平面
    # 计算法线的平均向量
    mean_normal = np.mean(normalized_normals, axis=0)
    mean_normal = mean_normal / np.linalg.norm(mean_normal) if np.linalg.norm(mean_normal) != 0 else mean_normal
    
    # 计算所有法线与平均法线的夹角
    dot_products = np.dot(normalized_normals, mean_normal)
    dot_products = np.clip(dot_products, -1.0, 1.0)
    angles = np.arccos(np.abs(dot_products))
    
    # 平面的法线应该高度一致，所有夹角都很小
    avg_angle = np.mean(angles)
    max_angle = np.max(angles)
    
    # 设置平面检测阈值
    plane_angle_threshold = 0.1  # 约5.7度
    if avg_angle < plane_angle_threshold and max_angle < plane_angle_threshold * 2:
        return False  # 是平面，不是圆柱面
    
    # 阶段一：确定圆柱轴线方向
    # 圆柱面的所有法线都垂直于轴线，因此轴线方向可以通过法线的PCA分析得到
    
    # 计算法线的协方差矩阵
    cov_normals = np.cov(normalized_normals.T)
    
    # 计算特征值和特征向量
    eigenvalues, eigenvectors = np.linalg.eigh(cov_normals)
    
    # 特征值排序（从大到小）
    sorted_indices = np.argsort(eigenvalues)[::-1]
    sorted_eigenvalues = eigenvalues[sorted_indices]
    sorted_eigenvectors = eigenvectors[:, sorted_indices]
    
    # 轴线方向对应法线分布的最小变化方向（第三个特征向量）
    axis_direction = sorted_eigenvectors[:, 2]
    
    # 阶段二：验证所有法线都垂直于轴线
    # 计算法线与轴线方向的点积
    dot_products = np.dot(normalized_normals, axis_direction)
    dot_products = np.clip(dot_products, -1.0, 1.0)
    
    # 法线应接近垂直于轴线，点积的绝对值应很小
    avg_dot = np.mean(np.abs(dot_products))
    max_dot = np.max(np.abs(dot_products))
    
    # 设置阈值
    dot_threshold_avg = 0.1  # 平均点积阈值
    dot_threshold_max = 0.2  # 最大点积阈值
    
    if avg_dot > dot_threshold_avg or max_dot > dot_threshold_max:
        return False
    
    # 阶段三：拟合圆柱轴线位置和半径
    # 方法：使用投影法，将点投影到垂直于轴线的平面，然后拟合圆
    
    # 步骤1：验证点集在三维空间中的分布
    # 计算点集的三维分布特征，确保不是平面
    points_cov = np.cov(points.T)
    points_eigenvalues, _ = np.linalg.eigh(points_cov)
    points_sorted_eigenvalues = np.sort(points_eigenvalues)[::-1]
    
    # 计算点集的平面度：最小特征值与最大特征值的比值
    planarity = points_sorted_eigenvalues[2] / points_sorted_eigenvalues[0]
    
    # 如果点集高度平坦，可能是平面，不是圆柱面
    if planarity < 1e-3:
        return False
    
    # 步骤2：将所有点投影到垂直于轴线的平面
    axis_matrix = np.outer(axis_direction, axis_direction)
    projection_matrix = np.eye(3) - axis_matrix
    projected_points = np.dot(points, projection_matrix)
    
    # 步骤2：在垂直平面内拟合圆
    def fit_circle_2d(points_2d):
        """2D圆拟合（最小二乘方法）
        Args:
            points_2d: 2D点集
        Returns:
            tuple: (center_x, center_y, radius)
        """
        if len(points_2d) < 3:
            return 0.0, 0.0, 0.0
        
        # 构建矩阵A和向量B
        A = np.zeros((len(points_2d), 3))
        B = np.zeros(len(points_2d))
        
        for i, (x, y) in enumerate(points_2d):
            A[i] = [2*x, 2*y, 1]
            B[i] = x**2 + y**2
        
        # 求解线性方程组
        coeffs, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
        
        # 计算圆心和半径
        cx, cy, c = coeffs
        radius = np.sqrt(cx**2 + cy**2 + c)
        
        return cx, cy, radius
    
    # 将投影点转换为2D（选择合适的坐标系）
    # 选择前两个主成分作为2D坐标系
    proj_cov = np.cov(projected_points.T)
    proj_eigenvalues, proj_eigenvectors = np.linalg.eigh(proj_cov)
    proj_sorted_indices = np.argsort(proj_eigenvalues)[::-1]
    
    # 构建2D投影矩阵
    proj_2d_matrix = proj_eigenvectors[:, proj_sorted_indices[:2]]
    
    # 转换为2D点
    points_2d = np.dot(projected_points, proj_2d_matrix)
    
    # 拟合2D圆
    center_2d_x, center_2d_y, radius = fit_circle_2d(points_2d)
    
    if radius < 1e-6:
        return False
    
    # 计算3D圆心
    center_3d = np.dot(np.array([center_2d_x, center_2d_y]), proj_2d_matrix.T)
    
    # 阶段四：验证所有点到轴线的距离都接近相等
    # 计算每个点到轴线的距离
    distances_to_axis = []
    for p in points:
        # 计算点到轴线的向量
        v = p - center_3d
        # 计算垂直于轴线的分量
        v_perp = v - np.dot(v, axis_direction) * axis_direction
        # 距离即为垂直分量的长度
        distance = np.linalg.norm(v_perp)
        distances_to_axis.append(distance)
    
    distances_to_axis = np.array(distances_to_axis)
    
    # 计算距离统计值
    mean_distance = np.mean(distances_to_axis)
    std_distance = np.std(distances_to_axis)
    
    # 设置距离阈值（允许一定的相对偏差）
    distance_threshold = radius * 0.15  # 允许15%的相对偏差
    
    if std_distance > distance_threshold:
        return False
    
    # 阶段五：验证法线方向指向径向
    # 计算每个点到轴线的垂足
    def get_foot_point(p, axis_point, axis_dir):
        """计算点p到轴线的垂足
        Args:
            p: 空间点
            axis_point: 轴线上一点
            axis_dir: 轴线方向向量
        Returns:
            np.ndarray: 垂足坐标
        """
        v = p - axis_point
        t = np.dot(v, axis_dir)
        return axis_point + t * axis_dir
    
    # 验证法线与径向的一致性
    normal_consistency = []
    
    for i, p in enumerate(points):
        # 计算垂足
        foot = get_foot_point(p, center_3d, axis_direction)
        
        # 计算径向向量
        radial = p - foot
        radial_len = np.linalg.norm(radial)
        
        if radial_len < 1e-6:
            continue
        
        # 归一化径向向量
        radial_unit = radial / radial_len
        
        # 检查法线是否指向径向
        cos_theta = np.dot(normalized_normals[i], radial_unit)
        normal_consistency.append(np.abs(cos_theta))
    
    # 计算法向量一致性比例
    mean_consistency = np.mean(normal_consistency)
    
    # 设置法向量一致性阈值
    consistency_threshold = 0.7  # 法线与径向的夹角余弦值应接近1
    
    if mean_consistency < consistency_threshold:
        return False
    
    # 所有验证都通过，判定为直圆柱面
    return True

def is_bspline_fit_part_cylinder_by_points_and_normals(points: np.ndarray, normals: np.ndarray) -> bool:
    """
    根据点云和法线判定给定的曲面是不是部分的圆柱面
    
    Args:
        points: 输入点集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
        normals: 输入法线集，形状可以是 [num_u, num_v, 3] 或 [num_points, 3]
    
    Returns:
        bool: 如果面近似圆锥面返回True，否则返回False
    """
    # 1. 数据预处理：将输入转换为统一格式 [num_points, 3]
    points = points.reshape(-1, 3)
    normals = normals.reshape(-1, 3)
    
    # 确保点和法线数量匹配
    if points.shape[0] != normals.shape[0]:
        raise ValueError("点集和法线集的数量不匹配")
    
    # 如果点太少，无法可靠判断
    if points.shape[0] < 10:
        return False
    
    # 2. 法线方向一致性检查
    # 计算法线方向的平均值和标准差
    avg_normal = np.mean(normals, axis=0)
    avg_normal /= np.linalg.norm(avg_normal)
    
    # 检查法线是否大致指向同一方向或相反方向
    normal_directions = np.sign(np.sum(normals * avg_normal, axis=1))
    direction_consistency = np.sum(normal_directions > 0) / len(normal_directions)
    
    # 如果法线方向太分散，可能不是圆锥面
    if direction_consistency < 0.7 and direction_consistency > 0.3:
        return False
    
    # 3. 估计圆锥轴线方向
    # 圆锥面的法线都应该与轴线保持恒定角度
    # 我们可以通过分析法线之间的关系来估计轴线
    
    # 计算法线之间的叉积，这些叉积应该都近似平行于圆锥轴线
    cross_products = []
    for i in range(len(normals)):
        for j in range(i+1, min(i+10, len(normals))):  # 只与附近的法线计算叉积，提高效率
            cross = np.cross(normals[i], normals[j])
            if np.linalg.norm(cross) > 0.1:  # 避免几乎平行的法线产生的小叉积
                cross_products.append(cross / np.linalg.norm(cross))
    
    if len(cross_products) < 5:
        return False
    
    cross_products = np.array(cross_products)
    
    # 使用SVD找到叉积的主方向，这应该是圆锥轴线方向
    _, _, V = svd(cross_products)
    axis_direction = V[0]
    
    # 4. 验证圆锥面特征
    # 圆锥面上任意一点的法线与轴线之间的夹角应该是恒定的
    
    # 计算每个法线与轴线的夹角余弦值
    angles_cos = np.abs(np.sum(normals * axis_direction, axis=1))
    
    # 计算角度余弦值的标准差，圆锥面应该有较小的标准差
    angle_std = np.std(angles_cos)
    
    # 计算角度余弦值的范围
    angle_range = np.max(angles_cos) - np.min(angles_cos)
    
    # 5. 几何形状验证
    # 计算点云的边界框
    min_bounds = np.min(points, axis=0)
    max_bounds = np.max(points, axis=0)
    size = max_bounds - min_bounds
    
    # 计算点云的主轴
    centered_points = points - np.mean(points, axis=0)
    _, _, V_points = svd(centered_points)
    principal_axis = V_points[0]
    
    # 检查主轴与估计的圆锥轴线是否一致
    axis_alignment = np.abs(np.dot(principal_axis, axis_direction))
    
    # 6. 综合判断
    # 设置自适应阈值
    num_points = len(points)
    angle_std_threshold = 0.05 + 0.05 * min(1, 500 / num_points)  # 点越多，阈值越严格
    angle_range_threshold = 0.1 + 0.1 * min(1, 500 / num_points)
    
    # 圆锥面的法线与轴线夹角应该相对一致
    angle_consistency = angle_std < angle_std_threshold and angle_range < angle_range_threshold
    
    # 圆锥轴线应该与点云的主轴大致一致
    axis_consistency = axis_alignment > 0.7
    
    # 综合判断是否为圆锥面
    is_cone = angle_consistency and axis_consistency
    
    return is_cone


def is_bspline_fit_cone_by_points_and_normals(
    points: np.ndarray,
    normals: np.ndarray,
    angle_tol_deg: float = 8.0,          # 放宽角度容忍度
    normal_std_tol: float = 0.1,         # |n·a| 的标准差容忍度
    min_point_inlier_ratio: float = 0.6, # 降低内点比例要求
    max_opt_iter: int = 200
) -> bool:
    """
    稳定版：判定是否为圆锥面（points 与 normals 无需对应）
    修复：消除随机性、双向轴向、扩大顶点搜索、fallback 机制
    """

    def _flatten(arr):
        if arr.ndim == 3:
            return arr.reshape(-1, 3)
        elif arr.ndim == 2 and arr.shape[1] == 3:
            return arr
        else:
            raise ValueError("Input must be (N, 3) or (U, V, 3)")

    pts = _flatten(points).astype(np.float64)
    nms = _flatten(normals).astype(np.float64)

    if pts.shape[0] < 15 or nms.shape[0] < 15:
        return False

    nms = nms / (np.linalg.norm(nms, axis=1, keepdims=True) + 1e-12)

    # -------------------------------------------------
    # Step 1: 确定性地估计法向轴向（无随机）
    # -------------------------------------------------
    # 方法：对法向做 PCA，最小方差方向即为法向圆锥的轴向
    # 因为法向分布在以 a 为轴的圆锥面上，其协方差在 a 方向最集中
    nm_centroid = np.mean(nms, axis=0)
    cov = np.cov(nms.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # 最大方差方向不一定对，但**最小方差方向通常是旋转对称轴**
    a_candidate1 = eigvecs[:, np.argmin(eigvals)]  # 最小方差方向
    a_candidate2 = eigvecs[:, np.argmax(eigvals)]  # 最大方差方向（备用）

    candidate_axes = [a_candidate1, -a_candidate1, a_candidate2, -a_candidate2]

    best_result = {
        'inlier_ratio': 0.0,
        'std_dot': np.inf,
        'sin_rel_error': np.inf
    }

    centroid = np.mean(pts, axis=0)

    for a_n in candidate_axes:
        a_n = a_n / (np.linalg.norm(a_n) + 1e-12)

        # --- 从该 a_n 估计 theta from normals ---
        dot_abs = np.abs(nms @ a_n)
        mean_dot = np.mean(dot_abs)
        std_dot = np.std(dot_abs)
        if std_dot > 0.25:  # 法向太分散，跳过
            continue
        theta_from_normal = np.arcsin(np.clip(mean_dot, 0.0, 1.0))
        if not (1e-3 < theta_from_normal < np.pi / 2 - 1e-3):
            continue

        # --- 用此 a_n 拟合点云 ---
        proj = (pts - centroid) @ a_n
        d_min, d_max = proj.min(), proj.max()
        d_range = d_max - d_min
        if d_range < 1e-6:
            continue

        # 尝试更广的顶点范围：从 -3*d_range 到 +3*d_range
        V_trials = []
        for factor in np.linspace(-6.0, 6.0, 14):  # -3, -2, ..., 3
            V0 = centroid + factor * d_range * a_n
            V_trials.append(V0)

        for V0 in V_trials:
            d0 = pts - V0
            d_norm0 = np.linalg.norm(d0, axis=1)
            valid0 = d_norm0 > 1e-6
            if not np.any(valid0):
                continue
            cos_vals = np.abs((d0[valid0] @ a_n) / d_norm0[valid0])
            cos_vals = np.clip(cos_vals, 0.0, 1.0)
            theta0 = np.arccos(cos_vals.mean())
            theta0 = np.clip(theta0, 1e-3, np.pi / 2 - 1e-3)

            # 固定 a = a_n，优化 V 和 theta
            def residuals(params):
                V = params[0:3]
                theta = params[3]
                theta = np.clip(theta, 1e-3, np.pi / 2 - 1e-3)
                d = pts - V
                d_norm = np.linalg.norm(d, axis=1)
                res = np.ones(len(pts))
                valid = d_norm > 1e-6
                if np.any(valid):
                    cos_angle = np.abs((d[valid] @ a_n) / d_norm[valid])
                    target_cos = np.cos(theta)
                    res[valid] = cos_angle - target_cos
                return res

            try:
                p0 = np.hstack([V0, theta0])
                res = least_squares(
                    residuals, p0,
                    method='trf',
                    max_nfev=max_opt_iter,
                    xtol=1e-6, ftol=1e-6,
                    verbose=0
                )
                if not res.success:
                    continue

                final_res = residuals(res.x)
                cos_tol = 1.0 - np.cos(np.radians(angle_tol_deg))
                inliers = np.abs(final_res) < cos_tol
                inlier_ratio = np.mean(inliers)

                if inlier_ratio < 0.3:
                    continue

                # 验证法向一致性
                theta_opt = np.clip(res.x[3], 1e-3, np.pi / 2 - 1e-3)
                expected_sin = np.sin(theta_opt)
                sin_rel_error = np.abs(mean_dot - expected_sin) / (expected_sin + 1e-3)

                # 更新最佳结果
                if inlier_ratio > best_result['inlier_ratio']:
                    best_result.update({
                        'inlier_ratio': inlier_ratio,
                        'std_dot': std_dot,
                        'sin_rel_error': sin_rel_error
                    })

            except Exception:
                continue

    # -------------------------------------------------
    # Final decision
    # -------------------------------------------------
    if (
            best_result['inlier_ratio'] >= min_point_inlier_ratio and
            best_result['std_dot'] < normal_std_tol and
            best_result['sin_rel_error'] < 0.35
    ):
        return True

    return False

def is_bspline_fit_cone_by_points_and_normals_v1(
    points: np.ndarray,
    normals: np.ndarray,
    angle_tol_deg: float = 8.0,          # 放宽角度容忍度
    normal_std_tol: float = 0.1,         # |n·a| 的标准差容忍度
    min_point_inlier_ratio: float = 0.6, # 降低内点比例要求
    max_opt_iter: int = 200
) -> bool:
    """
    稳定版：判定是否为圆锥面（points 与 normals 无需对应）
    修复：消除随机性、双向轴向、扩大顶点搜索、fallback 机制
    """

    def _flatten(arr):
        if arr.ndim == 3:
            return arr.reshape(-1, 3)
        elif arr.ndim == 2 and arr.shape[1] == 3:
            return arr
        else:
            raise ValueError("Input must be (N, 3) or (U, V, 3)")

    pts = _flatten(points).astype(np.float64)
    nms = _flatten(normals).astype(np.float64)

    if pts.shape[0] < 15 or nms.shape[0] < 15:
        return False

    nms = nms / (np.linalg.norm(nms, axis=1, keepdims=True) + 1e-12)

    # -------------------------------------------------
    # Step 1: 确定性地估计法向轴向（无随机）
    # -------------------------------------------------
    # 方法：对法向做 PCA，最小方差方向即为法向圆锥的轴向
    # 因为法向分布在以 a 为轴的圆锥面上，其协方差在 a 方向最集中
    nm_centroid = np.mean(nms, axis=0)
    cov = np.cov(nms.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # 最大方差方向不一定对，但**最小方差方向通常是旋转对称轴**
    candidate_axes = []
    for i in range(3):
        a = eigvecs[:, i]
        candidate_axes.extend([a, -a])

    best_result = {
        'inlier_ratio': 0.0,
        'std_dot': np.inf,
        'sin_rel_error': np.inf
    }

    centroid = np.mean(pts, axis=0)

    for a_n in candidate_axes:
        a_n = a_n / (np.linalg.norm(a_n) + 1e-12)

        # --- 从该 a_n 估计 theta from normals ---
        dot_abs = np.abs(nms @ a_n)
        mean_dot = np.mean(dot_abs)
        std_dot = np.std(dot_abs)
        # >>> 修改：放宽标准差容忍度 <<<
        if std_dot > 0.3:  # 原为 0.25
            continue
        theta_from_normal = np.arcsin(np.clip(mean_dot, 0.0, 1.0))
        if not (1e-3 < theta_from_normal < np.pi / 2 - 1e-3):
            continue

        # --- 用此 a_n 拟合点云 ---
        proj = (pts - centroid) @ a_n
        d_min, d_max = proj.min(), proj.max()
        d_range = d_max - d_min
        if d_range < 1e-6:
            continue

        # 尝试更广的顶点范围：从 -3*d_range 到 +3*d_range
        V_trials = []
        for factor in np.linspace(-6.0, 6.0, 25):  # 原为 14
            V0 = centroid + factor * d_range * a_n
            V_trials.append(V0)

        for V0 in V_trials:
            d0 = pts - V0
            d_norm0 = np.linalg.norm(d0, axis=1)
            valid0 = d_norm0 > 1e-6
            if not np.any(valid0):
                continue
            cos_vals = np.abs((d0[valid0] @ a_n) / d_norm0[valid0])
            cos_vals = np.clip(cos_vals, 0.0, 1.0)
            theta0 = np.arccos(cos_vals.mean())
            theta0 = np.clip(theta0, 1e-3, np.pi / 2 - 1e-3)

            # 固定 a = a_n，优化 V 和 theta
            def residuals(params):
                V = params[0:3]
                theta = params[3]
                theta = np.clip(theta, 1e-3, np.pi / 2 - 1e-3)
                d = pts - V
                d_norm = np.linalg.norm(d, axis=1)
                res = np.ones(len(pts))
                valid = d_norm > 1e-6
                if np.any(valid):
                    cos_angle = np.abs((d[valid] @ a_n) / d_norm[valid])
                    target_cos = np.cos(theta)
                    res[valid] = cos_angle - target_cos
                return res

            try:
                p0 = np.hstack([V0, theta0])
                res = least_squares(
                    residuals, p0,
                    method='trf',
                    max_nfev=max_opt_iter,
                    xtol=1e-6, ftol=1e-6,
                    verbose=0
                )
                if not res.success:
                    continue

                final_res = residuals(res.x)
                cos_tol = 1.0 - np.cos(np.radians(angle_tol_deg))
                inliers = np.abs(final_res) < cos_tol
                inlier_ratio = np.mean(inliers)

                if inlier_ratio < 0.3:
                    continue

                # 验证法向一致性
                theta_opt = np.clip(res.x[3], 1e-3, np.pi / 2 - 1e-3)
                expected_sin = np.sin(theta_opt)
                sin_rel_error = np.abs(mean_dot - expected_sin) / (expected_sin + 1e-3)

                # 更新最佳结果
                if inlier_ratio > best_result['inlier_ratio']:
                    best_result.update({
                        'inlier_ratio': inlier_ratio,
                        'std_dot': std_dot,
                        'sin_rel_error': sin_rel_error
                    })

            except Exception:
                continue

    # -------------------------------------------------
    # Final decision
    # -------------------------------------------------
    if (
            best_result['inlier_ratio'] >= min_point_inlier_ratio and
            best_result['std_dot'] < normal_std_tol and
            best_result['sin_rel_error'] < 0.35
    ):
        return True

    return False
