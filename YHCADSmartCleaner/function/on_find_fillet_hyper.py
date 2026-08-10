from function.on_find_fillet import find_fillet_with_dialog
from function.on_find_fillet_by_ai import find_fillet_by_ai


def find_fillet_ai_plus_geo(NCTI, doc, weight_path, stat_path):
    """
    ai算法就是find_fillet算子
    """
    found_fillet_geo = find_fillet_with_dialog(NCTI, doc, 1.0)
    found_fillet_ai = find_fillet_by_ai(NCTI, doc,
                                        weight_path=weight_path,
                                        stat_path=stat_path)

    if found_fillet_ai or found_fillet_geo:
        selection = NCTI.SelectionManager(doc)
        selection.ClearSelected()
        dict_geo = {}
        dict_ai = {}
        for name, cell_id in zip(found_fillet_geo.ObjectNames, found_fillet_geo.CellIDs):
            dict_geo[cell_id] = name
        for name, cell_id in zip(found_fillet_ai.ObjectNames, found_fillet_ai.CellIDs):
            dict_ai[cell_id] = name
        dict_interset = {key: dict_geo[key] for key in dict_geo if key in dict_ai and dict_ai[key] == dict_geo[key]}

        obj_names = []
        cell_ids = []
        for key, value in dict_interset.items():
            obj_names.append(value)
            cell_ids.append(key)

        selection.ObjectNames = obj_names
        selection.CellIDs = cell_ids
        return selection
    return None

