import random
import numpy as np
import torch
from scipy.spatial.transform import Rotation



def bounding_box_pointcloud(pts: torch.Tensor):
    x = pts[:, 0]
    y = pts[:, 1]
    z = pts[:, 2]
    box = [[x.min(), y.min(), z.min()], [x.max(), y.max(), z.max()]]
    return torch.tensor(box)


def bounding_box_uvgrid(inp: torch.Tensor):
    pts = inp[..., :3].reshape((-1, 3))
    mask = inp[..., 6].reshape(-1)
    point_indices_inside_faces = mask == 1
    pts = pts[point_indices_inside_faces, :]
    return bounding_box_pointcloud(pts)


def center_and_scale_uvgrid(inp: torch.Tensor, return_center_scale=False):
    inp = inp.transpose(1, 3) # channel last
    bbox = bounding_box_uvgrid(inp)
    diag = bbox[1] - bbox[0]
    scale = 2.0 / max(diag[0], diag[1], diag[2])
    center = 0.5 * (bbox[0] + bbox[1])
    inp[..., :3] -= center
    inp[..., :3] *= scale
    inp = inp.transpose(1, 3) # channel first
    if return_center_scale:
        return inp, center, scale
    return 


def center_and_scale(data: torch.Tensor):
    data["graph"].ndata["grid"], center, scale = center_and_scale_uvgrid(
        data["graph"].ndata["grid"], return_center_scale=True
    )
    if "grid" in data["graph"].edata.keys():
        egrid = data["graph"].edata["grid"]
        egrid = egrid.transpose(1, 2) # channel last
        egrid[..., :3] -= center
        egrid[..., :3] *= scale
        egrid = egrid.transpose(1, 2) # channel first
        data["graph"].edata["grid"] = egrid
    return data


def standardization(data, stat):
    data["graph"].ndata["x"] -= stat['mean_face_attr']
    data["graph"].ndata["x"] /= stat['std_face_attr']
    data["graph"].edata["x"] -= stat['mean_edge_attr']
    data["graph"].edata["x"] /= stat['std_edge_attr']
    return data


def get_random_rotation():
    """
    Get a random rotation in 90 degree increments along the canonical axes
    """
    axes = [
        np.array([1, 0, 0]),
        np.array([0, 1, 0]),
        np.array([0, 0, 1]),
    ]
    angles = [0.0, 90.0, 180.0, 270.0]
    axis = random.choice(axes)
    angle_radians = np.radians(random.choice(angles))
    return Rotation.from_rotvec(angle_radians * axis)


def rotate_uvgrid(inp, rotation):
    """
    Rotate the node features in the graph by a given rotation
    """
    inp = inp.transpose(1, 3) # channel last
    Rmat = torch.tensor(rotation.as_matrix()).float()
    orig_size = inp[..., :3].size()
    inp[..., :3] = torch.mm(inp[..., :3].reshape(-1, 3), Rmat).reshape(
        orig_size
    )  # Points
    inp[..., 3:6] = torch.mm(inp[..., 3:6].reshape(-1, 3), Rmat).reshape(
        orig_size
    )  # Normals/tangents
    inp = inp.transpose(1, 3) # channel first
    return inp
