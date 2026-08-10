# -*- coding: utf-8 -*-
import sys
import os
import ctypes
import importlib
import wx
import wx.aui
import numpy as np
import random
import math
import itertools
import json
import torch
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from src.utils.base_functions import load_config_basic, load_yaml

# 配置参数
CONFIG = {
    "dll_path": r'D:\tools\YHCppSDK-Community\SDK\bin\RelWithDebInfo',
    "output_dir": os.path.join(os.path.dirname(__file__), 'output'),
    "ai_u_count": 5,
    "ai_v_count": 5,
    "ai_edge_count": 5
}

# 人为输入参数
MANUAL_PARAMS = {
    "fillet_class": 1  # 圆角类别索引
}


def init_NCTI_Config(dll_path):
    try:
        # 加载炎核开发引擎的建模内核、渲染引擎、Python接口
        sys.path.insert(0, dll_path)
        os.add_dll_directory(dll_path + '/OCC')  # occ_path
        ctypes.CDLL(dll_path + "/ncti_command.dll")
        ctypes.CDLL(dll_path + "/ncti_occ_plugin.dll")
        ctypes.CDLL(dll_path + "/ncti_render_vulkan.dll")
        NCTI = importlib.import_module("ncti_python")
        if 1 != NCTI.Init(dll_path):
            return None
        return NCTI
    except:
        print("System path error or loading dll failure!")
        return None


def _build_args_from_config():
    """从 config 构建 BrepSeg 所需的 args 对象"""
    config = load_config_basic()
    model_config_path = config['model_infos'].get('brepmfr_config_path') or 'configs/model_configs/brepMFR/round_model_config.yaml'
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not config['data_path_infos']['use_absolute_path']:
        model_config_path = os.path.join(base_dir, model_config_path)
    model_config = load_yaml(model_config_path)

    processed_data = config['data_path_infos']['processed_data']
    splits_dir = config['data_path_infos']['divide_data_infos']['divide_result_txt_save_dir']
    checkpoint_dir = config['model_infos'].get('brepmfr_checkpoint_dir', 'results/BrepMFR')
    if not config['data_path_infos']['use_absolute_path']:
        processed_data = os.path.join(base_dir, processed_data)
        splits_dir = os.path.join(base_dir, splits_dir)
        checkpoint_dir = os.path.join(base_dir, checkpoint_dir)

    class Args:
        pass
    args = Args()
    # args.num_classes = model_config.get('num_classes', 25)
    # 对于二分类任务，强制设置 num_classes=2
    # 这样可以确保与训练时的模型结构匹配
    args.num_classes = 2
    args.batch_size = model_config.get('batch_size', 64)
    args.num_workers = model_config.get('num_workers', 0)
    args.dropout = model_config.get('dropout', 0.3)
    args.attention_dropout = model_config.get('attention_dropout', 0.3)
    args.act_dropout = model_config.get('act_dropout', 0.3)
    args.d_model = model_config.get('d_model', 512)
    args.dim_node = model_config.get('dim_node', 256)
    args.n_heads = model_config.get('n_heads', 32)
    args.n_layers_encode = model_config.get('n_layers_encode', 8)
    args.dataset_path = processed_data
    args.splits_dir = splits_dir
    args.checkpoint_dir = checkpoint_dir
    args.experiment_name = "BrepMFR1"
    args.checkpoint = None
    args.traintest = "train"
    return args


