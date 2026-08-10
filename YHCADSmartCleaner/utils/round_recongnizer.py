import numpy as np
from sklearn.decomposition import PCA
from scipy.spatial import cKDTree
from typing import Tuple, Optional, Dict


def normalize(v: np.ndarray) -> np.ndarray:
    """归一化向量或向量数组"""
    if v.ndim == 1:
        return v / (np.linalg.norm(v) + 1e-12)
    else:
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)


def extract_spine_direction_from_normals(
        normals: np.ndarray,
        method: str = 'pca'
) -> Tuple[np.ndarray, Dict]:
    """
    从倒圆角面的法向量集合中提取脊线方向

    几何原理：
    - 倒圆角面上的所有法向量都垂直于脊线
    - 因此法向量都位于一个平面内（该平面的法向 = 脊线方向）
    - 通过PCA，最小方差方向即为脊线方向

    Args:
        normals: [M, 3] 法向量集合（来自倒圆角面，但与输入点不对应）
        method: 'pca' 或 'svd'

    Returns:
        spine_direction: 脊线方向（单位向量）
        info: 详细信息
    """
    if normals.shape[0] < 10:
        raise ValueError("Not enough normals for PCA")

    # 归一化法向量
    normals = normalize(normals)

    # 检查法向量是否全部相同（方差为零）
    if np.allclose(normals, normals[0]):
        # 所有法向量相同，任意垂直方向都可以作为脊线方向
        # 生成一个与法向量垂直的向量
        if np.abs(normals[0][0]) < 0.9:
            spine_direction = normalize(np.array([1.0, 0.0, 0.0]) - normals[0][0] * normals[0])
        else:
            spine_direction = normalize(np.array([0.0, 1.0, 0.0]) - normals[0][1] * normals[0])
        
        info = {
            'method': method,
            'n_normals': normals.shape[0],
            'warning': 'All normals are the same, using arbitrary perpendicular direction as spine',
            'explained_variance': np.array([0.0, 0.0, 0.0]),
            'explained_variance_ratio': np.array([0.0, 0.0, 0.0]),
            'components': np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], spine_direction]),
            'variance_ratio_3rd': 0.0
        }
        return spine_direction, info

    info = {
        'method': method,
        'n_normals': normals.shape[0]
    }

    if method == 'pca':
        # PCA 分析
        pca = PCA(n_components=3)
        pca.fit(normals)

        # 主成分：最大方差方向 -> 法向量分布的主要方向
        # 最小方差方向 -> 法向量分布平面的法向 = 脊线方向
        components = pca.components_  # [3, 3] 每行是一个主成分
        explained_variance = pca.explained_variance_

        # 最小方差方向（第三主成分）
        spine_direction = normalize(components[2, :])

        # 计算总方差并处理可能的零方差情况
        total_var = np.sum(explained_variance)
        if total_var > 0:
            explained_variance_ratio = explained_variance / total_var
        else:
            explained_variance_ratio = np.zeros_like(explained_variance)

        info.update({
            'explained_variance': explained_variance,
            'explained_variance_ratio': explained_variance_ratio,
            'components': components
        })

        # 验证：法向量应该主要分布在前两个主成分平面内
        # 即第三个主成分的方差应该很小
        variance_ratio_3rd = explained_variance_ratio[2]
        info['variance_ratio_3rd'] = variance_ratio_3rd

        if variance_ratio_3rd > 0.1:
            # 警告：法向量分布可能不是平面，可能不是倒圆角面
            info['warning'] = f'3rd component variance ratio is high: {variance_ratio_3rd:.3f}'

    elif method == 'svd':
        # SVD 方法（等价于PCA）
        centroid = np.mean(normals, axis=0)
        centered = normals - centroid
        _, _, vh = np.linalg.svd(centered)

        # 最后一行对应最小奇异值的方向
        spine_direction = normalize(vh[-1, :])

        info.update({
            'sv_singular_values': _
        })

    return spine_direction, info


