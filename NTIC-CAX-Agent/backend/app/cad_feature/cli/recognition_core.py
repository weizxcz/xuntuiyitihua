"""cad_feature 几何识别核心（自包含，无 YHCADSmartCleaner 依赖）。

从 YHCADSmartCleaner 的 ``utils/sampler.py`` 与 ``utils/round_recongnizer.py``
内化而来，仅依赖 ``numpy`` / ``sklearn``（运行于装了 NCTI SDK 的
wygcleaner 环境，由 ``recognition_cli.py`` 在独立子进程内调用；依赖清单见同目录
``requirements.txt``）。

设计原则：
  - 所有函数输入都是普通 ``numpy`` 数组 / NCTI 文档对象，不 import 任何
    YHCADSmartCleaner 内部模块，独立仓库可直接使用。
  - ``scipy`` / ``sklearn`` 在函数内 lazy import，降低顶层依赖面。
  - 仅暴露识别链路真正用到的 ``get_face_sample`` 与
    ``is_constant_radius_fillet_by_points_and_normals``（含其几何辅助）。
"""
from __future__ import annotations

import numpy as np

SAMPLE_NUMBER = 100


# ---------------------------------------------------------------------------
# 面采样（源自 utils/sampler.py）
# ---------------------------------------------------------------------------
def get_face_sample(doc, obj_name_list, cell_id_list, seed: int = 42):
    """从指定 CAD 模型面中采样点和法线。

    Args:
        doc: NCTI 文档对象（提供 GetFacePointFromUV / GetNormalByUV）。
        obj_name_list: 对象名称列表。
        cell_id_list: 面 ID 列表。
        seed: 随机种子，默认 42，保证结果可复现。

    Returns:
        tuple: (points, normals) —— 每个面的采样点集和法线集。
    """
    points = []
    normals = []
    rng = np.random.RandomState(seed)

    for index, cell_id in enumerate(cell_id_list):
        points_in_face = []
        normals_in_face = []

        uv_list = rng.rand(SAMPLE_NUMBER, 2)
        for uv in uv_list:
            pt = doc.GetFacePointFromUV(obj_name_list[index], cell_id, uv[0], uv[1])
            points_in_face.append([pt.X, pt.Y, pt.Z])

            vec = doc.GetNormalByUV(obj_name_list[index], cell_id, uv[0], uv[1])
            normals_in_face.append([vec.X, vec.Y, vec.Z])

        points.append(np.array(points_in_face))
        normals.append(np.array(normals_in_face))
    return points, normals


# ---------------------------------------------------------------------------
# 恒半径圆角判定（源自 utils/round_recongnizer.py）
# ---------------------------------------------------------------------------
def normalize(v: np.ndarray) -> np.ndarray:
    """归一化向量或向量数组。"""
    if v.ndim == 1:
        return v / (np.linalg.norm(v) + 1e-12)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)


def extract_spine_direction_from_normals(normals: np.ndarray, method: str = "pca"):
    """从倒圆角面的法向量集合中提取脊线方向。"""
    if normals.shape[0] < 10:
        raise ValueError("Not enough normals for PCA")

    normals = normalize(normals)
    if np.allclose(normals, normals[0]):
        if np.abs(normals[0][0]) < 0.9:
            spine_direction = normalize(np.array([1.0, 0.0, 0.0]) - normals[0][0] * normals[0])
        else:
            spine_direction = normalize(np.array([0.0, 1.0, 0.0]) - normals[0][1] * normals[0])
        info = {
            "method": method,
            "n_normals": normals.shape[0],
            "warning": "All normals are the same, using arbitrary perpendicular direction as spine",
            "explained_variance": np.array([0.0, 0.0, 0.0]),
            "explained_variance_ratio": np.array([0.0, 0.0, 0.0]),
            "components": np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], spine_direction]),
            "variance_ratio_3rd": 0.0,
        }
        return spine_direction, info

    info = {"method": method, "n_normals": normals.shape[0]}
    if method == "pca":
        from sklearn.decomposition import PCA

        pca = PCA(n_components=3)
        pca.fit(normals)
        components = pca.components_
        explained_variance = pca.explained_variance_
        spine_direction = normalize(components[2, :])
        total_var = np.sum(explained_variance)
        explained_variance_ratio = (
            explained_variance / total_var if total_var > 0 else np.zeros_like(explained_variance)
        )
        info.update({
            "explained_variance": explained_variance,
            "explained_variance_ratio": explained_variance_ratio,
            "components": components,
        })
        variance_ratio_3rd = explained_variance_ratio[2]
        info["variance_ratio_3rd"] = variance_ratio_3rd
        if variance_ratio_3rd > 0.1:
            info["warning"] = f"3rd component variance ratio is high: {variance_ratio_3rd:.3f}"
    elif method == "svd":
        centroid = np.mean(normals, axis=0)
        centered = normals - centroid
        _, _, vh = np.linalg.svd(centered)
        spine_direction = normalize(vh[-1, :])
        info.update({"sv_singular_values": _})
    return spine_direction, info