class MainWindow(wx.Frame):
    def __init__(self, NCTI, doc):
        super().__init__(None, title="炎核看图工具V1.0", size=(1000, 800))
        self.HWND = -1
        self.NCTI = NCTI
        self.doc = doc
        self.name = 'box'

        self.max_distance = 1  # 最大直线距离，应为包围盒两个边界点距离
        self.sample_num = 512  # 采样个数
        self.dstb_cap = 64  # 分布裁切份数

        # 这里假设面个数为n，边个数为m，以下数组给出对应shape值
        self.face_samples = []  # 采样缓存，n*self.sample_num*3，数值是坐标，取值R
        self.angle_samples = []  # 采样缓存，n*self.sample_num的一半*3，数值是坐标，取值R
        self.face_ids = []  # 面ID信息，n，数值0~(n-1)
        self.edge_ids = []  # 边ID信息， m，数值一般为n~(n+m-1)

        self.face_adj = []  # 邻接矩阵，n*n，数值0或1
        self.d2_distance = []  # d2距离，n*n*self.dstb_cap，数值0~1
        self.a3_distance = []  # a3距离, n*n*self.dstb_cap，数值0~1

        self.edge_near_faces = {}  # 边的邻边，key-m & value-二元组，key是边ID，value是相邻的面
                                   # value的元组是分先后顺序的，这里通常ID值较小的在前面，因此这个数值的边体现的是双向边
        self.face_loops = {}  # 面的包围线，key-n & value-非空不定值，key是面ID，value是边ID列表
        self.face_common_edges = {}  # 面的共边，key-(n*(n+1)/2) & value-可空不定值，key是面ID对二元组，value是边ID列表

        self.init_main_layout()  # 初始化主布局
        self.HWND = self.view_panel.GetHandle()  # 获取视图面板的句柄
        self.Centre()
        self.Show()  # 显示窗口
        self.Layout()  # 更新布局以确保正确计算尺寸


    def init_main_layout(self):
        # 创建AUI管理器 - 这是整个应用的布局管理器
        self.aui_manager = wx.aui.AuiManager(self)
        # 创建顶部选项卡面板
        top_panel = wx.Panel(self)
        top_sizer = wx.BoxSizer(wx.VERTICAL)
        # 创建选项卡控件
        self.notebook = wx.Notebook(top_panel, wx.ID_ANY, style=wx.NB_TOP)
        self.doc_tab = wx.Panel(self.notebook)
        self.view_tab = wx.Panel(self.notebook)
        self.ai_tab = wx.Panel(self.notebook)
        # 添加选项卡到notebook
        self.notebook.AddPage(self.doc_tab, "文档")
        self.notebook.AddPage(self.view_tab, "看图")
        self.notebook.AddPage(self.ai_tab, "AI特征识别")
        # 创建选项卡的工具栏
        doc_toolbar = wx.ToolBar(self.doc_tab, wx.ID_ANY, style=wx.TB_FLAT | wx.TB_TEXT)
        view_toolbar = wx.ToolBar(self.view_tab, wx.ID_ANY, style=wx.TB_FLAT | wx.TB_TEXT)
        ai_toolbar = wx.ToolBar(self.ai_tab, wx.ID_ANY, style=wx.TB_FLAT | wx.TB_TEXT)

        # 工具栏按钮列表：选项卡名--按钮--按钮文本
        buttons = [
            (doc_toolbar, self.on_create_doc, "创建文档"),
            (doc_toolbar, self.on_close_doc, "关闭文档"),
            (view_toolbar, self.on_import_file, "导入模型"),
            (view_toolbar, self.on_zoom, "复位模型"),
            (view_toolbar, self.on_clean, "清空文档"),

            (ai_toolbar, self.on_get_shape_info, "获取实体信息"),
            (ai_toolbar, self.on_get_face_adj, "获取面相邻信息"),
            (ai_toolbar, self.on_get_d2_distance, "获取d2距离"),
            (ai_toolbar, self.on_get_a3_distance, "获取a3距离"),


            (ai_toolbar, self.on_get_edge_near_faces, "获取边的邻面"),
            (ai_toolbar, self.on_get_face_loop, "获取面的包围线"),
            (ai_toolbar, self.on_get_common_edge, "获取面的共边"),
            (ai_toolbar, self.on_detect_fillets, "圆角识别")
        ]
        for i in buttons:
            # 添加点击按钮事件、按钮及对应图标，并将响应函数与点击按钮事件绑定
            this_button_id = wx.NewIdRef()
            i[0].SetToolBitmapSize((36, 36))
            icon_path = os.path.join(f'icons/{i[2]}.png')
            if os.path.exists(icon_path):
                i[0].AddTool(this_button_id, i[2], wx.Bitmap(icon_path), shortHelp=i[2])
            else:
                i[0].AddTool(this_button_id, i[2], wx.Bitmap.FromRGBA(36, 36, *[200//2,220//2,255//2,255]), shortHelp=i[2])
            i[0].Bind(wx.EVT_TOOL, i[1], id=this_button_id)
            i[0].Realize()

        # 将notebook添加到顶部面板
        top_sizer.Add(self.notebook, 1, wx.EXPAND)
        top_panel.SetSizer(top_sizer)
        # 使用AUI管理器添加所有面板，设置正确的层级关系
        self.aui_manager.AddPane(top_panel,
                                 wx.aui.AuiPaneInfo().Top().
                                 CaptionVisible(False).
                                 CloseButton(False).
                                 Floatable(False).
                                 DockFixed(True).
                                 Layer(0).
                                 Position(0).
                                 BestSize(-1, 100))
        # 创建3D视图区域（使用Panel作为占位符）
        self.view_panel = wx.Panel(self, style=wx.SUNKEN_BORDER)
        self.view_panel.SetBackgroundColour(wx.Colour(200, 220, 255))
        self.aui_manager.AddPane(self.view_panel,
                                 wx.aui.AuiPaneInfo().Center().
                                 CaptionVisible(False).
                                 CloseButton(False).
                                 Floatable(False).
                                 DockFixed(True).
                                 Layer(1).
                                 Position(1))
        self.aui_manager.Update()


    # 创建和关闭文档的响应函数
    def on_create_doc(self, event):
        """创建文档事件处理"""
        if -1 != self.HWND:
            self.doc.New("OCC")  # 新建的文档默认调用OCC建模内核
            self.view = self.NCTI.View(self.doc.ID)
            self.view.CreateWindow(self.HWND)
            # 获取视图面板尺寸
            width, height = self.view_panel.GetSize()
            # 设置窗口可见性和几何尺寸
            self.view.SetWindowVis(True, self.doc.ID)
            self.view.SetGeometry(0, 0, width, height)
            # 更新文档
            self.doc.Update()
            self.doc.Zoom()
    def on_close_doc(self, event):
        self.doc.Close()


    # 导入模型和看图场景的响应函数
    def on_import_file(self, event):
        """导入文件事件处理"""
        if -1 == self.doc.ID:
            wx.MessageBox("请先新建文档！", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        # 创建文件选择对话框
        with wx.FileDialog(
                self,
                message="选取导入模型",
                defaultDir=".",
                defaultFile="",
                wildcard="Stp Files (*.stp)|*.stp|Step Files (*.step)|*.step|IGS Files (*.igs)|*.igs",
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                file_path = dlg.GetPath()
                # 如果是step/stp文件，打印文件名到终端
                if file_path.lower().endswith(('.step', '.stp')):
                    print(f"导入STEP文件: {os.path.basename(file_path)}")
                self.doc.RunCommand("cmd_ncti_import_file", file_path, self.name)
                self.doc.Zoom()
    def on_zoom(self, event):
        self.doc.Zoom()
        self.view.SetViewMode(0)
    def on_clean(self, event):
        self.doc.Clear()
        self.doc.ResetCaseResult()


    # 获取两点之间的绝对直线距离
    def get_dis(self, point1, point2):
        x_dis = point1[0] - point2[0]
        y_dis = point1[1] - point2[1]
        z_dis = point1[2] - point2[2]
        return math.sqrt(x_dis**2 + y_dis**2 + z_dis**2)
    # 获取两个点和一个顶点形成的夹角
    def get_angle(self, point1, point2, vertex):
        vector1 = [vertex[0] - point1[0], vertex[1] - point1[1], vertex[2] - point1[2]]
        vector2 = [vertex[0] - point2[0], vertex[1] - point2[1], vertex[2] - point2[2]]
        mod1 = math.sqrt(vector1[0]**2 + vector1[1]**2 + vector1[2]**2)
        mod2 = math.sqrt(vector2[0]**2 + vector2[1]**2 + vector2[2]**2)
        if mod1 < 1e-6 or mod2 < 1e-6:  # 规避point和vertex重复情况
            return 0
        dot = vector1[0]*vector2[0] + vector1[1]*vector2[1] + vector1[2]*vector2[2]
        cos_value = dot / (mod1 * mod2)  # 余弦值
        cos_value = max(-1.0, min(1.0, cos_value))  # 处理浮点精度误差
        angle_arc = math.acos(cos_value)
        return angle_arc / math.pi  # 获取的弧度值取值范围为0-pi，这里做一下归一化


    # 返回这个面上的num个随机点，每个点的存在形式是三维坐标
    def get_face_sample(self, face_id, num):
        points = []
        while len(points) < num:
            uv = [random.random(), random.random()]
            pt = self.doc.GetFacePointFromUV(self.name, face_id, uv[0], uv[1])
            points.append([pt.X, pt.Y, pt.Z])
        return points

    # 获取模型的全部面ID和边ID，并且提前计算包围盒边界、采样点，防止重复计算
    def get_face_info(self):
        print("开始获取面信息...")
        try:
            sel = self.NCTI.SelectionManager(self.doc)
            print("创建选择管理器成功")
            
            sel.ObjectNames = self.doc.AllNames()
            print(f"获取所有对象名称成功: {sel.ObjectNames}")
            
            if len(sel.ObjectNames) > 0:
                self.face_ids = self.doc.FindAllFaces(sel.ObjectNames[0])
                print(f"获取所有面ID成功: {self.face_ids}")
                
                bd = self.doc.GetBoundingBox(sel.ObjectNames)
                print(f"获取包围盒成功: {bd}")
                
                bd_pt1 = (bd[0], bd[1], bd[2])
                bd_pt2 = (bd[3], bd[4], bd[5])
                self.max_distance = self.get_dis(bd_pt1, bd_pt2)  # 获取包围盒边界值以计算最大距离，用于距离值归一化
                print(f"计算最大距离成功: {self.max_distance}")

                # 计算完整采样点
                self.face_samples = []  # 初始化一下，防止有重复录入
                self.angle_samples = []
                print(f"开始计算面采样点，共 {len(self.face_ids)} 个面")
                start_sampling = time.time()
                for i, face_id in enumerate(self.face_ids):
                    print(f"计算第 {i+1} 个面的采样点...")
                    # 完整采样点数，每个面都采512个点
                    self.face_samples.append(self.get_face_sample(face_id, self.sample_num))
                    self.angle_samples.append(self.get_face_sample(face_id, self.sample_num//2))  # angle_samples每个面也采512个点
                end_sampling = time.time()
                print(f"计算面采样点成功，耗时: {end_sampling - start_sampling:.6f}秒")
            else:
                print("没有找到对象")
                self.face_ids = []
        except Exception as e:
            print(f"获取面信息时出错: {e}")
            import traceback
            traceback.print_exc()


    def get_edge_info(self):
        ai = self.NCTI.AiModel(self.doc, self.name)
        test = ai.FaceID
        self.edge_ids = ai.EdgeID
        # self.edge_ids = sorted(set(self.edge_ids))


    # 获取两个面的d2距离，返回它们的采样点距离的分布情况
    def get_face_distance(self, face1, face2):
        start_time = time.time()
        sample1 = np.array(self.face_samples[face1])
        sample2 = np.array(self.face_samples[face2])
        # 生成随机排列
        arr_shuffled = np.random.permutation(self.sample_num)
        # 计算距离
        diff = sample1 - sample2[arr_shuffled]
        distances = np.sqrt(np.sum(diff**2, axis=1)) / self.max_distance
        # 统计分布
        distribution, _ = np.histogram(distances, bins=self.dstb_cap, range=(0, 1), density=False)
        end_time = time.time()
        print(f"get_face_distance({face1}, {face2})耗时: {end_time - start_time:.6f}秒")
        return distribution
    # 获取两个面的a3距离，返回它们的采样点角度的分布情况
    def get_angle_distance(self, face1, face2):
        start_time = time.time()
        sample1 = np.array(self.face_samples[face1])
        sample2 = np.array(self.face_samples[face2])
        vertexes = np.array(self.angle_samples[face1] + self.angle_samples[face2])
        vertex_count = len(vertexes)
        # 生成随机排列
        arr_shuffled_face = np.random.permutation(self.sample_num)
        arr_shuffled_vertex = np.random.permutation(vertex_count)[:self.sample_num]  # 确保不越界
        # 获取采样点
        p1 = sample1
        p2 = sample2[arr_shuffled_face]
        v = vertexes[arr_shuffled_vertex]
        # 计算向量
        vector1 = v - p1
        vector2 = v - p2
        # 计算模长
        mod1 = np.sqrt(np.sum(vector1**2, axis=1))
        mod2 = np.sqrt(np.sum(vector2**2, axis=1))
        # 规避零模长情况
        mask = (mod1 > 1e-6) & (mod2 > 1e-6)
        # 计算点积
        dot = np.sum(vector1 * vector2, axis=1)
        # 计算余弦值
        cos_value = dot / (mod1 * mod2)
        # 处理浮点精度误差
        cos_value = np.clip(cos_value, -1.0, 1.0)
        # 计算角度并归一化
        angles = np.zeros_like(cos_value)
        angles[mask] = np.arccos(cos_value[mask]) / np.pi
        # 统计分布
        distribution, _ = np.histogram(angles, bins=self.dstb_cap, range=(0, 1), density=False)
        end_time = time.time()
        print(f"get_angle_distance({face1}, {face2})耗时: {end_time - start_time:.6f}秒")
        return distribution


    # AI特征识别场景的响应函数
    def on_get_shape_info(self, event):
        
        if len(self.face_ids) == 0:
            self.get_face_info()
        if len(self.edge_ids) == 0:
            self.get_edge_info()
        print('面ID信息：')
        print(self.face_ids)
        print('边ID信息：')
        print(self.edge_ids)

    def on_get_face_adj(self, event):
        if len(self.face_ids) == 0:
            print('还没有初始化特征信息，请先点击"获取实体信息"！')
            return
        n = len(self.face_ids)
        self.face_adj = np.zeros((n, n), dtype=int)
        ai = NCTI.AiModel(self.doc, self.name)
        for i in range(n):
            for j in range(n):
                self.face_adj[i][j] = (ai.GetTwoFacesAdjacent(self.face_ids[i], self.face_ids[j]) != 0)
        print(self.face_adj)

    def on_get_d2_distance(self, event):
        start_time = time.time()
        if len(self.face_ids) == 0:
            print('还没有初始化特征信息，请先点击"获取实体信息"！')
            return
        n = len(self.face_ids)
        self.d2_distance = np.zeros((n, n, self.dstb_cap), dtype=int)
        
        # 并行计算d2距离
        def compute_d2(i):
            results = []
            for j in range(n):
                results.append(self.get_face_distance(self.face_ids[i], self.face_ids[j]))
            return i, results
        
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(compute_d2, i) for i in range(n)]
            for future in futures:
                i, results = future.result()
                for j, result in enumerate(results):
                    self.d2_distance[i][j] = result
        
        end_time = time.time()
        print(f"计算d2距离总耗时: {end_time - start_time:.6f}秒")
        print(self.d2_distance)

    def on_get_a3_distance(self, event):
        start_time = time.time()
        if len(self.face_ids) == 0:
            print('还没有初始化特征信息，请先点击"获取实体信息"！')
            return
        n = len(self.face_ids)
        self.a3_distance = np.zeros((n, n, self.dstb_cap), dtype=int)
        
        # 并行计算a3距离
        def compute_a3(i):
            results = []
            for j in range(n):
                results.append(self.get_angle_distance(self.face_ids[i], self.face_ids[j]))
            return i, results
        
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(compute_a3, i) for i in range(n)]
            for future in futures:
                i, results = future.result()
                for j, result in enumerate(results):
                    self.a3_distance[i][j] = result
        
        end_time = time.time()
        print(f"计算a3距离总耗时: {end_time - start_time:.6f}秒")
        print(self.a3_distance)

    def on_get_edge_near_faces(self, event):
        if len(self.face_ids) == 0:
            print('还没有初始化特征信息，请先点击"获取实体信息"！')
            return

        ai = NCTI.AiModel(self.doc, self.name)
        edge_id_match = ai.EdgeID
        face_eid_match = ai.FaceFID
        face_fid_match = ai.FaceEID
        print("面ID与边ID匹配列表：")
        print(edge_id_match)
        print(face_eid_match)
        print(face_fid_match)
        print("......................................")
        edge_near_faces = {}
        # 这里剔除掉重复的边，选择eid小于fid的部分
        for (e, f1, f2) in zip(edge_id_match, face_eid_match, face_fid_match):
            if f1 < f2:
                edge_near_faces[e] = (f1, f2)  # 注意：这里的边ID e是唯一的，但是不同边可能有相同的两个邻面f1/f2
        print(edge_near_faces)
        self.edge_near_faces = edge_near_faces

    def on_get_face_loop(self, event):
        if len(self.face_ids) == 0:
            print('还没有初始化特征信息，请先点击"获取实体信息"！')
            return
        face_loops = {item: [] for item in self.face_ids}
        ai = NCTI.AiModel(self.doc, self.name)
        face_id_match = ai.FaceEID
        edge_id_match = ai.EdgeID
        # 这里剔，选择eid小于fid的部分
        for (f, e) in zip(face_id_match, edge_id_match):
            face_loops[f].append(e)
        for i in face_loops:
            face_loops[i] = sorted(set(face_loops[i]))
        print(face_loops)
        self.face_loops = face_loops


    # 取面ID的两两组合（可以重复），获取它们的共边ID集合
    # 注意：共边是指两个面都包含的边，共边可以有多条。
    def on_get_common_edge(self, event):
        if len(self.face_ids) == 0 or len(self.face_loops) == 0:
            print('还没有初始化特征信息，请先点击"获取实体信息"和"获取面的包围线"！')
            return

        if len(self.face_common_edges) != 0:
            print(self.face_common_edges)
            return

        # 取面ID的两两组合，在face_loops中寻找它们的交集作为共边列表
        face_pairs = list(itertools.combinations_with_replacement(self.face_ids, 2))
        for (i, j) in face_pairs:
            common_edge = list(set(self.face_loops[i]) & set(self.face_loops[j]))
            self.face_common_edges[(i, j)] = common_edge
        print(self.face_common_edges)
        return

    def on_detect_fillets(self, event):
        """圆角识别"""
        total_start_time = time.time()
        print("开始圆角识别...")
        
        # 检查是否已导入模型
        if -1 == self.doc.ID:
            wx.MessageBox("请先新建文档并导入模型！", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        
        # 检查是否有对象
        sel = self.NCTI.SelectionManager(self.doc)
        sel.ObjectNames = self.doc.AllNames()
        if len(sel.ObjectNames) == 0:
            wx.MessageBox("请先导入模型！", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        
        # 创建文件选择对话框选择模型权重
        with wx.FileDialog(
                self,
                message="选择模型权重文件",
                defaultDir=".",
                defaultFile="",
                wildcard="Checkpoint Files (*.ckpt)|*.ckpt",
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            checkpoint_path = dlg.GetPath()
        
        # 配置
        dll_path = CONFIG["dll_path"]
        output_dir = CONFIG["output_dir"]
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # 保存原始工作目录
            original_cwd = os.getcwd()
            
            # 添加当前目录到 Python 搜索路径
            sys.path.insert(0, os.path.dirname(__file__))
            
            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)
            
            # 从配置中读取AI模型参数
            ai_u_count = CONFIG.get("ai_u_count", 5)
            ai_v_count = CONFIG.get("ai_v_count", 5)
            ai_edge_count = CONFIG.get("ai_edge_count", 5)
            
            # 初始化AI模型（忽略"Error:Set object name(m_pLCM is null)."警告，因为它不影响功能）
            ai_init_start = time.time()
            ai = self.NCTI.AiModel(self.doc, self.name, ai_u_count, ai_v_count, ai_edge_count)
            ai_init_end = time.time()
            print(f"初始化AI模型耗时: {ai_init_end - ai_init_start:.6f}秒")
            
            # 直接从AI模型获取面ID
            face_ids = ai.FaceID
            
            # 检查面ID是否存在
            if not face_ids:
                print("Warning: No FaceID found in AI model, skipping processing")
                # 返回空的图结构
                graph_data = {
                    "graph": {
                        "num_nodes": 0,
                        "num_edges": 0,
                        "src_nodes": [],
                        "dst_nodes": []
                    },
                    "node_data": {
                        "x": [],
                        "a": [],
                        "y": [],
                        "z": [],
                        "l": [],
                        "f": []
                    },
                    "edge_data": {
                        "x": [],
                        "l": [],
                        "t": [],
                        "a": [],
                        "c": []
                    },
                    "graph_labels": {
                        "angle_distance": [],
                        "d2_distance": [],
                        "spatial_pos": [],
                        "edges_path": []
                    }
                }
            else:
                # 提取图结构数据
                extract_start = time.time()
                graph_data = self.extract_graph_structure(ai, face_ids)
                extract_end = time.time()
                print(f"提取图结构数据耗时: {extract_end - extract_start:.6f}秒")
            
            # 检查graph_data是否为None
            if graph_data is None:
                raise Exception("Failed to extract graph data: No graph data generated")
            
            # 保存图结构
            save_start = time.time()
            output_json = os.path.join(output_dir, "temp_model.json")
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(graph_data, f, indent=2, ensure_ascii=False)
            save_end = time.time()
            print(f"保存图结构耗时: {save_end - save_start:.6f}秒")
            print(f"图结构已保存到: {output_json}")
            
            # 加载模型
            load_start = time.time()
            print(f"正在加载模型权重: {checkpoint_path}")
            from src.models.brepMFR.brepseg_model import BrepSeg
            
            # 构建args对象
            args = _build_args_from_config()
            
            # 加载模型
            model = BrepSeg.load_from_checkpoint(
                checkpoint_path,
                map_location="cuda" if torch.cuda.is_available() else "cpu",
                args=args,
                strict=False  # 忽略模型中不存在的参数，如domain_adv
            )
            model.eval()
            load_end = time.time()
            print(f"模型加载耗时: {load_end - load_start:.6f}秒")
            print("模型加载完成")
            
            # 预处理数据
            preprocess_start = time.time()
            print("正在预处理数据...")
            input_data = self.preprocess_graph(graph_data)
            
            # 将数据移动到模型所在的设备
            device = next(model.parameters()).device
            for key, value in input_data.items():
                if isinstance(value, torch.Tensor):
                    input_data[key] = value.to(device)
            preprocess_end = time.time()
            print(f"数据预处理耗时: {preprocess_end - preprocess_start:.6f}秒")
            
            # 模型推理
            inference_start = time.time()
            print("正在进行模型推理...")
            with torch.no_grad():
                # 调用模型的brep_encoder获取节点嵌入和图嵌入
                node_emb, graph_emb = model.brep_encoder(input_data, last_state_only=True)
                
                # 处理节点嵌入
                node_emb = node_emb[0].permute(1, 0, 2)  # node_emb [batch_size, max_node_num+1, dim] with global node dim=0
                node_emb = node_emb[:, 1:, :]            # node_emb [batch_size, max_node_num, dim] without global node
                padding_mask = input_data["padding_mask"]     # [batch_size, max_node_num]
                node_pos = torch.where(padding_mask == False)  # [(batch_size, node_index)]
                node_z = node_emb[node_pos]  # [total_nodes, dim_z]
                padding_mask_ = ~padding_mask
                num_nodes_per_graph = torch.sum(padding_mask_.long(), dim=-1)  # [batch_size]
                graph_z = graph_emb.repeat_interleave(num_nodes_per_graph, dim=0).to(graph_emb.device)
                
                # 使用注意力机制融合节点嵌入和图嵌入
                z = model.attention([node_z, graph_z])
                
                # 使用分类器预测每个面的类别
                node_seg = model.classifier(z)  # [total_nodes, 1] for binary classification
                
                # 获取预测结果
                if model.num_classes == 2:
                    # For binary classification, use sigmoid and threshold at 0.5
                    predictions = (torch.sigmoid(node_seg) > 0.5).float().squeeze(1).long()
                else:
                    # For multi-class classification, use argmax
                    predictions = torch.argmax(node_seg, dim=-1)
                # 确保只有当 predictions 是 PyTorch 张量时，才调用 cpu().numpy()
                if isinstance(predictions, torch.Tensor):
                    predictions = predictions.cpu().numpy()
            inference_end = time.time()
            print(f"模型推理耗时: {inference_end - inference_start:.6f}秒")
            
            # 识别圆角（类别1表示圆角，0表示非圆角）
            # 注意：这里可以根据需要修改类别索引
            FILLET_CLASS = MANUAL_PARAMS["fillet_class"]
            fillet_faces = [i for i, pred in enumerate(predictions) if pred == FILLET_CLASS]
            print(f"识别到 {len(fillet_faces)} 个圆角面")
            
            # 保存推理结果
            save_pred_start = time.time()
            output_json = os.path.join(output_dir, "temp_model_predictions.json")
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump({
                    "predictions": predictions.tolist() if hasattr(predictions, 'tolist') else predictions,
                    "fillet_faces": fillet_faces
                }, f, indent=2, ensure_ascii=False)
            save_pred_end = time.time()
            print(f"保存推理结果耗时: {save_pred_end - save_pred_start:.6f}秒")
            print(f"推理结果已保存到: {output_json}")
            
            # 可视化圆角面
            if fillet_faces:
                vis_start = time.time()
                print("正在可视化圆角面...")
                # 使用NCTI的API高亮显示圆角面
                try:
                    # 使用SelectionManager来管理选择的对象和单元格ID
                    sel = self.NCTI.SelectionManager(self.doc)
                    obj_names = []
                    cell_ids = []
                    
                    # 为每个圆角面添加到选择列表
                    for face_id in fillet_faces:
                        print(f"高亮显示圆角面：{face_id}")
                        obj_names.append(self.name)
                        cell_ids.append(face_id)
                    
                    # 清除之前的选择
                    sel.ClearSelected()
                    
                    # 设置选择
                    sel.ObjectNames = obj_names
                    sel.CellIDs = cell_ids
                    
                    # 高亮显示选择的面
                    sel.SetSelected()
                    
                    print(f"成功高亮显示 {len(fillet_faces)} 个圆角面")
                except Exception as e:
                    print(f"高亮显示圆角面时出错：{e}")
                    import traceback
                    traceback.print_exc()
                vis_end = time.time()
                print(f"可视化圆角面耗时: {vis_end - vis_start:.6f}秒")
            
            # 更新文档
            update_start = time.time()
            print("正在更新文档...")
            self.doc.Update()
            self.doc.Zoom()
            update_end = time.time()
            print(f"更新文档耗时: {update_end - update_start:.6f}秒")
            
            # 显示消息
            total_end_time = time.time()
            print(f"圆角识别总耗时: {total_end_time - total_start_time:.6f}秒")
            wx.MessageBox(f"圆角识别完成，共识别到 {len(fillet_faces)} 个圆角面！\n总耗时: {total_end_time - total_start_time:.2f}秒", "提示", wx.OK | wx.ICON_INFORMATION)
            
        except Exception as e:
            print(f"圆角识别时出错: {e}")
            import traceback
            traceback.print_exc()
            wx.MessageBox(f"圆角识别失败: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
        finally:
            # 恢复原始工作目录
            pass
    
    def extract_graph_structure(self, ai, face_ids):
        """从AI模型中提取图结构数据
        
        Args:
            ai: NCTI.AiModel实例
            face_ids: 面ID列表（此参数保留用于向后兼容，实际不再使用）
            
        Returns:
            dict: 符合BrepMFR格式的图结构JSON数据
        """
        try:
            # 导入并使用BrepMFRExtractor
            from src.data_utils.transforms.step2graph_mfr_ncti import BrepMFRExtractor
            
            # 创建提取器实例，传入已初始化的NCTI
            extractor = BrepMFRExtractor(config=CONFIG, ncti=self.NCTI)
            
            # 使用process_from_doc方法处理已有的文档
            return extractor.process_from_doc(self.doc, self.name, ai)
            
        except Exception as e:
            print(f"Error extracting graph structure: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def preprocess_graph(self, graph_data):
        """预处理图数据，转换为模型输入格式"""
        import dgl
        
        # 从graph_data中提取数据
        num_nodes = graph_data["graph"]["num_nodes"]
        num_edges = graph_data["graph"]["num_edges"]
        src_nodes = graph_data["graph"]["src_nodes"]
        dst_nodes = graph_data["graph"]["dst_nodes"]
        
        # 创建DGL图
        graph = dgl.graph((src_nodes, dst_nodes), num_nodes=num_nodes)
        
        # 添加节点特征
        # 从graph_data中提取实际的节点特征
        node_data = graph_data.get("node_data", {})
        
        # 添加UV网格特征 (x)
        # 格式: [num_nodes, 5, 5, 7]
        if "x" in node_data and node_data["x"]:
            # 转换为张量
            graph.ndata["x"] = torch.tensor(node_data["x"], dtype=torch.float32)
        else:
            # 如果没有x特征，使用默认值
            graph.ndata["x"] = torch.zeros(num_nodes, 5, 5, 7, dtype=torch.float32)
        
        # 添加面面积 (y)
        if "y" in node_data and node_data["y"]:
            graph.ndata["y"] = torch.tensor(node_data["y"], dtype=torch.float32)
        else:
            graph.ndata["y"] = torch.zeros(num_nodes, dtype=torch.float32)
        
        # 添加面类型 (z)
        # 面几何类型: 0: 平面, 1: 圆柱面, 2: 圆锥面, 3: 球面, 4: 环面
        if "z" in node_data and node_data["z"]:
            graph.ndata["z"] = torch.tensor(node_data["z"], dtype=torch.long)
        else:
            graph.ndata["z"] = torch.zeros(num_nodes, dtype=torch.long)
        
        # 添加环数量 (l)
        if "l" in node_data and node_data["l"]:
            graph.ndata["l"] = torch.tensor(node_data["l"], dtype=torch.long)
        else:
            graph.ndata["l"] = torch.zeros(num_nodes, dtype=torch.long)
        
        # 添加邻接面数量 (a)
        if "a" in node_data and node_data["a"]:
            graph.ndata["a"] = torch.tensor(node_data["a"], dtype=torch.long)
        else:
            graph.ndata["a"] = torch.zeros(num_nodes, dtype=torch.long)
        
        # 添加面特征标签 (f)
        if "f" in node_data and node_data["f"]:
            graph.ndata["f"] = torch.tensor(node_data["f"], dtype=torch.long)
        else:
            graph.ndata["f"] = torch.zeros(num_nodes, dtype=torch.long)
        
        # 添加边特征
        edge_data = graph_data.get("edge_data", {})
        
        # 添加边的网格特征 (x)
        # 格式: [num_edges, 5, 7]
        if "x" in edge_data and edge_data["x"]:
            graph.edata["x"] = torch.tensor(edge_data["x"], dtype=torch.float32)
        else:
            graph.edata["x"] = torch.zeros(num_edges, 5, 7, dtype=torch.float32)
        
        # 添加边长度 (l)
        if "l" in edge_data and edge_data["l"]:
            graph.edata["l"] = torch.tensor(edge_data["l"], dtype=torch.float32)
        else:
            graph.edata["l"] = torch.zeros(num_edges, dtype=torch.float32)
        
        # 添加边类型 (t)
        if "t" in edge_data and edge_data["t"]:
            graph.edata["t"] = torch.tensor(edge_data["t"], dtype=torch.long)
        else:
            graph.edata["t"] = torch.zeros(num_edges, dtype=torch.long)
        
        # 添加边角度 (a)
        if "a" in edge_data and edge_data["a"]:
            graph.edata["a"] = torch.tensor(edge_data["a"], dtype=torch.float32)
        else:
            graph.edata["a"] = torch.zeros(num_edges, dtype=torch.float32)
        
        # 添加边连接信息 (c)
        if "c" in edge_data and edge_data["c"]:
            graph.edata["c"] = torch.tensor(edge_data["c"], dtype=torch.long)
        else:
            graph.edata["c"] = torch.zeros(num_edges, dtype=torch.long)
        
        # 创建PyG图对象
        class PYGGraph:
            def __init__(self):
                self.graph = graph
                self.node_data = graph.ndata["x"]
                self.face_area = graph.ndata["y"]
                self.face_type = graph.ndata["z"]
                self.face_loop = graph.ndata["l"]
                self.face_adj = graph.ndata["a"]
                self.edge_data = graph.edata["x"]
                self.edge_type = graph.edata["t"]
                self.edge_len = graph.edata["l"]
                self.edge_ang = graph.edata["a"]
                self.edge_conv = graph.edata["c"]
                self.node_degree = torch.zeros(num_nodes, dtype=torch.long)
                self.attn_bias = torch.zeros([num_nodes + 1, num_nodes + 1], dtype=torch.float)
                
                # 从graph_data中提取其他必要的特征
                graph_labels = graph_data.get("graph_labels", {})
                
                # 添加空间位置特征
                if "spatial_pos" in graph_labels and graph_labels["spatial_pos"]:
                    self.spatial_pos = torch.tensor(graph_labels["spatial_pos"], dtype=torch.long)
                else:
                    self.spatial_pos = torch.zeros([num_nodes, num_nodes], dtype=torch.long)
                
                # 添加d2距离特征
                if "d2_distance" in graph_labels and graph_labels["d2_distance"]:
                    self.d2_distance = torch.tensor(graph_labels["d2_distance"], dtype=torch.float32)
                else:
                    self.d2_distance = torch.zeros([num_nodes, num_nodes, 64], dtype=torch.float32)
                
                # 添加角度距离特征
                if "angle_distance" in graph_labels and graph_labels["angle_distance"]:
                    self.angle_distance = torch.tensor(graph_labels["angle_distance"], dtype=torch.float32)
                else:
                    self.angle_distance = torch.zeros([num_nodes, num_nodes, 64], dtype=torch.float32)
                
                # 添加边路径特征
                if "edges_path" in graph_labels and graph_labels["edges_path"]:
                    self.edge_path = torch.tensor(graph_labels["edges_path"], dtype=torch.long)
                else:
                    self.edge_path = torch.zeros([num_nodes, num_nodes, 16], dtype=torch.long)
                
                self.label_feature = graph.ndata["f"]
                self.data_id = 0
        
        pyg_graph = PYGGraph()
        
        # 使用collator函数对数据进行预处理
        # 由于collator函数需要处理批量数据，这里需要将单个图数据转换为批量数据
        items = [pyg_graph]
        batch_data = self.collator(items, multi_hop_max_dist=16, spatial_pos_max=64)
        
        return batch_data
    
    def collator(self, items, multi_hop_max_dist=16, spatial_pos_max=32):
        """数据整理函数"""
        from src.data_utils.dataloader.brepmfr_collator import collator as original_collator
        return original_collator(items, multi_hop_max_dist, spatial_pos_max)


if __name__ == '__main__':
    # 1，确认炎核开发引擎的安装路径，请按需配置实际路径
    # 以下是当前用户默认设置下安装的路径，一般情况下是可用的：
    # dll_path = os.path.join(os.path.expanduser('~'), 'AppData/Local/Programs/YHCppSDK-Community/SDK/bin/RelWithDebInfo')
    dll_path = r'D:\tools\YHCppSDK-Community\SDK\bin\RelWithDebInfo'
    # 以下是admin用户默认设置下安装的参考路径，请根据实际用户名确认该路径有效：
    # dll_path = 'C:/Users/Admin/AppData/Local/Programs/YHCppSDK-Community/SDK/bin/RelWithDebInfo'
    # 如果自行安装至如下所示的其它目录，请自行修改，并将目录分隔符号反斜杠"\"修改为正斜杠"/"：
    # dll_path = 'C:/Program Files (x86)/YHCppSDK-Community/SDK/bin/RelWithDebInfo'
    if not os.path.exists(dll_path):
        # messagebox.showerror("安装路径检索错误",
        #                      "操作失败！请检查炎核开发引擎是否已正确安装、其安装路径与dll_path声明是否匹配。", icon='error')
        sys.exit(1)

    # 2，根据指定路径加载炎核开发引擎
    NCTI = init_NCTI_Config(dll_path)
    if None == NCTI:
        sys.exit(1)
    doc = NCTI.Document()

    # 3，准备工作完成，启动wxPython应用界面
    app = wx.App()
    frame = MainWindow(NCTI, doc)
    app.MainLoop()