def validate_normals_planarity(
        normals: np.ndarray,
        tol: float = 0.1
) -> Tuple[bool, Dict]:
    """
    验证法向量是否共面（倒圆角面的必要条件）

    原理：计算法向量集合的"平面度"
    - 如果法向量共面，则它们到最佳拟合平面的距离应该很小

    Args:
        normals: [M, 3] 法向量
        tol: 平面度容差（平均距离）

    Returns:
        is_planar: 是否共面
        planarity_info: 平面度详细信息
    """
    if normals.shape[0] < 10:
        return False, {
            'avg_distance': np.inf,
            'max_distance': np.inf,
            'planarity_score': np.inf,
            'is_planar': False
        }

    normals = normalize(normals)

    # 检查法向量是否全部相同（方差为零）
    if np.allclose(normals, normals[0]):
        return True, {
            'avg_distance': 0.0,
            'max_distance': 0.0,
            'planarity_score': 0.0,
            'is_planar': True
        }

    # PCA 找最佳拟合平面
    pca = PCA(n_components=3)
    pca.fit(normals)

    # 法向量到拟合平面的距离 = 在第三主成分上的投影
    components = pca.components_
    distances = np.abs(normals @ components[2, :])

    avg_distance = np.mean(distances)
    max_distance = np.max(distances)
    std_distance = np.std(distances)

    # 计算平面度分数：考虑平均距离和标准差
    planarity_score = avg_distance + std_distance

    # 检查PCA方差比例，第三主成分的方差应该很小
    explained_variance = pca.explained_variance_
    total_var = np.sum(explained_variance)
    if total_var > 0:
        variance_ratio_3rd = explained_variance[2] / total_var
    else:
        variance_ratio_3rd = 0.0

    # 综合判断：平面度分数和方差比例
    is_planar = (avg_distance < tol) and (variance_ratio_3rd < 0.1)

    return is_planar, {
        'avg_distance': avg_distance,
        'max_distance': max_distance,
        'std_distance': std_distance,
        'planarity_score': planarity_score,
        'variance_ratio_3rd': variance_ratio_3rd,
        'is_planar': is_planar
    }


def slice_point_cloud_along_direction(
        points: np.ndarray,
        direction: np.ndarray,
        n_slices: int = 10
) -> Tuple[list, np.ndarray]:
    """
    沿指定方向将点云切片

    Args:
        points: [N, 3] 点云
        direction: 切片方向（脊线方向）
        n_slices: 切片数量

    Returns:
        slices: 每个切片的点索引列表
        slice_positions: 每个切片沿方向的位置
    """
    # 投影到方向轴上
    proj = points @ direction

    # 确定切片边界
    min_proj, max_proj = proj.min(), proj.max()
    slice_edges = np.linspace(min_proj, max_proj, n_slices + 1)

    slices = []
    slice_positions = []

    for i in range(n_slices):
        if i < n_slices - 1:
            mask = (proj >= slice_edges[i]) & (proj < slice_edges[i + 1])
        else:
            mask = (proj >= slice_edges[i]) & (proj <= slice_edges[i + 1])
        indices = np.where(mask)[0]

        if len(indices) > 0:
            slices.append(indices)
            slice_positions.append((slice_edges[i] + slice_edges[i + 1]) / 2)

    return slices, np.array(slice_positions)


def fit_circle_2d(points_2d: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """
    拟合2D圆（代数法）

    Args:
        points_2d: [N, 2] 2D点

    Returns:
        center: 圆心 [2]
        radius: 半径
        rms_error: 拟合的RMS误差
    """
    if points_2d.shape[0] < 3:
        return np.zeros(2), 0.0, np.inf

    x, y = points_2d[:, 0], points_2d[:, 1]

    # 构建方程组：x^2 + y^2 + Ax + By + C = 0
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x ** 2 + y ** 2)

    try:
        # 最小二乘解
        coeffs, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        A_, B_, C_ = coeffs

        # 圆心和半径
        center_x = -A_ / 2
        center_y = -B_ / 2
        radius = np.sqrt(center_x ** 2 + center_y ** 2 - C_)

        center = np.array([center_x, center_y])

        # 计算RMS误差
        distances = np.linalg.norm(points_2d - center, axis=1)
        residuals = distances - radius
        rms_error = np.sqrt(np.mean(residuals ** 2))

        return center, radius, rms_error

    except np.linalg.LinAlgError:
        return np.zeros(2), 0.0, np.inf


