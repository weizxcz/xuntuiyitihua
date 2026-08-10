class IndexMapper:
    def __init__(self):
        self.id_maps = {}

    def compress(self, ids: list) -> list:
        """压缩ID列表，将非连续的ID映射为连续的ID
        
        Args:
            ids: 原始ID列表
            
        Returns:
            tuple: (压缩后的ID列表, ID映射字典)
        """
        if not ids:
            return []
        
        max_id = max(ids)
        if max_id < len(ids):
            return ids
        
        new_ids = list(range(len(ids)))
        self.id_maps = {str(item): str(i) for i, item in enumerate(ids)}
        
        return new_ids

    def convert(self, ids: list):
        new_ids = [int(self.id_maps.get(str(item), -1)) for item in ids]
        return new_ids

    def decompress(self, ids: list):
        reverse_maps = {v: k for k, v in self.id_maps.items()}
        new_ids = [int(reverse_maps.get(str(item), str(item))) for item in ids]
        return new_ids


class IndexFilter:
    def filter_by_neighbor(self, cell_ids: list, face_ids: list, fids: list, eids: list, edge_ids: list) -> list:
        """根据相邻关系过滤ID列表
        
        该函数用于过滤出与选中面相邻的边，以及选中的面本身
        
        Args:
            cell_ids: 所有单元格ID列表
            face_ids: 面ID列表
            fids: 边对应的第一个面ID列表
            eids: 边对应的第二个面ID列表
            edge_ids: 边ID列表
            
        Returns:
            list: 过滤后的ID列表，包含与选中面相邻的边和选中的面
        """
        cell_ids_filtered = []
        # 计算选中的边ID（不在面ID中的单元格ID）
        selected_edge_id = set(cell_ids) - set(face_ids)
        # 计算选中的面ID（同时在单元格ID和面ID中的ID）
        selected_face_id = set(cell_ids).intersection(set(face_ids))
        
        # 创建边到面的映射
        edge_face_map = {}
        for i, edge_id in enumerate(edge_ids):
            edge_face_map[edge_id] = (fids[i], eids[i])
        
        # 过滤出与选中面相邻的边
        for edge_id in selected_edge_id:
            fid, eid = edge_face_map.get(edge_id, (None, None))
            if fid in selected_face_id and eid in selected_face_id:
                cell_ids_filtered.append(edge_id)
        
        # 添加选中的面ID
        cell_ids_filtered.extend(selected_face_id)
        return cell_ids_filtered
