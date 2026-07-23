"""5 种几何可视化功能（属性 / 拓扑 / UV网格 / 点云 / 多视图）。

从 YHDataConverter/ui/convert_tab.py 迁移而来，
适配 YHCADLabeller-platform 的 main_window 接口（self.doc / NCTI / cad_view / fp_stp）。
"""

import csv
import json
import os
import shutil
import sys
import tempfile
import traceback

import numpy as np
import wx
import wx.grid


def _find_graphviz_dot():
    """Return the Graphviz ``dot`` executable path, if it is installed."""
    dot_path = shutil.which("dot")
    if dot_path:
        return dot_path

    if sys.platform == "win32":
        install_dirs = [
            r"C:\Program Files\Graphviz\bin",
            r"C:\Program Files (x86)\Graphviz\bin",
        ]
        for program_files in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if not program_files or not os.path.isdir(program_files):
                continue
            install_dirs.extend(
                os.path.join(program_files, directory, "bin")
                for directory in os.listdir(program_files)
                if directory.lower().startswith("graphviz")
            )

        for install_dir in install_dirs:
            candidate = os.path.join(install_dir, "dot.exe")
            if os.path.isfile(candidate):
                os.environ["PATH"] = install_dir + os.pathsep + os.environ.get("PATH", "")
                return candidate
    return None


# =====================================================================
# 可视化 Canvas（拓扑图缩放/拖拽面板）
# =====================================================================

class _GraphCanvas(wx.Panel):
    """支持缩放平移的图像面板。"""
    def __init__(self, parent, image_path):
        super().__init__(parent, style=wx.FULL_REPAINT_ON_RESIZE)
        self.img = wx.Bitmap(image_path, wx.BITMAP_TYPE_PNG).ConvertToImage()
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self._dragging = False
        self._drag_start = (0, 0)
        self._drag_offset_start = (0, 0)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_left_up)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_SIZE, self.on_size)
        wx.CallAfter(self.fit_to_window)

    def fit_to_window(self):
        w, h = self.GetSize().width, self.GetSize().height
        if w < 1 or h < 1:
            return
        iw, ih = self.img.GetWidth(), self.img.GetHeight()
        if iw < 1 or ih < 1:
            return
        self.scale = min(w / iw, h / ih)
        self.offset_x = (w - iw * self.scale) / 2
        self.offset_y = (h - ih * self.scale) / 2
        self.Refresh()

    def on_size(self, evt):
        self.fit_to_window()
        evt.Skip()

    def on_paint(self, evt):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(45, 45, 45)))
        dc.Clear()
        sw = int(self.img.GetWidth() * self.scale)
        sh = int(self.img.GetHeight() * self.scale)
        if sw < 1 or sh < 1:
            return
        scaled = self.img.Scale(sw, sh, wx.IMAGE_QUALITY_HIGH)
        dc.DrawBitmap(wx.Bitmap(scaled), int(self.offset_x), int(self.offset_y))

    def on_wheel(self, evt):
        mx, my = evt.GetPosition()
        old_scale = self.scale
        factor = 1.15 if evt.GetWheelRotation() > 0 else 1 / 1.15
        self.scale = max(0.05, min(self.scale * factor, 10.0))
        self.offset_x = mx - (mx - self.offset_x) * (self.scale / old_scale)
        self.offset_y = my - (my - self.offset_y) * (self.scale / old_scale)
        self.Refresh()

    def on_left_down(self, evt):
        self.CaptureMouse()
        self._dragging = True
        self._drag_start = evt.GetPosition()
        self._drag_offset_start = (self.offset_x, self.offset_y)

    def on_left_up(self, evt):
        if self._dragging:
            self._dragging = False
            self.ReleaseMouse()

    def on_motion(self, evt):
        if self._dragging and evt.Dragging():
            mx, my = evt.GetPosition()
            self.offset_x = self._drag_offset_start[0] + (mx - self._drag_start[0])
            self.offset_y = self._drag_offset_start[1] + (my - self._drag_start[1])
            self.Refresh()


# =====================================================================
# 公共辅助（与 main_window 协作）
# =====================================================================

