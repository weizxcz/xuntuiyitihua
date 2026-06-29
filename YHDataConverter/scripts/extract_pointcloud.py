"""子进程辅助脚本：提取点云并保存为 PLY。

用法: python extract_pointcloud.py <step_file> <output_ply> [dll_path]
dll_path 可选，默认从 config/system_config.json 读取。
"""
import sys
import ctypes
import importlib
import os
import json
import numpy as np
import open3d as o3d


def _init_ncti(dll_path):
    occ_path = os.path.join(dll_path, "OCC")
    os.add_dll_directory(occ_path)
    sys.path.insert(0, dll_path)
    ctypes.CDLL(os.path.join(dll_path, "ncti_command.dll"))
    ctypes.CDLL(os.path.join(dll_path, "ncti_occ_plugin.dll"))
    ctypes.CDLL(os.path.join(dll_path, "ncti_render_vulkan.dll"))
    NCTI = importlib.import_module("ncti_python")
    NCTI.Init(dll_path)
    return NCTI


def main():
    step_file = sys.argv[1]
    output_ply = sys.argv[2]

    if len(sys.argv) > 3:
        dll_path = sys.argv[3]
    else:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   "config", "system_config.json")
        with open(config_path, encoding="utf-8") as f:
            dll_path = json.load(f)["dllPath"]

    NCTI = _init_ncti(dll_path)

    doc = NCTI.Document()
    try:
        doc.New("OCC", "DCM", "GMSH")
        doc.SetImportAssemelFile(1)
        doc.RunCommand("cmd_ncti_import_file", step_file, 2)

        group = NCTI.RootGroup(doc)
        root = group.GetCurSubGroup()
        if not root:
            print("ERROR: GetCurSubGroup empty", file=sys.stderr)
            sys.exit(1)

        sub_solid_list = group.GetCurSubObject(root[0])
        if not sub_solid_list:
            print("ERROR: no solids found", file=sys.stderr)
            sys.exit(1)

        # 直接累积顶点和三角形，跳过逐个 TriangleMesh 构建
        all_vertices = []
        all_triangles = []
        offset = 0
        for solid in sub_solid_list:
            mesh_data = doc.GetMesh(solid)
            if len(mesh_data) in (0, 2):
                continue
            verts = np.array(mesh_data[0], dtype=float).reshape(-1, 3)
            tris = np.array(mesh_data[1], dtype=np.int32).reshape(-1, 3) + offset
            all_vertices.append(verts)
            all_triangles.append(tris)
            offset += len(verts)

        if not all_vertices:
            print("ERROR: no mesh data", file=sys.stderr)
            sys.exit(1)

        merged = o3d.geometry.TriangleMesh()
        merged.vertices = o3d.utility.Vector3dVector(np.vstack(all_vertices))
        merged.triangles = o3d.utility.Vector3iVector(np.vstack(all_triangles))

        pcd = merged.sample_points_uniformly(number_of_points=20000)
        o3d.io.write_point_cloud(output_ply, pcd, write_ascii=True)
        print(f"OK:{len(pcd.points)}")
    finally:
        doc.Delete()


if __name__ == "__main__":
    main()