def validate_normals_planarity(normals: np.ndarray, tol: float = 0.1):
    """验证法向量是否共面（倒圆角面的必要条件）。"""
    if normals.shape[0] < 10:
        return False, {
            "avg_distance": np.inf, "max_distance": np.inf,
            "planarity_score": np.inf, "is_planar": False,
        }
    normals = normalize(normals)
    if np.allclose(normals, normals[0]):
        return True, {
            "avg_distance": 0.0, "max_distance": 0.0,
            "planarity_score": 0.0, "is_planar": True,
        }
    pca = PCA(n_components=3)
    pca.fit(normals)
    components = pca.components_
    distances = np.abs(normals @ components[2, :])
    avg_distance = np.mean(distances)
    max_distance = np.max(distances)
    std_distance = np.std(distances)
    planarity_score = avg_distance + std_distance
    explained_variance = pca.explained_variance_
    total_var = np.sum(explained_variance)
    variance_ratio_3rd = explained_variance[2] / total_var if total_var > 0 else 0.0
    is_planar = (avg_distance < tol) and (variance_ratio_3rd < 0.1)
    return is_planar, {
        "avg_distance": avg_distance, "max_distance": max_distance,
        "std_distance": std_distance, "planarity_score": planarity_score,
        "variance_ratio_3rd": variance_ratio_3rd, "is_planar": is_planar,
    }


def slice_point_cloud_along_direction(points: np.ndarray, direction: np.ndarray, n_slices: int = 10):
    """沿指定方向将点云切片。"""
    proj = points @ direction
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


def fit_circle_2d(points_2d: np.ndarray):
    """拟合 2D 圆（代数法）。"""
    if points_2d.shape[0] < 3:
        return np.zeros(2), 0.0, np.inf
    x, y = points_2d[:, 0], points_2d[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x**2 + y**2)
    try:
        coeffs, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
        A_, B_, C_ = coeffs
        center_x = -A_ / 2
        center_y = -B_ / 2
        radius = np.sqrt(center_x**2 + center_y**2 - C_)
        center = np.array([center_x, center_y])
        distances = np.linalg.norm(points_2d - center, axis=1)
        residuals = distances - radius
        rms_error = np.sqrt(np.mean(residuals**2))
        return center, radius, rms_error
    except np.linalg.LinAlgError:
        return np.zeros(2), 0.0, np.inf


