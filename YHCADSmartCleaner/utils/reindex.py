class IndexManager:
    def __init__(self, doc, obj_name, cell_ids):
        self.doc = doc
        self.obj_name = obj_name

        self.id_map = self._init_id_map(cell_ids)
        self.cell_ids = []
        self.update_cell_ids()

    def _init_id_map(self, cell_ids):
        id_map = {}
        for cell_id in cell_ids:
            pt = self.doc.GetFaceMidPoint(self.obj_name, cell_id)
            id_map.update({cell_id: pt})
        return id_map

    def update_cell_ids(self):
        self.cell_ids = self.id_map.keys()

    def add_cell(self, new_cell_ids:list):
        for cell_id in new_cell_ids:
            if cell_id not in self.id_map:
                pt = self.doc.GetFaceMidPoint(self.obj_name, cell_id)
                self.id_map.update({cell_id: pt})
        self.update_cell_ids()

    def remove_cell(self, cell_ids: list):
        for cell_id in cell_ids:
            if cell_id in self.id_map:
                self.id_map.pop(cell_id)
        self.update_cell_ids()

    def reindex(self):
        new_id_map = {}
        for pt in self.id_map.values():
            cell_id = self.doc.FindFaceByNearestPoint(self.obj_name, pt)
            new_id_map.update({cell_id[0]:pt})
        self.id_map = new_id_map
        self.update_cell_ids()
