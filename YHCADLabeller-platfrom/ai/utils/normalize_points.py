import numpy as np


def normalize(points):
    points_array = np.asarray(points)
    original_shape = points_array.shape
    flattened_view = points_array.reshape(-1, 3)

    centroid = np.mean(flattened_view, axis=0)
    coord_range = np.ptp(flattened_view, axis=0)
    max_range = np.max(coord_range)

    if max_range > 1e-12:
        scale_ratio = 1.0 / max_range
    else:
        scale_ratio = 1.0

    normalized_points = (flattened_view - centroid) * scale_ratio
    normalized_points = normalized_points.reshape(original_shape)
    return centroid, scale_ratio, normalized_points


def scale(edge_attr: list, scale_ratio: float):
    edge_attr_array = np.array(edge_attr)
    edge_attr_array[:, 3] *= scale_ratio
    return edge_attr_array


def scale_to_unit_box(face_attr: list, centroid, scale_ratio):
    face_attr_array = np.array(face_attr)
    face_attr_array[:, 5] *= scale_ratio
    face_attr_array[:, 7:10] = (face_attr_array[:, 7:10] - centroid) * scale_ratio
    return face_attr_array