def fit_circle_3d(points_3d: np.ndarray):
    """拟合 3D 空间中的圆。"""
    from sklearn.decomposition import PCA

    fit_info = {
        "success": False, "n_points": points_3d.shape[0],
        "plane_fit_quality": 0.0, "circle_fit_quality": 0.0, "inlier_ratio": 0.0,
    }
    if points_3d.shape[0] < 3:
        return np.zeros(3), 0.0, np.inf, np.zeros(3), fit_info

    centroid = np.mean(points_3d, axis=0)
    centered = points_3d - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    if eigvals[-1] > 0:
        fit_info["plane_fit_quality"] = eigvals[0] / eigvals[-1]
    plane_normal = normalize(eigvecs[:, 0])
    u = normalize(eigvecs[:, 1])
    v = normalize(eigvecs[:, 2])
    points_2d = np.column_stack([centered @ u, centered @ v])
    center_2d, radius, rms_error = fit_circle_2d(points_2d)
    if radius > 1e-6:
        rel_error = rms_error / radius
        fit_info["circle_fit_quality"] = 1.0 - rel_error if rel_error < 1.0 else 0.0
    if radius > 1e-6:
        distances = np.linalg.norm(points_2d - center_2d, axis=1)
        inliers = np.abs(distances - radius) < 0.1 * radius
        fit_info["inlier_ratio"] = np.mean(inliers)
    center_3d = centroid + center_2d[0] * u + center_2d[1] * v
    fit_info["success"] = (radius > 0) and (rms_error < radius * 0.1)
    return center_3d, radius, rms_error, plane_normal, fit_info