# 面类型 → (face_data列索引, 显示名, 颜色)
_FACE_TYPE_DEFS = [
    (1, '平面', '#4CAF50'),
    (2, '圆柱面', '#2196F3'),
    (3, '圆锥面', '#FF9800'),
    (4, '球面', '#9C27B0'),
    (5, '环面', '#F44336'),
    (7, 'NURBS面', '#607D8B'),
]

# 多视图相机位姿（6 个方位）
_d = 2 ** -0.5
_MULTIVIEW_CAMERAS = [
    ("右前上",  (_d, _d, 0.2)),
    ("左后上",  (-_d, -_d, 0.2)),
    ("左前下",  (-_d, _d, -0.2)),
    ("右后下",  (_d, -_d, -0.2)),
    ("左前上",  (-_d, _d, 0.2)),
    ("右后上",  (_d, -_d, 0.2)),
]


def _get_step_path(main_window):
    """从 main_window 取 STEP 文件路径；为空则在状态栏报错。"""
    step_path = getattr(main_window, 'fp_stp', '')
    if not step_path or not os.path.exists(step_path):
        main_window.status_bar.SetStatusText("请先导入STEP文件")
        return None
    return step_path


def _import_step(main_window, step_path):
    """独立导入 STEP，返回 (doc, ai_data)。"""
    NCTI = main_window.NCTI
    doc = NCTI.Document()
    doc.New("OCC", "DCM", "GMSH")
    doc.RunCommand("cmd_ncti_import_file", str(step_path), "testbox")
    ai_data = NCTI.AiModel(doc, "testbox")
    return doc, ai_data


def _extract_attrs(ai_data):
    """提取面/边属性表，返回 (face_columns, face_data, edge_columns, edge_data)。"""
    face_attr_dict = {int(x): y for x, y in zip(ai_data.FaceID, ai_data.FaceAttr)}
    face_attr_sorted = dict(sorted(face_attr_dict.items(), key=lambda x: x[0]))

    face_columns = [
        'faceid', 'plane', 'cylinder', 'cone', 'SphereFaceAttribute',
        'TorusFaceAttribute', 'FaceAreaAttribute', 'RationalNurbsFaceAttribute',
        'FaceCentroidAttribute_x', 'FaceCentroidAttribute_y', 'FaceCentroidAttribute_z',
        'lopps', 'degree'
    ]
    face_data = [[fid] + attrs for fid, attrs in face_attr_sorted.items()]

    edge_columns = [
        'fid', 'eid', 'concave', 'convex', 'smooth', 'length',
        'circular edge attr', 'closed edge attr', 'elliptical edge attr',
        'nonrational b spline edge attr', 'rational b spline edge attr',
        'straight edge attr'
    ]
    edge_data = []
    for idx, (fid, eid) in enumerate(zip(ai_data.FaceFID, ai_data.FaceEID)):
        edge_attr = ai_data.EdgeAttr[idx][:10] if len(ai_data.EdgeAttr) > idx else []
        edge_data.append([int(fid), int(eid)] + edge_attr)

    return face_columns, face_data, edge_columns, edge_data


def _normalize_points(points_arrays):
    if points_arrays:
        stacked = np.stack(points_arrays, axis=0)
        mean_arr = np.mean(stacked, axis=(0, 1, 2), keepdims=True).reshape((1, 1, 3))
        std_arr = np.std(stacked, axis=(0, 1, 2), keepdims=True).reshape((1, 1, 3))
        std_arr = np.where(std_arr < 0.0001, 1.0, std_arr)
    else:
        mean_arr = np.zeros((1, 1, 3))
        std_arr = np.ones((1, 1, 3))
    return mean_arr, std_arr


def _build_raw_face_grids(ai_data):
    points_arrays = [np.array(p).reshape((5, 5, 3)) for p in ai_data.FacePoints]
    mean_arr, std_arr = _normalize_points(points_arrays)

    grids = {}
    for points_arr, normals, mask, face_id in zip(
            points_arrays, ai_data.FaceNormals, ai_data.FaceMask, ai_data.FaceID):
        normalized = (points_arr - mean_arr) / std_arr
        normals_arr = np.array(normals).reshape((5, 5, 3))
        mask_arr = np.array(mask).reshape((5, 5, 1))
        grids[int(face_id)] = np.concatenate([normalized, normals_arr, mask_arr], axis=2)
    return grids