def fit_circle_3d(points_3d: np.ndarray) -> Tuple[np.ndarray, float, float, np.ndarray, Dict]:
    """
    拟合3D空间中的圆

    步骤：
    1. 对点云做PCA，找到最佳拟合平面
    2. 将点投影到该平面
    3. 在2D平面内拟合圆

    Args:
        points_3d: [N, 3] 3D点

    Returns:
        center_3d: 3D圆心
        radius: 半径
        rms_error: RMS拟合误差
        plane_normal: 圆所在平面的法向
        fit_info: 拟合详细信息
    """
    fit_info = {
        'success': False,
        'n_points': points_3d.shape[0],
        'plane_fit_quality': 0.0,
        'circle_fit_quality': 0.0,
        'inlier_ratio': 0.0
    }

    if points_3d.shape[0] < 3:
        return np.zeros(3), 0.0, np.inf, np.zeros(3), fit_info

    # PCA 找最佳拟合平面
    centroid = np.mean(points_3d, axis=0)
    centered = points_3d - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)

    # 计算平面拟合质量：最小特征值与最大特征值的比值
    if eigvals[-1] > 0:
        plane_fit_quality = eigvals[0] / eigvals[-1]
        fit_info['plane_fit_quality'] = plane_fit_quality

    # 最小特征值对应的特征向量是平面法向
    plane_normal = normalize(eigvecs[:, 0])

    # 将点投影到平面（需要两个正交基向量）
    u = normalize(eigvecs[:, 1])  # 第一主方向
    v = normalize(eigvecs[:, 2])  # 第二主方向

    # 2D坐标
    points_2d = np.column_stack([
        centered @ u,
        centered @ v
    ])

    # 拟合2D圆
    center_2d, radius, rms_error = fit_circle_2d(points_2d)

    # 计算圆拟合质量：相对误差
    if radius > 1e-6:
        rel_error = rms_error / radius
        fit_info['circle_fit_quality'] = 1.0 - rel_error if rel_error < 1.0 else 0.0

    # 计算内点比例：距离圆心在半径±10%范围内的点
    if radius > 1e-6:
        distances = np.linalg.norm(points_2d - center_2d, axis=1)
        inliers = np.abs(distances - radius) < 0.1 * radius
        inlier_ratio = np.mean(inliers)
        fit_info['inlier_ratio'] = inlier_ratio

    # 转回3D
    center_3d = centroid + center_2d[0] * u + center_2d[1] * v

    fit_info['success'] = (radius > 0) and (rms_error < radius * 0.1)

    return center_3d, radius, rms_error, plane_normal, fit_info