def is_constant_radius_fillet_by_points_and_normals(
    points: np.ndarray,
    normals: np.ndarray,
    n_slices: int = 10,
    min_points_per_slice: int = 8,
    radius_tol: float = 0.2,
    circle_fit_tol: float = 0.05,
    min_inlier_slices: float = 0.7,
    planarity_tol: float = 0.2,
    spine_method: str = "pca",
    min_radius: float = 2.5,
    max_radius: float = 18.0,
    center_traj_straightness_tol: float = 0.1,
    min_points: int = 40,
    min_normals: int = 40,
    aspect_ratio_tol: float = 0.5,
    spine_variance_tol: float = 0.05,
    min_arc_span: float = 1.5708,
):
    """判定是否为恒等半径倒圆角面。

    输入：
        points: [N, 3] 倒圆角面上的采样点坐标。
        normals: [M, 3] 倒圆角面上的法向量（与 points 不对应）。

    输出：
        is_fillet: 是否为恒等半径倒圆角。
        info: 详细信息字典（含 ``radius_mean`` 半径）。
    """
    info = {
        "success": False, "spine_direction": None, "spine_method": spine_method,
        "planarity_check": None, "radii": [], "rms_errors": [], "centers": [],
        "radius_mean": None, "radius_std": None, "radius_cv": None,
        "inlier_slice_ratio": 0.0, "avg_rms_error": None,
        "center_traj_straightness": None, "failure_reason": None,
    }

    if points.shape[0] < min_points:
        info["failure_reason"] = f"Too few points: {points.shape[0]}"
        return False, info
    if normals.shape[0] < min_normals:
        info["failure_reason"] = f"Too few normals: {normals.shape[0]}"
        return False, info

    normals_normed = normalize(normals)
    if np.allclose(normals_normed, normals_normed[0]):
        info["failure_reason"] = "All normals are the same, not a fillet surface"
        return False, info

    pca = PCA(n_components=3)
    pca.fit(normals_normed)
    pca_components = pca.components_
    pca_explained_var = pca.explained_variance_
    pca_total_var = np.sum(pca_explained_var)
    pca_var_ratio = pca_explained_var / pca_total_var if pca_total_var > 0 else np.zeros(3)
    variance_ratio_3rd = pca_var_ratio[2]

    distances_to_plane = np.abs(normals_normed @ pca_components[2, :])
    avg_distance = np.mean(distances_to_plane)
    std_distance = np.std(distances_to_plane)
    planarity_score = avg_distance + std_distance
    is_planar = (avg_distance < planarity_tol) and (variance_ratio_3rd < 0.1)
    info["planarity_check"] = {
        "avg_distance": avg_distance, "max_distance": np.max(distances_to_plane),
        "std_distance": std_distance, "planarity_score": planarity_score,
        "variance_ratio_3rd": variance_ratio_3rd, "is_planar": is_planar,
    }
    if not is_planar:
        info["failure_reason"] = (
            f"Normals are not planar (avg distance={avg_distance:.4f} > {planarity_tol})"
        )
        return False, info

    spine_direction = normalize(pca_components[2, :])
    info["spine_direction"] = spine_direction
    info["method"] = spine_method
    info["n_normals"] = normals.shape[0]
    info["explained_variance"] = pca_explained_var
    info["explained_variance_ratio"] = pca_var_ratio
    info["components"] = pca_components
    info["variance_ratio_3rd"] = variance_ratio_3rd
    if variance_ratio_3rd > spine_variance_tol:
        info["failure_reason"] = (
            f"Spine direction not reliable (3rd variance ratio={variance_ratio_3rd:.4f} > {spine_variance_tol})"
        )
        return False, info

    slices, slice_positions = slice_point_cloud_along_direction(points, spine_direction, n_slices=n_slices)
    if len(slices) < max(2, int(n_slices * 0.6)):
        info["failure_reason"] = f"Too few slices: {len(slices)}"
        return False, info

    radii = []
    rms_errors = []
    centers = []
    good_slices = 0
    for idx, slice_indices in enumerate(slices):
        if len(slice_indices) < min_points_per_slice:
            continue
        slice_points = points[slice_indices]
        center, radius, rms_error, plane_normal, fit_info = fit_circle_3d(slice_points)
        if radius < min_radius or radius > max_radius:
            continue
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
        rel_error = rms_error / radius if radius > 1e-6 else np.inf
        if (rel_error < circle_fit_tol and fit_info["inlier_ratio"] > 0.7 and fit_info["plane_fit_quality"] < 0.1):
            radii.append(radius)
            rms_errors.append(rms_error)
            centers.append(center)
            good_slices += 1

    if len(radii) < max(2, int(n_slices * min_inlier_slices)):
        info["failure_reason"] = f"Too few good circle fits: {len(radii)}"
        return False, info

    radii = np.array(radii)
    rms_errors = np.array(rms_errors)
    centers = np.array(centers)
    info["radii"] = radii
    info["rms_errors"] = rms_errors
    info["centers"] = centers
    info["inlier_slice_ratio"] = good_slices / len(slices)

    radius_mean = np.mean(radii)
    radius_std = np.std(radii)
    radius_cv = radius_std / radius_mean if radius_mean > 1e-6 else np.inf
    info["radius_mean"] = radius_mean
    info["radius_std"] = radius_std
    info["radius_cv"] = radius_cv
    info["avg_rms_error"] = np.mean(rms_errors)
    if radius_cv >= radius_tol:
        info["failure_reason"] = f"Radius inconsistency: CV={radius_cv:.4f} > {radius_tol}"
        return False, info

    if len(centers) >= 3:
        centroid_c = np.mean(centers, axis=0)
        centered_c = centers - centroid_c
        cov_c = np.cov(centered_c.T)
        eigvals_c, _ = np.linalg.eigh(cov_c)
        if eigvals_c[-1] > 1e-6:
            straightness_ratio = eigvals_c[0] / eigvals_c[-1]
            info["center_traj_straightness"] = straightness_ratio
            if straightness_ratio > center_traj_straightness_tol:
                info["failure_reason"] = (
                    f"Center trajectory not straight enough (ratio={straightness_ratio:.4f} > {center_traj_straightness_tol})"
                )
                return False, info

    point_centroid = np.mean(points, axis=0)
    point_cov = np.cov((points - point_centroid).T)
    point_eigvals, _ = np.linalg.eigh(point_cov)
    point_eigvals = np.sort(point_eigvals)[::-1]
    if point_eigvals[0] > 0:
        aspect_ratio = point_eigvals[1] / point_eigvals[0]
        if aspect_ratio > aspect_ratio_tol:
            info["failure_reason"] = f"Point cloud not elongated enough (aspect ratio={aspect_ratio:.4f} > {aspect_ratio_tol})"
            return False, info

    info["success"] = True
    return True, info