def _build_face_grids(ai_data):
    """面网格 5×5×7 → dict[face_id] = list。"""
    raw = _build_raw_face_grids(ai_data)
    return {fid: grid.tolist() for fid, grid in raw.items()}


def _build_face_grids_transposed(ai_data):
    """面网格转置为 7×5×5，按 FaceID 排序返回列表。"""
    raw = _build_raw_face_grids(ai_data)
    return [np.transpose(grid, (2, 0, 1)).tolist()
            for _, grid in sorted(raw.items(), key=lambda x: x[0])]


def _build_edge_grids(ai_data):
    """边网格 5×7（3坐标+3切向量+1二面角），dict["fid_eid"] = list。"""
    FaceFID = ai_data.FaceFID
    FaceEID = ai_data.FaceEID
    EdgePoints = ai_data.EdgePoints
    EdgeTangents = ai_data.EdgeTangents

    edge_grid = {}
    if len(EdgePoints) == 0:
        return edge_grid

    n = len(EdgePoints)
    m = len(EdgePoints[0]) // 3
    points_arr = np.array(EdgePoints, dtype=float).reshape(n, m, 3)
    tangents_arr = np.array(EdgeTangents, dtype=float).reshape(n, m, 3)

    # 二面角
    try:
        left = np.array(ai_data.leftNormal, dtype=float)
        right = np.array(ai_data.rightNormal, dtype=float)
        dots = np.sum(left * right, axis=1)
        norms_l = np.linalg.norm(left, axis=1)
        norms_r = np.linalg.norm(right, axis=1)
        with np.errstate(divide='ignore', invalid='ignore'):
            cos_theta = np.clip(dots / (norms_l * norms_r), -1.0, 1.0)
        angles = np.arccos(cos_theta)
        angles[(norms_l == 0) | (norms_r == 0)] = 0.0
        angles = np.nan_to_num(angles, nan=0.0)
    except Exception:
        angles = np.zeros(n)

    dihedral = np.repeat(angles[:, np.newaxis, np.newaxis], m, axis=1)
    combined = np.concatenate([points_arr, tangents_arr, dihedral], axis=2)

    for idx, (fid, eid) in enumerate(zip(FaceFID, FaceEID)):
        key = f"{int(fid)}_{int(eid)}"
        edge_grid[key] = combined[idx].tolist() if idx < len(combined) else []
    return edge_grid


def _run_pointcloud_script(step_path, output_path):
    """运行点云提取子进程，返回 CompletedProcess。"""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "scripts", "extract_pointcloud.py")
    return subprocess_run(
        [sys.executable, script_path, step_path, output_path],
        timeout=300,
    )


def _render_multiview_offscreen(main_window, step_path, output_dir, name_prefix=""):
    """离屏渲染 6 个方向的多视图到 output_dir。"""
    NCTI = main_window.NCTI
    doc = NCTI.Document()
    doc.New("OCC", "DCM", "GMSH")
    try:
        doc.SetImportAssemelFile(1)
        doc.RunCommand("cmd_ncti_import_file", str(step_path), "testbox")

        view = NCTI.View(doc.ID)
        view.CreateWindow()

        images = []
        for view_name, (vx, vy, vz) in _MULTIVIEW_CAMERAS:
            path = os.path.join(output_dir, f"{name_prefix}{view_name}.png")
            view.Straighten(NCTI.Vector(vx, vy, vz))
            doc.Update()
            doc.SaveImage(path)
            images.append((view_name, path))
        return images
    finally:
        doc.Delete()


