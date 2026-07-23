import os
import tempfile
import traceback

import wx
import wx.aui

from config.config_load import global_scope
from dialog.export_file import export_file_dialog
from dialog.import_file import import_file_dialog
from dialog.open_ncti_file import open_ncti_file_dialog
from dialog.save_ncit_file import save_ncit_file_dialog
from dialog.select_file_base import select_file_base_dialog
from dialog.select_infer_method import select_infer_method_dialog
from dialog.show_features import show_features_dialog
from function.on_category_file import set_color
from function.on_find_cone import find_cone_by_points
from function.on_find_cylinder import find_cylinder_by_points, find_cylinder_by_normals, \
    find_cylinder_by_points_and_normals
from function.on_find_fillet_by_ai import find_feature_by_ai, filter_by_face_type_ncti, filter_by_cylinder
from function.on_find_plane import find_plane_by_points, find_plane_by_normals, find_plane_by_points_and_normals, \
    find_plane_by_ncti
from function.on_find_fillet import find_fillet_with_dialog, find_fillet_compound, find_fillet_by_geo
# from function.on_find_fillet_by_ai import find_fillet_by_ai, filter_by_face_type, filter_by_face_type_ncti, \
#     filter_by_plane, filter_by_cylinder, filter_by_cone
from function.on_new_assembly import new_assembly_with_dialog
from function.on_new_document import new_document_with_dialog, new_document_function
from function.on_remove_feature import remove_feature
from ui.assembly_panel import create_assembly_panel
from ui.property_panel import create_property_panel
from ui.viewer import CADViewer
from utils.reindex import IndexManager
from function.on_find_blind_hole_stp import find_blind_hole_by_stp #STP盲孔识别(可更改映射逻辑，on_find_blind_hole_stp/on_find_blind_hole_stp_geometric)
from function.on_find_countersunk_hole_stp import find_countersunk_hole_by_stp
from function.on_find_through_step_stp import find_through_step_by_stp #STP双侧通槽台阶识别
from function.on_find_through_step_ncti import find_through_step_by_ncti #NCTI-native通槽台阶识别
from function.on_find_through_step_featurefox import find_through_step_by_featurefox #FeatureFox数据驱动通槽识别
from function.on_find_through_step_featurefox_ncti import find_through_step_by_featurefox_ncti #FeatureFox-NCTI数据驱动通槽识别(零映射)

# from ai.brep_mfr.models.brepseg_model import BrepSeg