def is_constant_radius_fillet_by_points_and_normals(
        points: np.ndarray,
        normals: np.ndarray,
        n_slices: int = 10,
        min_points_per_slice: int = 8,
        radius_tol: float = 0.2,  # 半径相对容差（变异系数）
        circle_fit_tol: float = 0.05,  # 圆拟合相对误差容差
        min_inlier_slices: float = 0.7,  # 最少多少比例的切片需要是好的圆
        planarity_tol: float = 0.2,  # 法向量共面性容差
        spine_method: str = 'pca',
        min_radius: float = 2.5,  # 最小圆角半径
        max_radius: float = 18.0,  # 最大圆角半径
        center_traj_straightness_tol: float = 0.1,  # 圆心轨迹直线度容差
        min_points: int = 40,  # 最小点数量
        min_normals: int = 40,  # 最小法向量数量
        aspect_ratio_tol: float = 0.5,  # 长宽比容差
        spine_variance_tol: float = 0.05,  # 脊线方向可靠性容差
        min_arc_span: float = 1.5708  # 最小圆弧覆盖度（弧度，默认π/2≈90°）
) -> Tuple[bool, Dict]:
    """
    判定是否为恒等半径倒圆角面

    输入：
        points: [N, 3] 倒圆角面上的采样点坐标
        normals: [M, 3] 倒圆角面上的法向量（来自不同的采样点，与points不对应）

    输出：
        is_fillet: 是否为恒等半径倒圆角
        info: 详细信息字典
    """
    info = {
        'success': False,
        'spine_direction': None,
        'spine_method': spine_method,
        'planarity_check': None,
        'radii': [],
        'rms_errors': [],
        'centers': [],
        'radius_mean': None,
        'radius_std': None,
        'radius_cv': None,  # 变异系数
        'inlier_slice_ratio': 0.0,
        'avg_rms_error': None,
        'center_traj_straightness': None,
        'failure_reason': None
    }

    # 检查输入点数量
    if points.shape[0] < min_points:
        info['failure_reason'] = f'Too few points: {points.shape[0]}'
        return False, info

    if normals.shape[0] < min_normals:
        info['failure_reason'] = f'Too few normals: {normals.shape[0]}'
        return False, info

    # ========== Step 1+2: PCA 一次计算，同时用于共面性检查和脊线提取 ==========
    normals_normed = normalize(normals)

    if np.allclose(normals_normed, normals_normed[0]):
        info['failure_reason'] = 'All normals are the same, not a fillet surface'
        return False, info

    pca = PCA(n_components=3)
    pca.fit(normals_normed)
    pca_components = pca.components_
    pca_explained_var = pca.explained_variance_
    pca_total_var = np.sum(pca_explained_var)
    pca_var_ratio = pca_explained_var / pca_total_var if pca_total_var > 0 else np.zeros(3)
    variance_ratio_3rd = pca_var_ratio[2]

    # Step 1: 共面性检查
    distances_to_plane = np.abs(normals_normed @ pca_components[2, :])
    avg_distance = np.mean(distances_to_plane)
    std_distance = np.std(distances_to_plane)
    planarity_score = avg_distance + std_distance

    is_planar = (avg_distance < planarity_tol) and (variance_ratio_3rd < 0.1)

    info['planarity_check'] = {
        'avg_distance': avg_distance,
        'max_distance': np.max(distances_to_plane),
        'std_distance': std_distance,
        'planarity_score': planarity_score,
        'variance_ratio_3rd': variance_ratio_3rd,
        'is_planar': is_planar
    }

    if not is_planar:
        info['failure_reason'] = (
            f'Normals are not planar (avg distance={avg_distance:.4f} > {planarity_tol})'
        )
        return False, info

    # Step 2: 脊线方向 = PCA 最小方差方向
    spine_direction = normalize(pca_components[2, :])
    info['spine_direction'] = spine_direction
    info['method'] = spine_method
    info['n_normals'] = normals.shape[0]
    info['explained_variance'] = pca_explained_var
    info['explained_variance_ratio'] = pca_var_ratio
    info['components'] = pca_components
    info['variance_ratio_3rd'] = variance_ratio_3rd

    if variance_ratio_3rd > spine_variance_tol:
        info['failure_reason'] = f'Spine direction not reliable (3rd variance ratio={variance_ratio_3rd:.4f} > {spine_variance_tol})'
        return False, info

    # ========== Step 3: 沿脊线方向切片 ==========
    slices, slice_positions = slice_point_cloud_along_direction(
        points,
        spine_direction,
        n_slices=n_slices
    )

    if len(slices) < max(2, int(n_slices * 0.6)):
        info['failure_reason'] = f'Too few slices: {len(slices)}'
        return False, info

    # ========== Step 4: 对每个切片拟合圆 ==========
    radii = []
    rms_errors = []
    centers = []
    good_slices = 0

    for idx, slice_indices in enumerate(slices):
        if len(slice_indices) < min_points_per_slice:
            continue

        slice_points = points[slice_indices]

        # 拟合3D圆
        center, radius, rms_error, plane_normal, fit_info = fit_circle_3d(slice_points)

        if radius < min_radius or radius > max_radius:
            continue

        # 检查圆弧覆盖度：防止小弧段误判为圆角
        centered_slice = slice_points - center
        ref = np.array([1.0, 0.0, 0.0])
        if np.abs(np.dot(plane_normal, ref)) > 0.9:
            ref = np.array([0.0, 1.0, 0.0])
        u = normalize(np.cross(plane_normal, ref))
        v = np.cross(plane_normal, u)

        proj_u = centered_slice @ u
        proj_v = centered_slice @ v
        angles = np.arctan2(proj_v, proj_u)
        angles_sorted = np.sort(angles)
        gaps = np.diff(angles_sorted)
        gaps = np.append(gaps, 2 * np.pi + angles_sorted[0] - angles_sorted[-1])
        max_gap = np.max(gaps)
        arc_span = 2 * np.pi - max_gap

        if arc_span < min_arc_span:
            continue

        # 检查圆拟合质量
        rel_error = rms_error / radius if radius > 1e-6 else np.inf

        # 综合评估拟合质量：相对误差 + 内点比例 + 平面拟合质量
        if (rel_error < circle_fit_tol and 
            fit_info['inlier_ratio'] > 0.7 and 
            fit_info['plane_fit_quality'] < 0.1):
            radii.append(radius)
            rms_errors.append(rms_error)
            centers.append(center)
            good_slices += 1

    if len(radii) < max(2, int(n_slices * min_inlier_slices)):
        info['failure_reason'] = f'Too few good circle fits: {len(radii)}'
        return False, info

    radii = np.array(radii)
    rms_errors = np.array(rms_errors)
    centers = np.array(centers)

    info['radii'] = radii
    info['rms_errors'] = rms_errors
    info['centers'] = centers
    info['inlier_slice_ratio'] = good_slices / len(slices)

    # ========== Step 5: 检查半径一致性 ==========
    radius_mean = np.mean(radii)
    radius_std = np.std(radii)
    radius_cv = radius_std / radius_mean if radius_mean > 1e-6 else np.inf  # 变异系数

    info['radius_mean'] = radius_mean
    info['radius_std'] = radius_std
    info['radius_cv'] = radius_cv
    info['avg_rms_error'] = np.mean(rms_errors)

    if radius_cv >= radius_tol:
        info['failure_reason'] = f'Radius inconsistency: CV={radius_cv:.4f} > {radius_tol}'
        return False, info

    # ========== Step 6: 检查圆心轨迹是否为直线 ==========
    if len(centers) >= 3:
        # 对圆心进行PCA，检查是否近似直线
        centroid_c = np.mean(centers, axis=0)
        centered_c = centers - centroid_c
        cov_c = np.cov(centered_c.T)
        eigvals_c, _ = np.linalg.eigh(cov_c)
        
        # 计算直线度：最小特征值与最大特征值的比值
        if eigvals_c[-1] > 1e-6:
            straightness_ratio = eigvals_c[0] / eigvals_c[-1]
            info['center_traj_straightness'] = straightness_ratio
            
            if straightness_ratio > center_traj_straightness_tol:
                info['failure_reason'] = f'Center trajectory not straight enough (ratio={straightness_ratio:.4f} > {center_traj_straightness_tol})'
                return False, info

    # ========== Step 7: 检查点云形状是否符合圆角特征 ==========
    # 计算点云的长宽比
    point_centroid = np.mean(points, axis=0)
    point_cov = np.cov((points - point_centroid).T)
    point_eigvals, _ = np.linalg.eigh(point_cov)
    point_eigvals = np.sort(point_eigvals)[::-1]
    
    if point_eigvals[0] > 0:
        aspect_ratio = point_eigvals[1] / point_eigvals[0]
        # 圆角面通常是细长的，长宽比应该较小
        if aspect_ratio > aspect_ratio_tol:
            info['failure_reason'] = f'Point cloud not elongated enough (aspect ratio={aspect_ratio:.4f} > {aspect_ratio_tol})'
            return False, info

    # 所有检查都通过
    info['success'] = True
    return True, info