def subprocess_run(cmd, timeout=300):
    """子进程跑（独立出来方便测试 mock）。

    NCTI SDK 在主进程已有 3D 视图渲染时，偶发在子进程退出阶段（doc.Delete 之后的
    进程收尾）发生访问违例（约 10~20% 概率），但此时点云数据已经计算并写盘完成。
    因此以 stdout 中的 "OK:" 标记作为任务是否成功的依据，而不是单纯看 returncode。
    """
    import subprocess
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    if result.returncode != 0 and 'OK:' not in result.stdout:
        parts = [f"返回码 {result.returncode}"]
        if result.stderr.strip():
            parts.append(result.stderr.strip().split('\n')[-1])
        if result.stdout.strip():
            parts.append(result.stdout.strip().split('\n')[-1])
        raise RuntimeError(' | '.join(parts))
    return result


def _ask_output_path(main_window, default_dir, base_name, suffix):
    """统一的"另存为"对话框。"""
    if suffix.endswith('.ply'):
        wildcard = "PLY文件 (*.ply)|*.ply"
    else:
        wildcard = "JSON文件 (*.json)|*.json"

    dlg = wx.FileDialog(
        main_window,
        message="保存转换结果",
        defaultDir=default_dir,
        defaultFile=base_name + suffix,
        wildcard=wildcard,
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
    )
    path = ""
    if dlg.ShowModal() == wx.ID_OK:
        path = dlg.GetPath()
    dlg.Destroy()
    return path


def _ask_output_dir(parent, default_path=""):
    dlg = wx.DirDialog(parent, message="选择输出目录",
                       defaultPath=default_path or "")
    path = ""
    if dlg.ShowModal() == wx.ID_OK:
        path = dlg.GetPath()
    dlg.Destroy()
    return path


def _format_cell(val):
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)


# =====================================================================
# 5 种可视化入口（每个对应 general_tab 上的一个按钮）
# =====================================================================

def viz_attributes(main_window):
    """属性可视化：弹窗显示面/边属性表，可过滤、可导出 CSV。"""
    step_path = _get_step_path(main_window)
    if not step_path:
        return
    doc = None
    try:
        main_window.status_bar.SetStatusText("正在提取属性用于可视化...")
        doc, ai_data = _import_step(main_window, step_path)
        face_columns, face_data, edge_columns, edge_data = _extract_attrs(ai_data)

        # 数据已提取，立即释放 doc
        doc.Delete()
        doc = None

        _show_attrs_dialog(main_window, face_columns, face_data, edge_columns, edge_data)
        main_window.status_bar.SetStatusText("属性可视化完成")

    except Exception as e:
        traceback.print_exc()
        main_window.status_bar.SetStatusText(f"属性可视化失败: {e}")
    finally:
        if doc:
            doc.Delete()


