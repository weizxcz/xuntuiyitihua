
import numpy as np
import os
from ..base_functions import load_config_basic

os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"



class AAGGraphExtraToolNcti():

    def __init__(self,NCTI,step_path):
        config = load_config_basic()
        self.eps = config['step2graph_infos']['std_eps']
        self.NCTI = NCTI
        self.ai_data_info,self.doc = self.import_step_get_info(step_path)
        self.FaceID = self.ai_data_info.FaceID

    def import_step_get_info(self,step_path):
        doc = self.NCTI.Document()
        doc.New("OCC", "DCM", 0)
        doc.RunCommand("cmd_ncti_import_file", str(step_path), "testbox")
        ai_data_info = self.NCTI.AiModel(doc, "testbox")
        return ai_data_info,doc

    def get_graph(self):
        FaceFID = self.ai_data_info.FaceFID
        FaceEID = self.ai_data_info.FaceEID
        graph = {'edges': (FaceFID, FaceEID), 'num_nodes': len(self.FaceID)}
        return graph

    def get_graph_edge_attr(self):
        original_graph_edge_attr = self.ai_data_info.EdgeAttr
        graph_edge_attr = [sublist[:10] for sublist in original_graph_edge_attr]
        return graph_edge_attr

    def get_graph_face_attr(self):
        graph_face_attr = self.ai_data_info.FaceAttr
        graph_face_attr = self.resortface(self.FaceID,graph_face_attr)
        return graph_face_attr

    def get_graph_face_grid(self):
        FacePoints = self.ai_data_info.FacePoints
        FaceNormals = self.ai_data_info.FaceNormals
        FaceMask = self.ai_data_info.FaceMask
        graph_face_grid = self.extract_face_point_grid(FacePoints, FaceNormals, FaceMask)
        graph_face_grid = self.resortface(self.FaceID,graph_face_grid)
        return graph_face_grid

    def extract_face_point_grid(self, FacePoints, FaceNormals, FaceMask):
        graph_face_grid = []
        # First pass: collect all points arrays to compute global mean and std
        points_arrays = [np.array(points).reshape((5, 5, 3)) for points in FacePoints]
        if len(points_arrays) > 0:
            stacked_points = np.stack(points_arrays, axis=0)  # (N, 5, 5, 3)
            mean_arr = np.mean(stacked_points, axis=(0, 1, 2), keepdims=True)  # (1, 1, 1, 3)
            std_arr = np.std(stacked_points, axis=(0, 1, 2), keepdims=True)
            # reshape to (1, 1, 3)
            mean_arr = mean_arr.reshape((1, 1, 3))
            std_arr = std_arr.reshape((1, 1, 3))
            # avoid division by zero
            std_arr = np.where(std_arr < 0.0001, 1.0, std_arr)
        else:
            # Fallback if no points provided
            mean_arr = np.zeros((1, 1, 3), dtype=float)
            std_arr = np.ones((1, 1, 3), dtype=float)
        # Second pass: normalize each face's points using global mean/std and build grid
        for points_arr, normals, mask in zip(points_arrays, FaceNormals, FaceMask):
            normalized_points = (points_arr - mean_arr) / std_arr
            normals_arr = np.array(normals).reshape((5, 5, 3))
            mask_arr = np.array(mask).reshape((5, 5, 1))
            single_grid = np.concatenate([normalized_points, normals_arr, mask_arr], axis=2)
            single_grid = np.transpose(single_grid, (2, 0, 1))
            graph_face_grid.append(single_grid.tolist())
        return graph_face_grid

    def resortface(self,faceid,faceattr):
        face_attr_dict = {x: y for x, y in zip(faceid, faceattr)}
        face_attr_sort_dict = dict(sorted(face_attr_dict.items(), key=lambda x: x[0]))
        graph_face_attr = list(face_attr_sort_dict.values())
        return graph_face_attr

    def delete_doc(self):
        self.doc.Delete()

def find_standardization(data):
    """计算face和edge属性的均值与标准差"""
    all_face_attr = []
    all_edge_attr = []
    for one_sample in data:
        if one_sample is None:
            continue
        fn, stat_data = one_sample
        all_face_attr.extend(stat_data["graph_face_attr"])
        all_edge_attr.extend(stat_data["graph_edge_attr"])

    if not all_face_attr or not all_edge_attr:
        return {
            'mean_face_attr': [],
            'std_face_attr': [],
            'mean_edge_attr': [],
            'std_edge_attr': [],
        }

    graph_face_attr = np.asarray(all_face_attr)
    graph_edge_attr = np.asarray(all_edge_attr)

    mean_face_attr = np.mean(graph_face_attr, axis=0)
    std_face_attr = np.std(graph_face_attr, axis=0)
    mean_edge_attr = np.mean(graph_edge_attr, axis=0)
    std_edge_attr = np.std(graph_edge_attr, axis=0)

    return {
        'mean_face_attr': mean_face_attr.tolist(),
        'std_face_attr': std_face_attr.tolist(),
        'mean_edge_attr': mean_edge_attr.tolist(),
        'std_edge_attr': std_edge_attr.tolist(),
    }
def check_zero_std(stat_data):
    std_face_attr = stat_data['std_face_attr']
    std_edge_attr = stat_data['std_edge_attr']
    if np.nonzero(std_face_attr)[0].shape[0] != len(std_face_attr) \
            or np.nonzero(std_edge_attr)[0].shape[0] != len(std_edge_attr):
        print('WARNING! has zero standard deviation.')
