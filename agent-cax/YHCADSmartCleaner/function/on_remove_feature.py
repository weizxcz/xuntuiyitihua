def remove_feature(doc, feature_list:list):
    if feature_list is None or not feature_list:
        return False
    doc.ResetCaseResult()
    object_names = [feature[0] for feature in feature_list]
    cell_ids = [feature[1] for feature in feature_list]
    if len(cell_ids) > 0 and len(object_names) > 0:
        doc.RunCommand("cmd_ncti_remove_features", object_names[0], cell_ids)
    return True