class CAEPlatform(wx.Frame):
    def __init__(self):
        super().__init__(None, title="炎核 几何特征识别清理工具", size=(1200, 800))

        if not self.init_cad_env():
            return
        self.init_ai_env()

        self.icon_dir = "icons"
        if not os.path.exists(self.icon_dir):
            os.makedirs(self.icon_dir)
        icon = wx.Icon("icons/ncti.ico", wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)

        # 初始化状态栏
        self.init_status_bar()

        # 初始化主布局
        # self.init_main_layout()
        wx.CallAfter(self.init_main_layout)

        # self.bind_evt()
        wx.CallAfter(self.bind_evt)

        # 显示窗口
        self.Centre()
        self.Show()

    def init_cad_env(self):
        global global_scope
        if "NCTI" in global_scope:
            self.NCTI = global_scope["NCTI"]
            self.doc = global_scope["doc"]
            self.selected_feature = []
            self.current_stp_path = ""
            return True
        else:
            return False

    def init_ai_env(self):
        self.pretrained_model_round = os.path.join("ai",
                                                   "AAGNet_infer",
                                                   "weights",
                                                   "weight_round.pth")
        # self.pretrained_model_round = os.path.join("ai",
        #                                            "AAGNet_infer",
        #                                            "weights",
        #                                            "weight_round.onnx")
        self.pretrained_model_chamfer = os.path.join("ai",
                                                   "AAGNet_infer",
                                                   "weights",
                                                   "chamfer1 dropout0.25.pth")
                                                #    "weight_chamfer.pth")
        self.pretrained_model_blind_hole = os.path.join("ai",
                                                   "AAGNet_infer",
                                                   "weights",
                                                   "true_best_model.pth")
        self.stat_path_round = os.path.join("ai",
                                      "AAGNet_infer",
                                      "weights",
                                      "attr_stat_ncti_62k.json")
        self.stat_path_chamfer = os.path.join("ai",
                                      "AAGNet_infer",
                                      "weights",
                                      "attr_stat_data2+part_chamfer.json")
        self.stat_path_blind_hole = os.path.join("ai",
                                      "AAGNet_infer",
                                      "weights",
                                      "true_attr_stat.json")
        self.pretrained_model_blind_hole_public = os.path.join("ai",
                                                   "AAGNet_infer",
                                                   "weights",
                                                   "weight_blind_hole.pth")
        self.stat_path_blind_hole_public = os.path.join("ai",
                                      "AAGNet_infer",
                                      "weights",
                                      "attr_stat_blind_hole.json")
        self.infer_method = "AAG"

        # 用户通过「选择预训练模型」导入的自定义模型（与内置各特征默认权重相互独立，不覆盖）
        self.pretrained_model_custom = None
        self.stat_path_custom = None

        self.pretrained_mfr_model_round = os.path.join("ai",
                                                       "brep_mfr",
                                                       "weights",
                                                       "best.ckpt")
        # self.mfr_model = BrepSeg.load_from_checkpoint(
        #         self.pretrained_mfr_model_round,
        #         map_location="cuda" if torch.cuda.is_available() else "cpu"
        #     )

    def init_status_bar(self):
        """初始化状态栏"""
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetStatusText("Kernel: OCC Mesh: GMSH")

    def init_main_layout(self):
        """初始化主布局"""
        self.scale_factor = self.GetDPIScaleFactor()
        print(f"scale factor:{self.scale_factor}")

        # 创建AUI管理器 - 这是整个应用的布局管理器
        self.aui_manager = wx.aui.AuiManager(self)

        # 创建顶部选项卡面板
        top_panel = wx.Panel(self)
        top_sizer = wx.BoxSizer(wx.VERTICAL)

        # 创建选项卡控件
        self.notebook = wx.Notebook(top_panel, wx.ID_ANY,
                                    style=wx.NB_TOP)

        # 创建各个选项卡面板
        self.file_tab = wx.Panel(self.notebook)
        self.general_tab = wx.Panel(self.notebook)
        self.ai_tab = wx.Panel(self.notebook)
        # self.setting_tab = wx.Panel(self.notebook)

        # 添加选项卡到notebook
        self.notebook.AddPage(self.file_tab, "文件")
        self.notebook.AddPage(self.general_tab, "常规")
        self.notebook.AddPage(self.ai_tab, "AI")
        # self.notebook.AddPage(self.setting_tab, "设置")

        # 绑定选项卡切换事件
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)

        # 初始化各个选项卡的内容
        self.init_file_tab_content()
        self.init_general_tab_content()
        self.init_ai_tab_content()
        # self.init_setting_tab_content()

        # 将notebook添加到顶部面板
        top_sizer.Add(self.notebook, 1, wx.EXPAND)
        top_panel.SetSizer(top_sizer)

        # 创建中央3D视图区域
        self.cad_view = CADViewer(parent=self)
        self.hwnd = int(self.cad_view.GetId())

        # 使用AUI管理器添加所有面板，设置正确的层级关系
        # 计算顶部面板的最佳高度，基于缩放因子
        top_panel_height = max(100, int(100*self.scale_factor))
        print(f"top panel height:{top_panel_height}")
        self.aui_manager.AddPane(top_panel,
                                 wx.aui.AuiPaneInfo().Top().
                                 CaptionVisible(False).
                                 CloseButton(False).
                                 Floatable(False).
                                 DockFixed(True).
                                 Layer(0).
                                 Position(0).
                                 BestSize(-1, top_panel_height).
                                 MinSize(-1, top_panel_height))

        self.aui_manager.AddPane(self.cad_view,
                                 wx.aui.AuiPaneInfo().Center().
                                 CaptionVisible(False).
                                 CloseButton(False).
                                 Floatable(False).
                                 DockFixed(True).
                                 Layer(1).
                                 Position(1))

        # 更新AUI布局，这一步非常重要，不能省略
        self.aui_manager.Update()

    def on_tab_change(self, event):
        """选项卡切换事件处理"""
        page_index = event.GetSelection()
        page_title = self.notebook.GetPageText(page_index)

        # 更新状态栏
        self.status_bar.SetStatusText(f"当前页面: {page_title}")

        # 给当前页面设置焦点
        self.notebook.GetCurrentPage().SetFocus()

        # 跳过事件，让系统继续处理
        event.Skip()

    def init_file_tab_content(self):
        """初始化文件选项卡内容"""
        # 创建文件选项卡的工具栏
        file_toolbar = wx.ToolBar(self.file_tab, wx.ID_ANY,
                                  style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT )
        # 设置工具 bitmap 大小，根据缩放因子调整
        bitmap_size = max(36, int(36*self.scale_factor))  # 减小基础大小，确保在高缩放级别下不会过大
        print(f"bitmap size:{bitmap_size}")
        file_toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        # 设置工具栏的垂直尺寸，确保有足够空间显示文字和图标
        toolbar_height = max(60, int(80*self.scale_factor))  # 增加最小高度
        print(f"toolbar height:{toolbar_height}")
        file_toolbar.SetMinSize((-1, toolbar_height))
        # 设置工具栏的最佳尺寸
        file_toolbar.SetSize((-1, toolbar_height))

        self.button_new_doc = wx.NewIdRef()
        self.button_import_part = wx.NewIdRef()
        self.button_new_assembly = wx.NewIdRef()
        self.button_open_file = wx.NewIdRef()
        self.button_save_file = wx.NewIdRef()
        self.button_close_doc = wx.NewIdRef()
        self.button_export_file = wx.NewIdRef()
        self.button_remove_face = wx.NewIdRef()

        # 文件选项卡按钮列表
        file_buttons = [
            ("创建装配", self.button_new_assembly),
            ("创建零件", self.button_new_doc),  # 使用固定ID，方便后续绑定事件
            ("添加装配", wx.ID_ANY),
            ("添加零件", wx.ID_ANY),
            ("导入零件", wx.ID_ANY),
            ("删除零件", self.button_remove_face),
            (wx.ID_SEPARATOR, None),
            ("打开", self.button_open_file),
            ("保存", self.button_save_file),
            ("关闭文档", self.button_close_doc),
            (wx.ID_SEPARATOR, None),
            ("导入", self.button_import_part),
            ("导出", self.button_export_file),
        ]

        for btn in file_buttons:
            if btn[0] == wx.ID_SEPARATOR:
                file_toolbar.AddSeparator()
            else:
                # 获取或创建图标
                icon = self.load_icon(btn[0])
                # 直接在工具栏中添加工具，会显示图标
                file_toolbar.AddTool(btn[1], btn[0], icon, shortHelp=btn[0])

        file_toolbar.Bind(wx.EVT_TOOL, self.on_new_part_click, id=self.button_new_doc)
        file_toolbar.Bind(wx.EVT_TOOL, self.on_import_part_button_click, id=self.button_import_part)
        file_toolbar.Bind(wx.EVT_TOOL, self.on_new_assembly_click, id=self.button_new_assembly)
        file_toolbar.Bind(wx.EVT_TOOL, self.on_open_file_click, id=self.button_open_file)
        file_toolbar.Bind(wx.EVT_TOOL, self.on_save_file_click, id=self.button_save_file)
        file_toolbar.Bind(wx.EVT_TOOL, self.on_close_doc_click, id=self.button_close_doc)
        file_toolbar.Bind(wx.EVT_TOOL, self.on_export_file_click, id=self.button_export_file)
        file_toolbar.Bind(wx.EVT_TOOL, self.on_remove_face_export_part_click, id=self.button_remove_face)

        file_toolbar.Realize()

        # 设置文件选项卡的布局
        file_sizer = wx.BoxSizer(wx.VERTICAL)
        file_sizer.Add(file_toolbar, 0, wx.EXPAND)
        self.file_tab.SetSizer(file_sizer)
        self.file_tab.Layout()

    def init_general_tab_content(self):
        """初始化常规选项卡内容"""
        # 创建垂直布局管理器
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建水平工具栏
        toolbar_panel = wx.Panel(self.general_tab)
        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 显示模式组
        show_mode_group = wx.StaticBoxSizer(wx.StaticBox(toolbar_panel, wx.ID_ANY, "显示模式"), wx.HORIZONTAL)
        
        # 显示模式 - 体
        self.show_body = wx.CheckBox(toolbar_panel, wx.ID_ANY, "体")
        self.show_body.SetValue(False)
        show_mode_group.Add(self.show_body, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        # 显示模式 - 面
        self.show_face = wx.CheckBox(toolbar_panel, wx.ID_ANY, "面")
        show_mode_group.Add(self.show_face, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        # 显示模式 - 线
        self.show_edge = wx.CheckBox(toolbar_panel, wx.ID_ANY, "线")
        show_mode_group.Add(self.show_edge, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        # 显示模式 - 点
        self.show_vertex = wx.CheckBox(toolbar_panel, wx.ID_ANY, "点")
        show_mode_group.Add(self.show_vertex, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        toolbar_sizer.Add(show_mode_group, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar_sizer.AddSpacer(20)
        
        # 选择模式组
        select_mode_group = wx.StaticBoxSizer(wx.StaticBox(toolbar_panel, wx.ID_ANY, "选择模式"), wx.HORIZONTAL)
        
        # 选择模式 - 体
        self.select_body = wx.CheckBox(toolbar_panel, wx.ID_ANY, "体")
        self.select_body.SetValue(True)
        select_mode_group.Add(self.select_body, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        # 选择模式 - 面
        self.select_face = wx.CheckBox(toolbar_panel, wx.ID_ANY, "面")
        self.select_face.SetValue(True)
        select_mode_group.Add(self.select_face, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        # 选择模式 - 线
        self.select_edge = wx.CheckBox(toolbar_panel, wx.ID_ANY, "线")
        self.select_edge.SetValue(True)
        select_mode_group.Add(self.select_edge, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        # 选择模式 - 点
        self.select_vertex = wx.CheckBox(toolbar_panel, wx.ID_ANY, "点")
        self.select_vertex.SetValue(True)
        select_mode_group.Add(self.select_vertex, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        
        toolbar_sizer.Add(select_mode_group, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar_sizer.AddSpacer(20)
        
        toolbar_panel.SetSizer(toolbar_sizer)
        toolbar_panel.Layout()
        
        main_sizer.Add(toolbar_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        self.general_tab.SetSizer(main_sizer)
        self.general_tab.Layout()

    def init_ai_tab_content(self):
        """初始化AI选项卡内容"""
        # 创建AI选项卡的工具栏
        ai_toolbar = wx.ToolBar(self.ai_tab, wx.ID_ANY, style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)
        # 设置工具 bitmap 大小，根据缩放因子调整
        bitmap_size = max(28, int(28*self.scale_factor))  # 减小基础大小，确保在高缩放级别下不会过大
        ai_toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        # 设置工具栏的垂直尺寸，确保有足够空间显示文字和图标
        toolbar_height = max(60, int(80*self.scale_factor))  # 增加最小高度
        ai_toolbar.SetMinSize((-1, toolbar_height))
        # 设置工具栏的最佳尺寸
        ai_toolbar.SetSize((-1, toolbar_height))

        self.button_find_fillet = wx.NewIdRef()
        self.button_remove_feature = wx.NewIdRef()
        self.button_find_fillet_ai = wx.NewIdRef()
        self.button_find_fillet_hyper = wx.NewIdRef()
        self.button_find_plane_by_points = wx.NewIdRef()
        self.button_find_plane_by_normals = wx.NewIdRef()
        self.button_find_plane_by_points_and_normals = wx.NewIdRef()
        self.button_find_cylinder_by_points = wx.NewIdRef()
        self.button_find_cylinder_by_normal = wx.NewIdRef()
        self.button_find_cylinder_by_points_and_normal = wx.NewIdRef()
        self.button_find_cone = wx.NewIdRef()
        self.button_find_chamfer_ai = wx.NewIdRef()
        self.button_find_blind_hole_ai = wx.NewIdRef()
        self.button_find_blind_hole_stp = wx.NewIdRef()
        self.button_find_countersunk_hole_stp = wx.NewIdRef()
        self.button_find_through_step_stp = wx.NewIdRef()
        self.button_find_through_step_ncti = wx.NewIdRef()
        self.button_find_through_step_featurefox = wx.NewIdRef()
        self.button_find_through_step_featurefox_ncti = wx.NewIdRef()
        self.button_export_feature = wx.NewIdRef()

        # AI选项卡按钮列表
        ai_buttons = [
            ("几何圆角识别", self.button_find_fillet),
            ("AI圆角识别", self.button_find_fillet_ai),
            ("混合圆角识别", self.button_find_fillet_hyper),
            (wx.ID_SEPARATOR, None),

            ("几何倒角识别", self.button_find_plane_by_points),#("点集找平面", self.button_find_plane_by_points),
            ("AI倒角识别", self.button_find_chamfer_ai),#("法线找平面", self.button_find_plane_by_normals),
            ("混合倒角识别", self.button_find_plane_by_points_and_normals),#("点集+法线找平面", self.button_find_plane_by_points_and_normals),
            (wx.ID_SEPARATOR, None),

            ("开源数据AI盲孔识别", self.button_find_cone),#("找圆锥面", self.button_find_cone),
            ("真实数据AI盲孔识别", self.button_find_blind_hole_ai),#("法线找椭圆面", self.button_find_cylinder_by_normal),
            ("文本规则盲孔识别", self.button_find_blind_hole_stp), #STP盲孔识别
            ("文本规则沉头孔识别", self.button_find_countersunk_hole_stp),
            ("文本规则通槽台阶识别", self.button_find_through_step_stp), #STP通槽台阶识别
            ("FeatureFox通槽识别", self.button_find_through_step_featurefox), #FeatureFox数据驱动通槽识别(STEP版)
            ("FeatureFox通槽识别(NCTI)", self.button_find_through_step_featurefox_ncti), #FeatureFox数据驱动通槽识别(NCTI零映射版)
            ("NCTI通槽台阶识别", self.button_find_through_step_ncti), #NCTI-native通槽台阶识别
            (wx.ID_SEPARATOR, None),

            ("移除特征", self.button_remove_feature),
            ("导出特征", self.button_export_feature),
        ]

        for btn in ai_buttons:
            if btn[0] == wx.ID_SEPARATOR:
                ai_toolbar.AddSeparator()
            else:
                # 获取或创建图标
                icon_name = "混合盲孔识别" if btn[0] in {"STP盲孔识别", "沉头孔识别"} else btn[0]
                icon = self.load_icon(icon_name, target_size=bitmap_size)
                ai_toolbar.AddTool(btn[1], btn[0], icon, shortHelp=btn[0])

        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_fillet_click, id=self.button_find_fillet)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_remove_feature_click, id=self.button_remove_feature)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_export_feature_click, id=self.button_export_feature)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_fillet_by_ai_click, id=self.button_find_fillet_ai)
        # ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_fillet_by_ai_click_mfr, id=self.button_find_fillet_ai)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_fillet_hyper_click, id=self.button_find_fillet_hyper)
        # ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_plane_by_points_click, id=self.button_find_plane_by_points)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_chamfer_by_ai_click, id=self.button_find_chamfer_ai)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_blind_hole_by_ai_click, id=self.button_find_blind_hole_ai)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_blind_hole_by_stp_click, id=self.button_find_blind_hole_stp)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_countersunk_hole_by_stp_click, id=self.button_find_countersunk_hole_stp)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_through_step_by_stp_click, id=self.button_find_through_step_stp)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_through_step_by_featurefox_click, id=self.button_find_through_step_featurefox)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_through_step_by_featurefox_ncti_click, id=self.button_find_through_step_featurefox_ncti)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_through_step_by_ncti_click, id=self.button_find_through_step_ncti)
        # ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_plane_by_points_and_normals_click, id=self.button_find_plane_by_points_and_normals)
        # ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_cylinder_by_points_click, id=self.button_find_cylinder_by_points)
        # ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_cylinder_by_normal_click, id=self.button_find_cylinder_by_normal)
        # ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_cylinder_by_points_and_normal_click, id=self.button_find_cylinder_by_points_and_normal)
        # ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_cone_by_points_click, id=self.button_find_cone)
        ai_toolbar.Bind(wx.EVT_TOOL, self.on_find_blind_hole_public_click, id=self.button_find_cone)

        ai_toolbar.Realize()

        # 设置AI选项卡的布局
        ai_sizer = wx.BoxSizer(wx.VERTICAL)
        ai_sizer.Add(ai_toolbar, 0, wx.EXPAND)
        self.ai_tab.SetSizer(ai_sizer)
        self.ai_tab.Layout()

    def init_setting_tab_content(self):
        setting_toolbar = wx.ToolBar(self.setting_tab, wx.ID_ANY,
                                     style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT | wx.TB_HORZ_LAYOUT)
        # 设置工具 bitmap 大小，根据缩放因子调整
        bitmap_size = max(24, int(24*self.scale_factor))  # 减小基础大小，确保在高缩放级别下不会过大
        setting_toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        # 设置工具栏的垂直尺寸，确保有足够空间显示文字和图标
        toolbar_height = max(60, int(80*self.scale_factor))  # 增加最小高度
        setting_toolbar.SetMinSize((-1, toolbar_height))
        # 设置工具栏的最佳尺寸
        setting_toolbar.SetSize((-1, toolbar_height))
        self.button_select_pretrained_model = wx.NewIdRef()
        self.button_select_infer_method = wx.NewIdRef()
        setting_buttons = [
            ("模型加载", self.button_select_pretrained_model),
            ("识别算法", self.button_select_infer_method)
        ]
        for btn in setting_buttons:
            if btn[0] == wx.ID_SEPARATOR:
                setting_toolbar.AddSeparator()
            else:
                # 获取或创建图标
                icon = self.load_icon(btn[0])
                setting_toolbar.AddTool(btn[1], btn[0], icon, shortHelp=btn[0])
        setting_toolbar.Bind(wx.EVT_TOOL, self.on_select_model_click, id=self.button_select_pretrained_model)
        setting_toolbar.Bind(wx.EVT_TOOL, self.on_select_infer_click, id=self.button_select_infer_method)

        setting_toolbar.Realize()

        # 设置AI选项卡的布局
        ai_sizer = wx.BoxSizer(wx.VERTICAL)
        ai_sizer.Add(setting_toolbar, 0, wx.EXPAND)
        self.setting_tab.SetSizer(ai_sizer)
        self.setting_tab.Layout()

    def bind_evt(self):
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.Bind(wx.EVT_SIZE, self.on_resize_and_move)
        self.Bind(wx.EVT_MOVE, self.on_resize_and_move)

        # 绑定勾选事件
        self.show_body.Bind(wx.EVT_CHECKBOX, self.on_show_body)
        self.show_face.Bind(wx.EVT_CHECKBOX, self.on_show_face)
        self.show_edge.Bind(wx.EVT_CHECKBOX, self.on_show_edge)
        self.show_vertex.Bind(wx.EVT_CHECKBOX, self.on_show_vertex)
        self.select_body.Bind(wx.EVT_CHECKBOX, self.on_select_body)
        self.select_face.Bind(wx.EVT_CHECKBOX, self.on_select_face)
        self.select_edge.Bind(wx.EVT_CHECKBOX, self.on_select_edge)
        self.select_vertex.Bind(wx.EVT_CHECKBOX, self.on_select_vertex)

    def on_resize_and_move(self, event):
        self.Refresh()
        self.cad_view.update_view()

    def load_icon(self, name, target_size=None):
        icon_path = os.path.join(self.icon_dir, f"{name}.png")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(self.icon_dir, f"ncti.ico")
        bmp = wx.Bitmap(icon_path)
        # 缩放到目标尺寸：ncti.ico 是 256×256、png 多为 48×48，不缩放会被大图撑爆按钮
        # （用 ncti.ico 兜底的通槽等按钮尤其明显，导致工具栏横向溢出）。
        if target_size is not None:
            img = bmp.ConvertToImage()
            img = img.Scale(target_size, target_size, wx.IMAGE_QUALITY_HIGH)
            bmp = wx.Bitmap(img)
        return bmp

    def bind_view(self, view):
        self.cad_view.view = view
        set_color(self)
        self.cad_view.update_doc(self)
        self.cad_view.update_view()

    def on_new_part_click(self, event):
        """创建零件按钮点击事件处理"""
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            self.doc.Close()
            view = new_document_with_dialog(self.NCTI, self.doc, self.cad_view.GetHandle(), self.scale_factor)
            self.current_stp_path = ""
            self.bind_view(view)
            self.status_bar.SetStatusText(f"新建零件文档")
        except Exception as e:
            self.status_bar.SetStatusText(f"新建零件文档失败:{e}")

    def on_new_assembly_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            self.doc.Close()
            view = new_assembly_with_dialog(self.NCTI, self.doc, self.cad_view.GetHandle(), self.scale_factor)
            self.current_stp_path = ""
            self.bind_view(view)
            self.status_bar.SetStatusText(f"新建装配文档")
        except Exception as e:
            self.status_bar.SetStatusText(f"新建装配文档失败:{e}")

    def on_import_part_button_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            filename_path = import_file_dialog(self.NCTI, self.doc)
            if filename_path:
                self.current_stp_path = filename_path
                self.cad_view.update_doc(self)
                self.cad_view.update_view()
                self.status_bar.SetStatusText(f"导入模型:{filename_path}")
        except Exception as e:
            self.status_bar.SetStatusText(f"导入文件失败:{e}")

    def on_export_file_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            filename_path = export_file_dialog(self.NCTI, self.doc)
            if filename_path:
                self.status_bar.SetStatusText(f"导出模型成功:{filename_path}")
        except Exception as e:
            self.status_bar.SetStatusText(f"没有导出文件:{e}")

    def on_save_file_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            save_ncit_file_dialog(self.NCTI, self.doc)
            self.status_bar.SetStatusText(f"保存文档")
        except Exception as e:
            self.status_bar.SetStatusText(f"保存文件失败:{e}")

    def on_open_file_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            view = open_ncti_file_dialog(self.NCTI, self.doc, self.cad_view.GetHandle())
            if view:
                self.current_stp_path = ""
                self.cad_view.view = view
                self.cad_view.update_doc(self)
                self.cad_view.update_view()
                self.status_bar.SetStatusText(f"打开文档")
        except Exception as e:
            self.status_bar.SetStatusText(f"打开文件失败:{e}")

    def on_close_doc_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            self.doc.Close()
            view = new_document_function(self.NCTI, self.doc, self.cad_view.GetHandle())
            self.current_stp_path = ""
            self.bind_view(view)
            self.set_select_mode()
            self.status_bar.SetStatusText(f"关闭文档")
        except Exception as e:
            self.status_bar.SetStatusText(f"关闭文档失败:{e}")

    def show_selection(self, obj_names, cell_ids):
        selection = self.NCTI.SelectionManager(self.doc)
        selection.ClearSelected()
        selection.ObjectNames = obj_names
        selection.CellIDs = cell_ids
        selection.SetSelected()
        self.selected_feature = [(obj_names[i], cell_id) for i, cell_id in enumerate(cell_ids)]

    def sync_selected_feature(self):
        selection = self.NCTI.SelectionManager(self.doc)
        if selection.ObjectNames and selection.CellIDs:
            self.selected_feature = list(zip(selection.ObjectNames, selection.CellIDs))

    def focus_selection(self, obj_names, cell_ids):
        self.show_selection(obj_names, cell_ids)
        # self.cad_view.view.Zoom(obj_names, cell_ids)
        # self.cad_view.view.FocusSelect()
        self.status_bar.SetStatusText(f"找到{len(cell_ids)}个特征")

    def on_find_fillet_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        # cell_ids, obj_names = find_fillet_with_dialog(self.NCTI, self.doc, self.scale_factor)
        cell_ids, obj_names = find_fillet_by_geo(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个倒圆角面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            wx.MessageBox(f"没有找到倒圆角面", "圆角识别", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"没有找到倒圆角面")

    def on_find_fillet_by_ai_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names, _, _, _, _ = find_feature_by_ai(self.NCTI, self.doc,
                                                         weight_path=self.pretrained_model_round,
                                                         min_faces_num=0,
                                                         max_faces_num=9,
                                                         stat_path=self.stat_path_round)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            print(f"obj names:{obj_names}\ncell_ids:{cell_ids}")
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个倒圆角面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            wx.MessageBox(f"没有找到倒圆角面", "圆角识别", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"没有找到倒圆角面")

    def on_find_chamfer_by_ai_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names, _, _, _, _ = find_feature_by_ai(self.NCTI, self.doc,
                                                         weight_path=self.pretrained_model_chamfer,
                                                         stat_path=self.stat_path_chamfer,
                                                         min_faces_num=0,
                                                         max_faces_num=9)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            print(f"obj names:{obj_names}\ncell_ids:{cell_ids}")
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个倒角面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            wx.MessageBox(f"没有找到倒角面", "倒角识别", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"没有找到倒角面")
    
    def on_find_blind_hole_by_ai_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names, _, _, _, groups = find_feature_by_ai(self.NCTI, self.doc,
                                                         weight_path=self.pretrained_model_blind_hole,
                                                         stat_path=self.stat_path_blind_hole,
                                                         feature_name="blind_hole",
                                                         min_faces_num=2,
                                                         max_faces_num=5)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            print(f"obj names:{obj_names}\ncell_ids:{cell_ids}")
            hole_count = len(groups) if groups else len(cell_ids)
            self.status_bar.SetStatusText(f"共查找到{hole_count}个盲孔，{len(cell_ids)}个面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            wx.MessageBox(f"没有找到盲孔", "盲孔识别", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"没有找到盲孔")

    def on_find_blind_hole_public_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names, _, _, _, groups = find_feature_by_ai(self.NCTI, self.doc,
                                                         weight_path=self.pretrained_model_blind_hole_public,
                                                         stat_path=self.stat_path_blind_hole_public,
                                                         feature_name="blind_hole",
                                                         min_faces_num=2,
                                                         max_faces_num=5)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            print(f"obj names:{obj_names}\ncell_ids:{cell_ids}")
            hole_count = len(groups) if groups else len(cell_ids)
            self.status_bar.SetStatusText(f"共查找到{hole_count}个盲孔，{len(cell_ids)}个面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            wx.MessageBox(f"没有找到盲孔", "盲孔识别", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"没有找到盲孔")

    def _select_stp_path_for_detection(self):
        if getattr(self, "current_stp_path", "") and os.path.isfile(self.current_stp_path):
            return self.current_stp_path

        dlg = wx.FileDialog(
            self,
            message="选择当前模型对应的STP文件",
            defaultDir=os.getcwd(),
            defaultFile="",
            wildcard="STEP文件 (*.stp;*.step)|*.stp;*.step",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        )
        if dlg.ShowModal() == wx.ID_CANCEL:
            dlg.Destroy()
            return ""
        file_path = dlg.GetPath()
        dlg.Destroy()
        self.current_stp_path = file_path
        return file_path

    def on_find_blind_hole_by_stp_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return

        stp_path = self._select_stp_path_for_detection()
        if not stp_path:
            self.status_bar.SetStatusText("已取消STP盲孔识别")
            return

        try:
            selection = self.NCTI.SelectionManager(self.doc)
            selected_obj_name = selection.ObjectNames[0] if selection.ObjectNames else None
            result = find_blind_hole_by_stp(self.doc, stp_path, obj_name=selected_obj_name)
            cell_ids = result["cell_ids"]
            obj_names = result["obj_names"]
            hole_count = len(result["holes"])
            print(f"STP blind hole object: {result['obj_name']}")
            print(f"STP blind hole STEP faces: {result['selected_step_faces']}")
            print(f"STP blind hole highlight STEP faces: {result.get('highlight_step_faces', result['selected_step_faces'])}")
            print(f"STP blind hole cell ids: {cell_ids}")
            print(
                "STP blind hole mapped faces:",
                [
                    f"{item['step_face']}->{item['obj_name']}:{item['cell_id']}"
                    for item in result.get("mapped_faces", [])
                ]
            )
            print(
                "STP blind hole shell matches:",
                {key: value["name"] for key, value in result.get("shell_matches", {}).items()}
            )

            if cell_ids:
                self.show_selection(obj_names, cell_ids)
                self.status_bar.SetStatusText(f"STP盲孔识别完成：{hole_count}个盲孔，{len(cell_ids)}个面")
                show_features_dialog(self, obj_names, cell_ids)
            else:
                wx.MessageBox("没有找到盲孔面", "STP盲孔识别", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("没有找到盲孔面")
        except Exception as e:
            wx.MessageBox(f"STP盲孔识别失败:\n{e}", "STP盲孔识别", wx.OK | wx.ICON_ERROR)
            self.status_bar.SetStatusText(f"STP盲孔识别失败:{e}")

    def on_find_through_step_by_stp_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return

        stp_path = self._select_stp_path_for_detection()
        if not stp_path:
            self.status_bar.SetStatusText("已取消通槽台阶识别")
            return

        try:
            result = find_through_step_by_stp(self.NCTI, self.doc, stp_path)
            cell_ids = result["cell_ids"]
            obj_names = result["obj_names"]
            instance_count = len(result["instances"])
            print(f"STP through step object: {result['obj_name']}")
            print(f"STP through step STEP faces: {result['selected_step_faces']}")
            print(f"STP through step cell ids: {cell_ids}")
            print(
                "STP through step mapped faces:",
                [
                    f"{item['step_face']}->{item['obj_name']}:{item['cell_id']}"
                    for item in result.get("mapped_faces", [])
                ]
            )
            for i, inst in enumerate(result["instances"], 1):
                print(f"  通槽 #{i}: faces={inst['faces']}, bottom=#{inst['bottom_face']}, walls={inst['side_walls']}, angles={inst['angles']}")

            if cell_ids:
                self.show_selection(obj_names, cell_ids)
                self.status_bar.SetStatusText(f"通槽台阶识别完成：{instance_count}个通槽，{len(cell_ids)}个面")
                show_features_dialog(self, obj_names, cell_ids)
            else:
                wx.MessageBox("没有找到通槽台阶面", "通槽台阶识别", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("没有找到通槽台阶面")
        except Exception as e:
            wx.MessageBox(f"通槽台阶识别失败:\n{e}", "通槽台阶识别", wx.OK | wx.ICON_ERROR)
            self.status_bar.SetStatusText(f"通槽台阶识别失败:{e}")

    def on_find_through_step_by_featurefox_click(self, evt):
        """FeatureFox 数据驱动通槽识别（需要 STP 文件）。"""
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return

        stp_path = self._select_stp_path_for_detection()
        if not stp_path:
            self.status_bar.SetStatusText("已取消FeatureFox通槽识别")
            return

        # 当前文档对应的 object name（主程序导入文件时记在 index_manager）
        obj_name = getattr(self, 'index_manager', None) and getattr(self.index_manager, 'obj_name', None)
        if not obj_name:
            # 兜底：取最近导入的对象（AllNames 最后一个）
            all_names = list(self.doc.AllNames() or [])
            obj_name = all_names[-1] if all_names else None
        if not obj_name:
            self.status_bar.SetStatusText("未找到可识别对象，请先导入STP模型")
            return

        try:
            result = find_through_step_by_featurefox(self.doc, stp_path, self.NCTI, obj_name=obj_name)
            cell_ids = result["cell_ids"]
            obj_names = result["obj_names"]
            instance_count = len(result["instances"])
            print(f"FeatureFox through step object: {result['obj_name']}")
            print(f"FeatureFox through step STEP faces: {result['selected_step_faces']}")
            print(f"FeatureFox through step cell ids: {cell_ids}")

            if cell_ids:
                self.show_selection(obj_names, cell_ids)
                self.status_bar.SetStatusText(
                    f"FeatureFox通槽识别完成：{instance_count}个通槽，{len(cell_ids)}个面")
                show_features_dialog(self, obj_names, cell_ids)
            else:
                wx.MessageBox("没有找到通槽面", "FeatureFox通槽识别", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("没有找到通槽面")
        except Exception as e:
            traceback.print_exc()
            wx.MessageBox(f"FeatureFox通槽识别失败:\n{e}", "FeatureFox通槽识别", wx.OK | wx.ICON_ERROR)
            self.status_bar.SetStatusText(f"FeatureFox通槽识别失败:{e}")

    def on_find_through_step_by_featurefox_ncti_click(self, evt):
        """FeatureFox-NCTI 数据驱动通槽识别（NCTI 原生数据，零映射，不需要 STP 文件）。"""
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText("没有doc对象")
            return

        # 当前文档对应的 object name（与 featurefox 版一致：优先 index_manager，兜底 AllNames 末位）
        obj_name = getattr(self, 'index_manager', None) and getattr(self.index_manager, 'obj_name', None)
        if not obj_name:
            all_names = list(self.doc.AllNames() or [])
            obj_name = all_names[-1] if all_names else None
        if not obj_name:
            self.status_bar.SetStatusText("未找到可识别对象，请先导入模型")
            return

        try:
            result = find_through_step_by_featurefox_ncti(self.NCTI, self.doc, obj_name=obj_name)
            cell_ids = result["cell_ids"]
            obj_names = result["obj_names"]
            instance_count = len(result["instances"])
            print(f"FeatureFox-NCTI through step object: {result['obj_name']}")
            print(f"FeatureFox-NCTI through step cell ids: {cell_ids}")

            if cell_ids:
                self.show_selection(obj_names, cell_ids)
                self.status_bar.SetStatusText(
                    f"FeatureFox(NCTI)通槽识别完成：{instance_count}个通槽，{len(cell_ids)}个面")
                show_features_dialog(self, obj_names, cell_ids)
            else:
                wx.MessageBox("没有找到通槽面", "FeatureFox(NCTI)通槽识别", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("没有找到通槽面")
        except Exception as e:
            traceback.print_exc()
            wx.MessageBox(f"FeatureFox(NCTI)通槽识别失败:\n{e}", "FeatureFox(NCTI)通槽识别", wx.OK | wx.ICON_ERROR)
            self.status_bar.SetStatusText(f"FeatureFox(NCTI)通槽识别失败:{e}")

    def on_find_through_step_by_ncti_click(self, evt):
        """NCTI-native 通槽台阶识别（不需要 STP 文件）。"""
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText("没有doc对象")
            return

        try:
            result = find_through_step_by_ncti(self.NCTI, self.doc)
            cell_ids = result["cell_ids"]
            obj_names = result["obj_names"]
            instance_count = len(result["instances"])

            if cell_ids:
                self.show_selection(obj_names, cell_ids)
                self.status_bar.SetStatusText(
                    f"NCTI通槽识别完成：{instance_count}个通槽，{len(cell_ids)}个面")
                show_features_dialog(self, obj_names, cell_ids)
            else:
                wx.MessageBox("没有找到通槽台阶面", "NCTI通槽识别", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("没有找到通槽台阶面")
        except Exception as e:
            wx.MessageBox(f"NCTI通槽识别失败:\n{e}", "NCTI通槽识别", wx.OK | wx.ICON_ERROR)
            self.status_bar.SetStatusText(f"NCTI通槽识别失败:{e}")

    def on_find_countersunk_hole_by_stp_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return

        stp_path = self._select_stp_path_for_detection()
        if not stp_path:
            self.status_bar.SetStatusText("已取消沉头孔识别")
            return

        try:
            selection = self.NCTI.SelectionManager(self.doc)
            selected_obj_name = selection.ObjectNames[0] if selection.ObjectNames else None
            result = find_countersunk_hole_by_stp(self.doc, stp_path, obj_name=selected_obj_name)
            cell_ids = result["cell_ids"]
            obj_names = result["obj_names"]
            features = result["features"]
            countersink_count = sum(1 for item in features if item.get("kind") == "countersink_hole")
            counterbore_count = sum(1 for item in features if item.get("kind") == "counterbore_hole")

            print(f"STP countersunk hole object: {result['obj_name']}")
            print(f"STP countersunk hole STEP faces: {result['selected_step_faces']}")
            print(f"STP countersunk hole cell ids: {cell_ids}")
            print(
                "STP countersunk hole mapped faces:",
                [
                    f"{item['step_face']}->{item['obj_name']}:{item['cell_id']}"
                    for item in result.get("mapped_faces", [])
                ]
            )
            print(
                "STP countersunk hole shell matches:",
                {key: value["name"] for key, value in result.get("shell_matches", {}).items()}
            )

            if cell_ids:
                self.show_selection(obj_names, cell_ids)
                self.status_bar.SetStatusText(
                    f"沉头孔识别完成：{countersink_count}个沉头孔，"
                    f"{counterbore_count}个沉孔，{len(cell_ids)}个面"
                )
                show_features_dialog(self, obj_names, cell_ids)
            else:
                wx.MessageBox("没有找到沉头孔面", "沉头孔识别", wx.OK | wx.ICON_INFORMATION)
                self.status_bar.SetStatusText("没有找到沉头孔面")
        except Exception as e:
            wx.MessageBox(f"沉头孔识别失败:\n{e}", "沉头孔识别", wx.OK | wx.ICON_ERROR)
            self.status_bar.SetStatusText(f"沉头孔识别失败:{e}")

    def on_find_fillet_by_ai_click_mfr(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        from ai.brep_mfr.ai_recongnizer import infer
        cell_ids, obj_names = infer(self.doc, self.NCTI, self.mfr_model)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个倒圆角面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            wx.MessageBox(f"没有找到倒圆角面", "圆角识别", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"没有找到倒圆角面")

    def on_find_fillet_hyper_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names, face_type_dict, filtered_face_points, filtered_face_normals, _ = find_feature_by_ai(self.NCTI, self.doc,
                                                                 weight_path=self.pretrained_model_round,
                                                                 stat_path=self.stat_path,
                                                                 min_faces_num=0,
                                                                 max_faces_num=5)
        print(f"ai result: \n cell count:{len(cell_ids)};cell id:{cell_ids}")
        # cell_ids, obj_names = filter_by_face_type(cell_ids, obj_names, face_type_dict)
        cell_ids, obj_names = filter_by_face_type_ncti(self.NCTI, cell_ids, obj_names)
        # cell_ids, obj_names = filter_by_plane(cell_ids, obj_names, filtered_face_points, filtered_face_normals)
        # cell_ids, obj_names = filter_by_plane(self.doc, cell_ids, obj_names)
        print(f"filter_by_plane result: \n cell count:{len(cell_ids)};cell id:{cell_ids}")
        cell_ids, obj_names = filter_by_cylinder(self.doc, cell_ids, obj_names)
        print(f"filter_by_cylinder result: \n cell count:{len(cell_ids)};cell id:{cell_ids}")
        # cell_ids, obj_names = filter_by_cone(self.doc, cell_ids, obj_names)
        # print(f"filter_by_cone result: \n cell count:{len(cell_ids)};cell id:{cell_ids}")
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个倒圆角面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            wx.MessageBox(f"没有找到倒圆角面", "圆角识别", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"没有找到倒圆角面")

    def on_find_plane_by_points_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        # cell_ids, obj_names = find_plane_by_points(self.NCTI, self.doc)
        cell_ids, obj_names = find_plane_by_ncti(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个平面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            self.status_bar.SetStatusText(f"没有找到平面")

    def on_find_plane_by_normals_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names = find_plane_by_normals(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个平面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            self.status_bar.SetStatusText(f"没有找到平面")

    def on_find_plane_by_points_and_normals_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names = find_plane_by_points_and_normals(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个平面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            self.status_bar.SetStatusText(f"没有找到平面")

    def on_find_cylinder_by_points_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names = find_cylinder_by_points(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个圆柱面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            self.status_bar.SetStatusText(f"没有找到圆柱面")

    def on_find_cylinder_by_normal_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names = find_cylinder_by_normals(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个圆柱面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            self.status_bar.SetStatusText(f"没有找到圆柱面")

    def on_find_cylinder_by_points_and_normal_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names = find_cylinder_by_points_and_normals(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个圆柱面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            self.status_bar.SetStatusText(f"没有找到圆柱面")

    def on_find_cone_by_points_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        cell_ids, obj_names = find_cone_by_points(self.NCTI, self.doc)
        if cell_ids:
            self.show_selection(obj_names, cell_ids)
            self.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个圆锥面")
            show_features_dialog(self, obj_names, cell_ids)
        else:
            self.status_bar.SetStatusText(f"没有找到圆锥面")

    def on_find_fillet_hyper(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        min_radius_1 = 1
        max_radius_1 = 1.5
        fillet_type_1 = 2 #"凹圆角"

        min_radius_2 = 0
        max_radius_2 = 0.5
        fillet_type_2 = 1 #"凸圆角"

        found_fillet_1 = find_fillet_compound(self.NCTI, self.doc, min_radius_1, max_radius_1, fillet_type_1)
        found_fillet_2 = find_fillet_compound(self.NCTI, self.doc, min_radius_2, max_radius_2, fillet_type_2)

        dict_geo = {}
        dict_ai = {}
        for name, cell_id in zip(found_fillet_1.ObjectNames, found_fillet_1.CellIDs):
            dict_geo[cell_id] = name
        for name, cell_id in zip(found_fillet_2.ObjectNames, found_fillet_2.CellIDs):
            dict_ai[cell_id] = name
        dict_geo.update(dict_ai)

        obj_names = []
        cell_ids = []
        for key, value in dict_geo.items():
            obj_names.append(value)
            cell_ids.append(key)

        self.show_selection(obj_names, cell_ids)

    def on_remove_feature_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        self.sync_selected_feature()
        ret = remove_feature(self.doc, self.selected_feature)
        if ret:
            selection = self.NCTI.SelectionManager(self.doc)
            selection.ClearSelected()
            self.status_bar.SetStatusText(f"移除特征成功")
        else:
            self.status_bar.SetStatusText(f"没有特征被移除")
        self.cad_view.update()

    def _reopen_and_import(self, path):
        self.doc.Close()
        view = new_document_function(self.NCTI, self.doc, self.cad_view.GetHandle())
        self.bind_view(view)
        self.set_select_mode()
        self.doc.RunCommand("cmd_ncti_import_file", path)
        self.doc.Zoom()

    def on_export_feature_click(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return

        self.sync_selected_feature()

        if not self.selected_feature:
            wx.MessageBox("请先选择要导出的特征", "导出特征", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"请先选择要导出的特征")
            return

        obj_names = set(f[0] for f in self.selected_feature)
        if len(obj_names) > 1:
            wx.MessageBox("暂不支持跨对象导出，请选择同一对象的面", "导出特征", wx.OK | wx.ICON_INFORMATION)
            self.status_bar.SetStatusText(f"暂不支持跨对象导出")
            return

        obj_name = self.selected_feature[0][0]
        cell_id_list = [f[1] for f in self.selected_feature]

        dlg = wx.FileDialog(
            self,
            message="导出特征",
            defaultDir=os.getcwd(),
            defaultFile="",
            wildcard="STEP文件 (*.stp;*.step)|*.stp;*.step",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )
        if dlg.ShowModal() == wx.ID_CANCEL:
            dlg.Destroy()
            return
        file_path = dlg.GetPath()
        dlg.Destroy()

        all_face = self.doc.FindAllFaces(obj_name)

        # 选中了全部面时直接导出，无需走删除-恢复流程
        if set(cell_id_list) == set(all_face):
            self.doc.RunCommand("cmd_ncti_export_file", file_path, obj_name)
            self.status_bar.SetStatusText(f"导出特征成功: {file_path}")
            return

        fd, temp_path = tempfile.mkstemp(suffix=".stp")
        os.close(fd)

        try:
            self.doc.RunCommand("cmd_ncti_export_file", temp_path, obj_name)

            unselected_face = list(set(all_face) - set(cell_id_list))
            self.doc.RunCommand("cmd_ncti_remove_faces", obj_name, unselected_face)
            self.doc.RunCommand("cmd_ncti_export_file", file_path, obj_name)

            self._reopen_and_import(temp_path)

            try:
                os.remove(temp_path)
            except OSError:
                pass

            self.status_bar.SetStatusText(f"导出特征成功: {file_path}")
        except Exception as e:
            self.status_bar.SetStatusText(f"导出特征失败: {e}")
            try:
                self._reopen_and_import(temp_path)
                os.remove(temp_path)
            except Exception:
                wx.MessageBox(
                    f"文档恢复失败，临时备份保存在:\n{temp_path}",
                    "导出特征",
                    wx.OK | wx.ICON_WARNING
                )

    def on_select_model_click(self, evt):
        filename_path = select_file_base_dialog(parent=None,
                                                wildcard="Pth (*.pth)|*.pth|Onnx (*.onnx)|*.onnx",
                                                message="选择预训练模型",
                                                default_dir="C:",
                                                default_file="")
        if filename_path:
            self.pretrained_model_custom = filename_path
            # 自动在同目录匹配归一化统计量 json（即使与模型不同名也尽量定位）：
            # 优先 同名json > attr_stat.json > 目录下唯一单个json
            model_dir = os.path.dirname(filename_path)
            base = os.path.splitext(os.path.basename(filename_path))[0]
            stat_json = os.path.join(model_dir, base + ".json")
            if not os.path.exists(stat_json):
                stat_json = os.path.join(model_dir, "attr_stat.json")
            if not os.path.exists(stat_json):
                jsons = [os.path.join(model_dir, f) for f in os.listdir(model_dir)
                         if f.lower().endswith(".json")
                         and os.path.isfile(os.path.join(model_dir, f))]
                stat_json = jsons[0] if len(jsons) == 1 else None
            if stat_json and os.path.exists(stat_json):
                self.stat_path_custom = stat_json
                self.status_bar.SetStatusText(f"导入自定义模型:{filename_path}（统计量:{stat_json}）")
            else:
                self.status_bar.SetStatusText(f"导入自定义模型:{filename_path}（同目录未找到统计量json，请确认）")
        else:
            self.status_bar.SetStatusText(f"导入预训练模型失败")

    def on_select_infer_click(self, evt):
        infer_method = select_infer_method_dialog(self, "选择ai识别算法")
        if infer_method:
            self.infer_method = infer_method
            self.status_bar.SetStatusText(f"选择ai识别算法:{infer_method}")
        else:
            self.status_bar.SetStatusText(f"没有选择ai识别算法")

    def on_show_body(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()        
        
        self.show_body.SetValue(state)
        self.show_face.SetValue(state)
        self.show_edge.SetValue(state)
        self.show_vertex.SetValue(state)

        if state:   
            self.doc.SetVisualMode(1, 1, 1)    
            self.show_face.Enable(not state)
            self.show_edge.Enable(not state)
            self.show_vertex.Enable(not state)
        else:
            self.doc.SetVisualMode(0, 0, 0)
            self.show_face.Enable(not state)
            self.show_edge.Enable(not state)
            self.show_vertex.Enable(not state)

    def on_show_face(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        is_show_edge = self.show_edge.IsChecked()
        is_show_vertex = self.show_vertex.IsChecked()
        self.doc.SetVisualMode(int(state), int(is_show_edge), int(is_show_vertex))

    def on_show_edge(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        is_show_face = self.show_face.IsChecked()
        is_show_vertex = self.show_vertex.IsChecked()
        self.doc.SetVisualMode(int(is_show_face), int(state), int(is_show_vertex))

    def on_show_vertex(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        is_show_face = self.show_face.IsChecked()
        is_show_edge = self.show_edge.IsChecked()
        self.doc.SetVisualMode(int(is_show_face), int(is_show_edge), int(state))

    def on_select_body(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.doc.SetSelBody(int(state))
        if not state:
            selection = self.NCTI.SelectionManager(self.doc)
            selection.ClearSelected()
        else:
            self.select_face.SetValue(True)
            self.select_edge.SetValue(True)
            self.select_vertex.SetValue(True)

            self.doc.SetSelFace(state)
            self.doc.SetSelLine(state)
            self.doc.SetSelVertex(state)

    def on_select_face(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.doc.SetSelFace(state)
        if not state:
            self.doc.SetSelBody(False)
            self.select_body.SetValue(False)

    def on_select_edge(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.doc.SetSelLine(state)
        if not state:
            self.doc.SetSelBody(False)
            self.select_body.SetValue(False)

    def on_select_vertex(self, evt):
        if not hasattr(self, 'doc'):
            self.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.doc.SetSelVertex(state)
        if not state:
            self.doc.SetSelBody(False)
            self.select_body.SetValue(False)

    def on_close(self, event):
        """
        处理窗口关闭事件。
        弹出确认对话框，询问用户是否真的要关闭窗口。
        """
        dlg = wx.MessageDialog(
            self,
            message="确定要退出程序吗？",
            caption="确认退出",
            style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        )
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            # 用户确认退出，真正关闭窗口
            self.doc.Close()
            self.Destroy()
        else:
            # 用户取消，不执行关闭
            event.Veto()  # 阻止窗口被关闭

    def set_select_mode(self):
        is_select_body_check = self.select_body.IsChecked()
        self.doc.SetSelBody(is_select_body_check)

    def on_remove_face_export_part_click(self, evt):
        selection = self.NCTI.SelectionManager(self.doc)
        obj_name_list = selection.ObjectNames
        print(f"obj name list:{obj_name_list}")
        cell_id_list = selection.CellIDs
        all_face = self.doc.FindAllFaces(obj_name_list[0])

        index_manager = IndexManager(self.doc, obj_name_list[0], all_face)

        unselected_face = list(set(all_face)-set(cell_id_list))

        self.doc.RunCommand("cmd_ncti_remove_faces", obj_name_list[0], unselected_face)
        index_manager.remove_cell(list(unselected_face))
        index_manager.reindex()
        print(f"id pt map:{index_manager.id_map}")

        cwd = os.getcwd()
        file_path = os.path.join(cwd, "export.stp")
        print(f"file path:{file_path}")

        self.doc.RunCommand("cmd_ncti_export_file", file_path, obj_name_list[0])
        self.doc.Close()
        view = new_document_function(self.NCTI, self.doc, self.cad_view.GetHandle())
        self.bind_view(view)
        self.set_select_mode()

        self.doc.RunCommand("cmd_ncti_import_file", file_path)
        self.doc.Zoom()
        self.cad_view.update_doc(self)
        self.cad_view.update_view()

        object_current_stp = self.doc.AllNames()
        print(f"object current:{object_current_stp}")
        print(f"obj current:{object_current_stp[0]}")
        index_manager.obj_name = object_current_stp[0]
        index_manager.reindex()
        cell_ids = index_manager.cell_ids
        print(f"cell ids:{list(cell_ids)}")
        print(f"id pt map:{index_manager.id_map}")
        obj_names = [object_current_stp[0] for _ in range(len(cell_ids))]
        print(f"obj names:{obj_names}")
        if cell_ids:
            show_features_dialog(self, obj_names, cell_ids)
