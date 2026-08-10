import json
import os

import numpy as np
import onnxruntime as ort


class AGGNetInferenceONNX:
    """NumPy and ONNX Runtime implementation compatible with ``ai_recognizer``."""

    maps_output_indices_to_face_ids = True

    def __init__(self, weight_path="weight_round.onnx", stat_path="attr_stat.json"):
        self.inst_thres = 0.5
        self.bottom_thres = 0.5
        self.eps = 1e-6
        self.onnx_path = weight_path
        self.model_type = "full"
        self.init_recognizer()
        self.stat = self.load_statistics(stat_path)

    def init_recognizer(self):
        if not os.path.exists(self.onnx_path):
            raise FileNotFoundError(f"ONNX model not found: {self.onnx_path}")
        options = ort.SessionOptions()
        options.log_severity_level = 3
        self.sess = ort.InferenceSession(
            self.onnx_path, sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.node_attr_dim = self._read_input_dim("node_attr")
        self.edge_attr_dim = self._read_input_dim("edge_attr")

    def _read_input_dim(self, input_name):
        for input_meta in self.sess.get_inputs():
            if input_meta.name == input_name:
                return int(input_meta.shape[1])
        raise ValueError(f"ONNX model is missing input: {input_name}")

    @staticmethod
    def _sigmoid(values):
        values = np.asarray(values)
        return 1.0 / (1.0 + np.exp(-np.clip(values, -709.0, 709.0)))

    @staticmethod
    def _face_grid(points, normals, mask):
        points = np.asarray(points, dtype=np.float32).reshape(5, 5, 3)
        normals = np.asarray(normals, dtype=np.float32).reshape(5, 5, 3)
        mask = np.asarray(mask, dtype=np.float32).reshape(5, 5, 1)
        return np.transpose(np.concatenate([points, normals, mask], axis=2), (2, 0, 1))

    def load_statistics(self, stat_path):
        with open(stat_path, "r", encoding="utf-8") as stream:
            stat = json.load(stream)
        for key in ("mean_face_attr", "std_face_attr", "mean_edge_attr", "std_edge_attr"):
            stat[key] = np.asarray(stat[key], dtype=np.float64)
        stat["std_face_attr"] = stat["std_face_attr"].copy()
        stat["std_edge_attr"] = stat["std_edge_attr"].copy()
        stat["std_face_attr"][stat["std_face_attr"] < 1e-8] = 1.0
        stat["std_edge_attr"][stat["std_edge_attr"] < 1e-8] = 1.0
        return stat

    def prepare_onnx_input_from_arrays(
        self, face_id, face_fid, face_eid, face_points, face_normals, face_mask,
        graph_edge_attr, graph_face_attr,
    ):
        order = np.argsort(np.asarray(face_id, dtype=np.int64), kind="stable")
        node_attr = np.asarray(graph_face_attr, dtype=np.float32)[order, :self.node_attr_dim]
        node_grid = np.stack(
            [self._face_grid(face_points[index], face_normals[index], face_mask[index]) for index in order]
        ).astype(np.float32, copy=False)
        edge_attr = np.asarray(graph_edge_attr, dtype=np.float32)[:, :self.edge_attr_dim]
        node_attr = (node_attr.astype(np.float64) - self.stat["mean_face_attr"]).astype(np.float32)
        node_attr = (node_attr.astype(np.float64) / self.stat["std_face_attr"]).astype(np.float32)
        edge_attr = (edge_attr.astype(np.float64) - self.stat["mean_edge_attr"]).astype(np.float32)
        edge_attr = (edge_attr.astype(np.float64) / self.stat["std_edge_attr"]).astype(np.float32)
        return {
            "node_attr": node_attr.astype(np.float32, copy=False),
            "node_grid": node_grid,
            "edge_attr": edge_attr.astype(np.float32, copy=False),
            "src": np.asarray(face_fid, dtype=np.int64),
            "dst": np.asarray(face_eid, dtype=np.int64),
        }

    def ai_model_inference(
        self, face_id, face_fid, face_eid, face_points, face_normals, face_mask,
        graph_edge_attr, graph_face_attr,
    ):
        return self.sess.run(
            None,
            self.prepare_onnx_input_from_arrays(
                face_id, face_fid, face_eid, face_points, face_normals, face_mask,
                graph_edge_attr, graph_face_attr,
            ),
        )

    def statistic_prob(self, prob_list):
        if not prob_list:
            return 0.5
        probs = np.asarray(prob_list, dtype=np.float64)
        probs = probs[np.isfinite(probs)]
        if not len(probs):
            return 0.5

        sorted_probs = np.sort(probs)
        cumulative = np.cumsum(sorted_probs)
        otsu = 0.5
        best_variance = 0.0
        for index in range(1, len(sorted_probs)):
            if sorted_probs[index] == sorted_probs[index - 1]:
                continue
            weight0 = index / len(sorted_probs)
            weight1 = 1.0 - weight0
            mean0 = cumulative[index - 1] / index
            mean1 = (cumulative[-1] - cumulative[index - 1]) / (len(sorted_probs) - index)
            variance = weight0 * weight1 * (mean0 - mean1) ** 2
            if variance > best_variance:
                best_variance = variance
                otsu = (sorted_probs[index] + sorted_probs[index - 1]) / 2

        hist, edges = np.histogram(probs, bins=100, range=(0, 1))
        peaks = [i for i in range(1, len(hist) - 1)
                 if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > np.mean(hist)]
        valleys = []
        for start, end in zip(peaks, peaks[1:]):
            valley = start + np.argmin(hist[start:end])
            valleys.append((edges[valley] + edges[valley + 1]) / 2)
        histogram = max(valleys) if valleys else np.median(probs)

        diffs = np.diff(sorted_probs)
        if len(diffs) > 10:
            relative = np.where(sorted_probs[:-1] > 1e-6, diffs / sorted_probs[:-1], diffs)
            significant = np.where(relative > np.percentile(relative, 90))[0]
            gradient = ((sorted_probs[significant[np.argmax(relative[significant])]] +
                         sorted_probs[significant[np.argmax(relative[significant])] + 1]) / 2
                        if len(significant) else np.median(probs))
        else:
            gradient = np.median(probs)

        hist50, edges50 = np.histogram(probs, bins=50, range=(0, 1))
        low_ratio = hist50[:16].sum() / max(hist50.sum(), 1)
        high_ratio = hist50[33:].sum() / max(hist50.sum(), 1)
        if low_ratio > 0.1 and high_ratio > 0.05:
            bimodal = (edges50[np.searchsorted(np.cumsum(hist50), hist50.sum() / 2)] +
                       edges50[np.searchsorted(np.cumsum(hist50), hist50.sum() / 2) + 1]) / 2
        else:
            bimodal = np.median(probs)

        smoothed = np.convolve(hist / (hist.sum() + 1e-10), np.ones(3) / 3, mode="same")
        left = np.argmax(smoothed[:50])
        right = 50 + np.argmax(smoothed[50:])
        density = edges[left + np.argmin(smoothed[left:right + 1])] if left < right else np.median(probs)
        valid = [value for value in (otsu, histogram, gradient, bimodal, density) if 0 <= value <= 1]
        return float(np.clip(np.median(valid) if valid else 0.5, 0.01, 0.99))

    def optimize_seg_predict_face(self, seg_predict_face, adj_true, min_faces_num=2, max_faces_num=5):
        if not seg_predict_face:
            return []
        selected = set(seg_predict_face)
        additions = set()
        for face_index in selected:
            if np.sum(adj_true[face_index, list(selected)]) < min_faces_num:
                additions.update(np.where(adj_true[face_index] > 0)[0])
        selected.update(additions)
        selected_list = list(selected)
        selected.difference_update(
            selected_list[index]
            for index, count in enumerate(np.sum(adj_true[selected_list], axis=1))
            if count > max_faces_num
        )
        return sorted(selected)

    def group_connected_faces(self, seg_predict_face, adj_true):
        faces = sorted(set(seg_predict_face))
        if len(faces) < 2:
            return [faces] if faces else []
        face_to_index = {face: index for index, face in enumerate(faces)}
        parent = list(range(len(faces)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for index, face in enumerate(faces):
            for neighbor in np.where(adj_true[face] > 0)[0]:
                if neighbor in face_to_index:
                    left, right = find(index), find(face_to_index[neighbor])
                    if left != right:
                        parent[left] = right
        groups = {}
        for index, face in enumerate(faces):
            groups.setdefault(find(index), []).append(face)
        return list(groups.values())

    def postprocess_feature(self, seg_out, inst_out, bottom_out, adj_true,
                            min_faces_num=0, max_faces_num=5, feature_name="round",
                            face_ids=None):
        seg_probabilities = self._sigmoid(np.asarray(seg_out)[:, 1])
        threshold = self.statistic_prob(seg_probabilities.tolist())
        selected = np.where(seg_probabilities > threshold)[0].tolist()
        selected = self.optimize_seg_predict_face(selected, adj_true, min_faces_num, max_faces_num)
        groups = self.group_connected_faces(selected, adj_true)

        if face_ids is not None:
            ordered_face_ids = np.asarray(face_ids, dtype=np.int64)[
                np.argsort(np.asarray(face_ids, dtype=np.int64), kind="stable")
            ]
            if len(ordered_face_ids) != len(seg_probabilities):
                raise ValueError("The ONNX output count does not match the supplied NCTI face IDs.")
            selected = [int(ordered_face_ids[index]) for index in selected]
            groups = [[int(ordered_face_ids[index]) for index in group] for group in groups]

        return {
            0: {
                "instance": selected,
                "inst_name": feature_name,
                "bottom_faces": [],
                "groups": groups,
            }
        }