# ========== 辅助可视化函数 ==========

def visualize_fillet_detection(
        points: np.ndarray,
        normals: np.ndarray,
        result_info: Dict,
        show: bool = True,
        figsize: Tuple[int, int] = (18, 12),
        planarity_tol: float = 0.1
):
    """
    可视化检测结果（需要安装 matplotlib）
    """
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D

        fig = plt.figure(figsize=figsize)

        # ========== 子图1: 法向量在单位球面上的分布 ==========
        ax1 = fig.add_subplot(231, projection='3d')

        # 绘制单位球面
        u = np.linspace(0, 2 * np.pi, 50)
        v = np.linspace(0, np.pi, 25)
        x = np.outer(np.cos(u), np.sin(v))
        y = np.outer(np.sin(u), np.sin(v))
        z = np.outer(np.ones_like(u), np.cos(v))
        ax1.plot_surface(x, y, z, color='lightgray', alpha=0.1, linewidth=0)

        # 绘制法向量（从原点出发）
        normals_norm = normalize(normals)
        ax1.quiver(np.zeros_like(normals_norm[:, 0]),
                   np.zeros_like(normals_norm[:, 1]),
                   np.zeros_like(normals_norm[:, 2]),
                   normals_norm[:, 0], normals_norm[:, 1], normals_norm[:, 2],
                   length=1.0, color='b', alpha=0.5, arrow_length_ratio=0.1)

        # 绘制PCA主成分
        if 'components' in result_info:
            components = result_info['components']
            colors = ['r', 'g', 'm']
            labels = ['PC1 (max variance)', 'PC2', 'PC3 (spine direction)']

            for i in range(3):
                ax1.quiver(0, 0, 0,
                           components[i, 0], components[i, 1], components[i, 2],
                           length=1.2, color=colors[i], linewidth=2,
                           label=labels[i], arrow_length_ratio=0.1)

        ax1.set_title('Normals Distribution on Unit Sphere')
        ax1.set_xlabel('X')
        ax1.set_ylabel('Y')
        ax1.set_zlabel('Z')
        ax1.legend()
        ax1.set_box_aspect([1, 1, 1])
        ax1.set_xlim([-1.5, 1.5])
        ax1.set_ylim([-1.5, 1.5])
        ax1.set_zlim([-1.5, 1.5])

        # ========== 子图2: 法向量投影到主平面 ==========
        ax2 = fig.add_subplot(232)

        if 'components' in result_info:
            components = result_info['components']
            # 将法向量投影到前两个主成分平面
            proj_2d = normals_norm @ components[:2, :].T

            ax2.scatter(proj_2d[:, 0], proj_2d[:, 1], alpha=0.5, s=10)

            # 绘制单位圆
            theta = np.linspace(0, 2 * np.pi, 100)
            ax2.plot(np.cos(theta), np.sin(theta), 'r--', linewidth=1, label='Unit Circle')

            ax2.set_title('Normals Projected to PC1-PC2 Plane')
            ax2.set_xlabel('PC1')
            ax2.set_ylabel('PC2')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            ax2.set_aspect('equal')
            ax2.set_xlim([-1.2, 1.2])
            ax2.set_ylim([-1.2, 1.2])

        # ========== 子图3: 点云 + 脊线方向 ==========
        ax3 = fig.add_subplot(233, projection='3d')

        ax3.scatter(points[:, 0], points[:, 1], points[:, 2],
                    s=10, alpha=0.3, label='Points')

        if result_info['spine_direction'] is not None:
            spine = result_info['spine_direction']
            centroid = np.mean(points, axis=0)
            ax3.quiver(centroid[0], centroid[1], centroid[2],
                       spine[0], spine[1], spine[2],
                       length=2.0, color='r', linewidth=2, label='Spine Direction')

        ax3.set_title('Point Cloud + Spine Direction')
        ax3.legend()
        ax3.set_xlabel('X')
        ax3.set_ylabel('Y')
        ax3.set_zlabel('Z')
        ax3.set_box_aspect([1, 1, 1])

        # ========== 子图4: 半径分布 ==========
        ax4 = fig.add_subplot(234)

        if len(result_info['radii']) > 0:
            radii = result_info['radii']
            x_vals = np.arange(len(radii))

            ax4.plot(x_vals, radii, 'o-', label='Radius per slice', linewidth=2, markersize=6)
            ax4.axhline(np.mean(radii), color='r', linestyle='--',
                        label=f'Mean: {np.mean(radii):.3f}', linewidth=2)
            ax4.fill_between(x_vals,
                             np.mean(radii) - np.std(radii),
                             np.mean(radii) + np.std(radii),
                             alpha=0.3, color='r', label='±1σ')

            ax4.set_title(f'Radius Distribution\nCV: {result_info["radius_cv"]:.4f}')
            ax4.set_xlabel('Slice Index')
            ax4.set_ylabel('Radius')
            ax4.legend()
            ax4.grid(True, alpha=0.3)

        # ========== 子图5: 圆心轨迹 ==========
        ax5 = fig.add_subplot(235, projection='3d')

        ax5.scatter(points[:, 0], points[:, 1], points[:, 2],
                    s=5, alpha=0.2, label='Points')

        if len(result_info['centers']) > 0:
            centers = np.array(result_info['centers'])
            ax5.scatter(centers[:, 0], centers[:, 1], centers[:, 2],
                        s=80, c='r', marker='x', linewidth=2, label='Circle Centers')

            # 拟合圆心轨迹直线
            if len(centers) >= 2:
                centroid_c = np.mean(centers, axis=0)
                cov_c = np.cov((centers - centroid_c).T)
                eigvals_c, eigvecs_c = np.linalg.eigh(cov_c)
                direction_c = eigvecs_c[:, np.argmax(eigvals_c)]

                t = np.linspace(-1, 1, 10)
                line_pts = centroid_c + np.outer(t, direction_c)
                ax5.plot(line_pts[:, 0], line_pts[:, 1], line_pts[:, 2],
                         'g-', linewidth=2, label='Center Trajectory')

        ax5.set_title('Circle Centers Trajectory')
        ax5.legend()
        ax5.set_xlabel('X')
        ax5.set_ylabel('Y')
        ax5.set_zlabel('Z')
        ax5.set_box_aspect([1, 1, 1])

        # ========== 子图6: 平面度分析 ==========
        ax6 = fig.add_subplot(236)

        if result_info['planarity_check'] is not None:
            planarity = result_info['planarity_check']

            # 计算每个法向量到拟合平面的距离
            if 'components' in result_info:
                components = result_info['components']
                distances = np.abs(normals_norm @ components[2, :])

                ax6.hist(distances, bins=20, alpha=0.7, color='blue', edgecolor='black')
                ax6.axvline(planarity['avg_distance'], color='r', linestyle='--',
                            label=f'Avg: {planarity["avg_distance"]:.4f}')
                ax6.axvline(planarity_tol, color='g', linestyle='--',
                            label=f'Tolerance: {planarity_tol}')

                ax6.set_title('Normals Distance to Best-fit Plane')
                ax6.set_xlabel('Distance')
                ax6.set_ylabel('Count')
                ax6.legend()
                ax6.grid(True, alpha=0.3)

        plt.tight_layout()

        if show:
            plt.show()

        return fig

    except ImportError:
        print("Matplotlib not available, skipping visualization")
        return None