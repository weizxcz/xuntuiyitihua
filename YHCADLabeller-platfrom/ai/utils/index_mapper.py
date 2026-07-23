class IndexMapper:
    def __init__(self):
        self.id_maps = {}

    def compress(self, ids: list) -> list:
        if not ids:
            return []
        max_id = max(ids)
        if max_id < len(ids):
            return ids
        new_ids = list(range(len(ids)))
        self.id_maps = {str(item): str(i) for i, item in enumerate(ids)}
        return new_ids

    def convert(self, ids: list) -> list:
        return [int(self.id_maps.get(str(item), -1)) for item in ids]

    def decompress(self, ids: list) -> list:
        reverse_maps = {v: k for k, v in self.id_maps.items()}
        new_ids = [int(reverse_maps.get(str(item), str(item))) for item in ids]
        return new_ids


class IndexFilter:
    def filter_by_neighbor(self,
                           cell_ids: list,
                           face_ids: list,
                           fids: list,
                           eids: list,
                           edge_ids: list) -> list:
        cell_ids_filtered = []
        selected_edge_id = set(cell_ids) - set(face_ids)
        selected_face_id = set(cell_ids).intersection(set(face_ids))

        edge_face_map = {}
        for i, edge_id in enumerate(edge_ids):
            edge_face_map[edge_id] = (fids[i], eids[i])

        for edge_id in selected_edge_id:
            fid, eid = edge_face_map.get(edge_id, (None, None))
            if fid not in selected_face_id:
                continue
            if eid not in selected_face_id:
                continue
            cell_ids_filtered.append(edge_id)

        cell_ids_filtered.extend(selected_face_id)
        return cell_ids_filtered