def _show_attrs_dialog(main_window, face_columns, face_data, edge_columns, edge_data):
    parent_size = main_window.GetSize()
    dlg_w = min(int(parent_size.width * 0.85), 1400)
    dlg_h = min(int(parent_size.height * 0.8), 900)
    dialog = wx.Dialog(main_window, title="属性可视化",
                       size=(dlg_w, dlg_h),
                       style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)

    # 顶部过滤栏
    active_types = [(None, '全部')]
    for col_idx, label, _ in _FACE_TYPE_DEFS:
        if any(abs(row[col_idx] - 1) < 0.001 for row in face_data):
            active_types.append((col_idx, label))

    top_sizer = wx.BoxSizer(wx.HORIZONTAL)
    top_sizer.Add(wx.StaticText(dialog, label="面类型过滤:"),
                  0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

    face_type_choice = wx.Choice(dialog, choices=[t[1] for t in active_types])
    face_type_choice.SetSelection(0)
    top_sizer.Add(face_type_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 20)

    count_label = wx.StaticText(
        dialog, label=f"共 {len(face_data)} 个面, {len(edge_data)} 条边")
    top_sizer.Add(count_label, 0, wx.ALIGN_CENTER_VERTICAL)
    top_sizer.AddStretchSpacer()

    # Notebook：面属性 / 边属性
    notebook = wx.Notebook(dialog)

    face_panel = wx.Panel(notebook)
    face_grid = wx.grid.Grid(face_panel)
    face_grid.CreateGrid(0, len(face_columns))
    for col, name in enumerate(face_columns):
        face_grid.SetColLabelValue(col, name)

    def populate_face_grid(rows):
        n = face_grid.GetNumberRows()
        if n > 0:
            face_grid.DeleteRows(0, n)
        face_grid.AppendRows(len(rows))
        face_grid.BeginBatch()
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                face_grid.SetCellValue(r, c, _format_cell(val))
        face_grid.EndBatch()
        face_grid.AutoSizeColumns()

    populate_face_grid(face_data)

    face_sizer = wx.BoxSizer(wx.VERTICAL)
    face_sizer.Add(face_grid, 1, wx.EXPAND)
    face_panel.SetSizer(face_sizer)

    edge_panel = wx.Panel(notebook)
    edge_grid = wx.grid.Grid(edge_panel)
    edge_grid.CreateGrid(len(edge_data), len(edge_columns))
    for col, name in enumerate(edge_columns):
        edge_grid.SetColLabelValue(col, name)
    edge_grid.BeginBatch()
    for r, row in enumerate(edge_data):
        for c, val in enumerate(row):
            edge_grid.SetCellValue(r, c, _format_cell(val))
    edge_grid.EndBatch()
    edge_grid.AutoSizeColumns()

    edge_sizer = wx.BoxSizer(wx.VERTICAL)
    edge_sizer.Add(edge_grid, 1, wx.EXPAND)
    edge_panel.SetSizer(edge_sizer)

    notebook.AddPage(face_panel, "面属性")
    notebook.AddPage(edge_panel, "边属性")

    outer_sizer = wx.BoxSizer(wx.VERTICAL)
    outer_sizer.Add(top_sizer, 0, wx.EXPAND | wx.ALL, 8)
    outer_sizer.Add(notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
    dialog.SetSizer(outer_sizer)
    dialog.Layout()
    dialog.Centre()

    def on_face_type_change(evt):
        sel = face_type_choice.GetSelection()
        col_idx = active_types[sel][0]
        if col_idx is None:
            filtered = face_data
        else:
            filtered = [row for row in face_data if abs(row[col_idx] - 1) < 0.001]
        populate_face_grid(filtered)
        count_label.SetLabel(
            f"显示 {len(filtered)}/{len(face_data)} 个面, {len(edge_data)} 条边")
        evt.Skip()

    face_type_choice.Bind(wx.EVT_CHOICE, on_face_type_change)

    def on_export(evt):
        base_name = os.path.splitext(os.path.basename(main_window.fp_stp or ""))[0]
        dlg = wx.FileDialog(dialog, message="导出",
                            defaultFile=base_name + "_attributes.csv",
                            wildcard="CSV文件 (*.csv)|*.csv",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        path = dlg.GetPath()
        dlg.Destroy()

        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['面属性'])
                writer.writerow(face_columns)
                for row in face_data:
                    writer.writerow(row)
                writer.writerow([])
                writer.writerow(['边属性'])
                writer.writerow(edge_columns)
                for row in edge_data:
                    writer.writerow(row)
            main_window.status_bar.SetStatusText(f"已导出: {path}")
        except Exception as e:
            traceback.print_exc()
            main_window.status_bar.SetStatusText(f"导出失败: {e}")

    dialog.Bind(wx.EVT_CLOSE, lambda e: dialog.Destroy())
    dialog.Show()


def viz_topology(main_window):
    """拓扑可视化：用 graphviz 渲染面邻接图，可缩放拖拽查看。"""
    if not _find_graphviz_dot():
        message = (
            "未找到 Graphviz 的 dot.exe，无法渲染拓扑图。\n\n"
            "请从 https://graphviz.org/download/ 安装 Graphviz，"
            "并在安装程序中选择将 Graphviz 加入 PATH；安装后请重新启动本程序。"
        )
        main_window.status_bar.SetStatusText("拓扑可视化不可用：未安装 Graphviz dot.exe")
        wx.MessageBox(message, "缺少 Graphviz", wx.OK | wx.ICON_WARNING, main_window)
        return

    import networkx as nx  # noqa: lazy import
    import graphviz  # noqa

    step_path = _get_step_path(main_window)
    if not step_path:
        return

    doc = None
    try:
        main_window.status_bar.SetStatusText("正在提取拓扑用于可视化...")
        doc, ai_data = _import_step(main_window, step_path)

        FaceFID = list(ai_data.FaceFID)
        FaceEID = list(ai_data.FaceEID)
        FaceID = list(ai_data.FaceID)

        face_id_to_idx = {fid: idx for idx, fid in enumerate(FaceID)}
        face_f_idx = [face_id_to_idx.get(fid, 0) for fid in FaceFID]
        face_e_idx = [face_id_to_idx.get(eid, 0) for eid in FaceEID]
        num_nodes = len(FaceID)
        adj = np.zeros((num_nodes, num_nodes), dtype=np.int32)
        rows = np.array(face_f_idx + face_e_idx, dtype=np.int32)
        cols = np.array(face_e_idx + face_f_idx, dtype=np.int32)
        np.add.at(adj, (rows, cols), 1)
        adj = (adj > 0).astype(np.int32)

        face_attr_dict = {int(x): y for x, y in zip(FaceID, ai_data.FaceAttr)}
        face_id_list = [int(fid) for fid in FaceID]
        node_types, node_colors = [], []
        for fid in face_id_list:
            attrs = face_attr_dict[fid]
            matched = False
            for col_idx, tname, color in _FACE_TYPE_DEFS:
                if abs(attrs[col_idx - 1] - 1) < 0.001:
                    node_types.append(tname)
                    node_colors.append(color)
                    matched = True
                    break
            if not matched:
                node_types.append('未知')
                node_colors.append('#999999')

        graph_face_attr = [v for _, v in sorted(face_attr_dict.items(), key=lambda x: x[0])]
        graph_face_grid = _build_face_grids_transposed(ai_data)
        graph_edge_attr = [sublist[:10] for sublist in ai_data.EdgeAttr]
        graph_json = {
            'graph': {'edges': (FaceFID, FaceEID), 'num_nodes': num_nodes},
            'graph_face_attr': graph_face_attr,
            'graph_face_grid': graph_face_grid,
            'graph_edge_attr': graph_edge_attr,
            'graph_edge_grid': [],
            'adjacency matrix': adj.tolist()
        }

        G = nx.Graph()
        G.add_nodes_from(range(num_nodes))
        for fi, ei in zip(face_f_idx, face_e_idx):
            G.add_edge(fi, ei)

        dot = graphviz.Graph(comment='Face Adjacency Graph',
                             graph_attr={'dpi': '96', 'fontname': 'Microsoft YaHei'},
                             node_attr={'fontname': 'Microsoft YaHei'},
                             edge_attr={'fontname': 'Microsoft YaHei'})
        for i in range(num_nodes):
            dot.node(str(i), f'Face {face_id_list[i]}\n({node_types[i]})',
                     shape='ellipse', style='filled', fillcolor=node_colors[i],
                     fontcolor='white', fontsize='11',
                     margin='0.05,0.02')
        for u, v in G.edges():
            dot.edge(str(u), str(v))

        svg_data = dot.pipe(format='svg')
        temp_dir = tempfile.mkdtemp()
        png_path = os.path.join(temp_dir, 'graph.png')
        with open(png_path, 'wb') as f:
            f.write(dot.pipe(format='png'))

        num_edges = int(adj.sum() // 2)

        doc.Delete()
        doc = None

        _show_graph_dialog(main_window, png_path, svg_data, graph_json, step_path,
                           num_nodes, num_edges, node_types, temp_dir)
        main_window.status_bar.SetStatusText("拓扑可视化完成")

    except Exception as e:
        traceback.print_exc()
        main_window.status_bar.SetStatusText(f"拓扑可视化失败: {e}")
    finally:
        if doc:
            doc.Delete()


def _show_graph_dialog(main_window, png_path, svg_data, graph_json, step_path,
                        num_nodes, num_edges, node_types, temp_dir):
    dialog = wx.Dialog(main_window, title="拓扑可视化",
                       size=(900, 700),
                       style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)

    type_counts = {}
    for t in node_types:
        type_counts[t] = type_counts.get(t, 0) + 1
    stats_parts = [f"{t}: {c}" for t, c in type_counts.items()]
    stats_text = f"节点: {num_nodes}, 边: {num_edges}  |  " + ", ".join(stats_parts)

    canvas = _GraphCanvas(dialog, png_path)

    type_to_color = {name: color for _, name, color in _FACE_TYPE_DEFS}
    type_to_color['未知'] = '#999999'
    legend_sizer = wx.BoxSizer(wx.HORIZONTAL)
    for tname, count in type_counts.items():
        color = type_to_color.get(tname, '#999999')
        swatch = wx.Panel(dialog, size=(14, 14))
        swatch.SetBackgroundColour(wx.Colour(color))
        label = wx.StaticText(dialog, label=f"{tname} ({count})")
        legend_sizer.Add(swatch, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)
        legend_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)

    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    stats_label = wx.StaticText(dialog, label=stats_text)
    button_sizer.Add(stats_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
    button_sizer.AddStretchSpacer()

    outer_sizer = wx.BoxSizer(wx.VERTICAL)
    outer_sizer.Add(canvas, 1, wx.EXPAND)
    outer_sizer.Add(legend_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
    outer_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 5)
    dialog.SetSizer(outer_sizer)

    def on_export(evt):
        base_name = os.path.splitext(os.path.basename(step_path))[0]
        dlg = wx.DirDialog(dialog, message="选择导出目录")
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        output_dir = dlg.GetPath()
        dlg.Destroy()

        try:
            svg_path = os.path.join(output_dir, f"{base_name}.svg")
            with open(svg_path, 'wb') as f:
                f.write(svg_data)
            json_path = os.path.join(output_dir, f"{base_name}_graph.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(graph_json, f, indent=4)
            main_window.status_bar.SetStatusText(
                f"已导出: {svg_path}, {json_path}")
        except Exception as e:
            traceback.print_exc()
            main_window.status_bar.SetStatusText(f"导出失败: {e}")

    def on_close(evt):
        shutil.rmtree(temp_dir, ignore_errors=True)
        dialog.Destroy()
        evt.Skip()

    dialog.Bind(wx.EVT_CLOSE, on_close)
    dialog.Show()


def viz_uvgrid(main_window):
    """UV网格可视化：在弹窗里嵌入 NCTI 视图，运行 cmd_ncti_ai_uv_point_display。"""
    step_path = _get_step_path(main_window)
    if not step_path:
        return

    try:
        main_window.status_bar.SetStatusText("正在生成UV网格可视化...")
        NCTI = main_window.NCTI
        doc, ai_model = _import_step(main_window, step_path)

        dialog = wx.Dialog(main_window, title="UV网格可视化",
                           size=(800, 600),
                           style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        panel = wx.Panel(dialog)
        panel.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)

        outer_sizer = wx.BoxSizer(wx.VERTICAL)
        outer_sizer.Add(panel, 1, wx.EXPAND)
        dialog.SetSizer(outer_sizer)

        def setup_view():
            hwnd = panel.GetHandle()
            view = NCTI.View(doc.ID)
            view.CreateWindow(hwnd)
            doc.RunCommand("cmd_ncti_ai_uv_point_display",
                           "testbox", ai_model)
            view.SetWindowVis(True, doc.ID)
            doc.Zoom()
            doc.Update()
            size = panel.GetSize()
            view.SetGeometry(0, 0, size.width, size.height)
            view.RenderEnable(True)
            doc.Update()

            def on_panel_size(evt):
                s = panel.GetSize()
                view.SetGeometry(0, 0, s.width, s.height)
                doc.Update()
                evt.Skip()
            panel.Bind(wx.EVT_SIZE, on_panel_size)

        def on_save(evt):
            default_dir = os.path.dirname(main_window.fp_stp or "")
            base_name = os.path.splitext(os.path.basename(main_window.fp_stp or ""))[0]
            output_path = _ask_output_path(main_window, default_dir, base_name, "_uv_grid.json")
            if not output_path:
                return
            try:
                face_grid = _build_face_grids(ai_model)
                edge_grid = _build_edge_grids(ai_model)
                result = {'face': face_grid, 'edge': edge_grid}
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=4)
                main_window.status_bar.SetStatusText(
                    f"UV网格已保存: {len(face_grid)} 个面, {len(edge_grid)} 条边 → {output_path}")
            except Exception as e:
                main_window.status_bar.SetStatusText(f"保存失败: {e}")

        def on_dialog_close(evt):
            doc.Delete()
            dialog.Destroy()
            main_window.doc.Update()
            main_window.cad_view.update_view()
            main_window.status_bar.SetStatusText("UV网格可视化完成")
            evt.Skip()

        dialog.Bind(wx.EVT_CLOSE, on_dialog_close)
        wx.CallAfter(setup_view)
        dialog.Show()

    except Exception as e:
        traceback.print_exc()
        main_window.status_bar.SetStatusText(f"UV网格可视化失败: {e}")


def viz_pointcloud(main_window):
    """点云可视化：子进程跑 Open3D，弹窗显示。"""
    import open3d as o3d  # noqa: lazy import
    step_path = _get_step_path(main_window)
    if not step_path:
        return

    temp_dir = tempfile.mkdtemp()
    try:
        main_window.status_bar.SetStatusText("正在生成点云可视化...")
        temp_ply = os.path.join(temp_dir, "pointcloud.ply")
        _run_pointcloud_script(step_path, temp_ply)

        pcd = o3d.io.read_point_cloud(temp_ply)
        count = len(pcd.points)
        if count == 0:
            main_window.status_bar.SetStatusText("点云为空")
            return

        o3d.visualization.draw_geometries(
            [pcd], window_name="点云可视化", width=800, height=600)
        main_window.status_bar.SetStatusText(
            f"点云可视化完成: {count} 个点")

    except Exception as e:
        traceback.print_exc()
        main_window.status_bar.SetStatusText(f"点云可视化失败: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def viz_multiview(main_window):
    """多视图可视化：6 个方位 PNG，弹窗 2×3 网格显示。"""
    step_path = _get_step_path(main_window)
    if not step_path:
        return

    temp_dir = tempfile.mkdtemp()
    try:
        main_window.status_bar.SetStatusText("正在生成多视图...")
        images = _render_multiview_offscreen(main_window, step_path, temp_dir)
        _show_multiview_dialog(main_window, images)
        main_window.status_bar.SetStatusText(
            f"多视图可视化: {len(_MULTIVIEW_CAMERAS)} 张")

    except Exception as e:
        traceback.print_exc()
        main_window.status_bar.SetStatusText(f"多视图可视化失败: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _show_multiview_dialog(main_window, images):
    dialog = wx.Dialog(main_window, title="多视图可视化", size=(820, 660))
    dialog.SetBackgroundColour(wx.Colour(30, 30, 30))
    grid = wx.GridSizer(2, 3, 5, 5)

    for view_name, image_path in images:
        panel = wx.Panel(dialog)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)

        bmp = wx.Bitmap(image_path, wx.BITMAP_TYPE_PNG)
        img = bmp.ConvertToImage()
        w, h = img.GetWidth(), img.GetHeight()
        scale = min(250 / w, 250 / h)
        img = img.Scale(int(w * scale), int(h * scale), wx.IMAGE_QUALITY_HIGH)
        bmp = wx.Bitmap(img)

        static_bmp = wx.StaticBitmap(panel, bitmap=bmp)
        label = wx.StaticText(panel, label=view_name)
        label.SetForegroundColour(wx.WHITE)

        panel_sizer.Add(static_bmp, 1, wx.EXPAND)
        panel_sizer.Add(label, 0, wx.ALIGN_CENTER)
        panel.SetSizer(panel_sizer)
        grid.Add(panel, 1, wx.EXPAND)

    outer_sizer = wx.BoxSizer(wx.VERTICAL)
    outer_sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 5)
    dialog.SetSizer(outer_sizer)
    dialog.ShowModal()
    dialog.Destroy()
