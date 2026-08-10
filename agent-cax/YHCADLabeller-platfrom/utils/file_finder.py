import os

_GEOM_EXTENSIONS = {".step", ".stp", ".igs"}
_GEOM_DIRS = ("steps", "step")


def _find_geom_file(directory, base_name):
    for ext in _GEOM_EXTENSIONS:
        candidate = os.path.join(directory, base_name + ext)
        if os.path.isfile(candidate):
            return candidate
    return None


def json_labels_path_to_step_path(json_path):
    """根据 JSON 路径查找对应的 CAD 几何文件。

    查找策略（按优先级）：
    1. 同级 steps/ 或 step/ 目录中查找
    2. 上级目录递归搜索同名文件
    """
    json_path = os.path.normpath(json_path)
    base_name = os.path.splitext(os.path.basename(json_path))[0]
    parent_dir = os.path.dirname(json_path)

    for dirname in _GEOM_DIRS:
        candidate = _find_geom_file(os.path.join(parent_dir, dirname), base_name)
        if candidate:
            return candidate

    upper_dir = os.path.dirname(parent_dir)
    if upper_dir and upper_dir != parent_dir:
        target_names = {base_name + ext for ext in _GEOM_EXTENSIONS}
        for root, dirs, _files in os.walk(upper_dir):
            dirs[:] = [d for d in dirs if d.lower() != "labels"]
            for f in _files:
                if f in target_names:
                    return os.path.join(root, f)

    return None
