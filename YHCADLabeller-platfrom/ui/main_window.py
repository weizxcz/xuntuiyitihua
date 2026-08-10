import os
import sys

import wx
import wx.aui

from config.config_load import global_scope
from function.on_category_file import set_color
from ui.viewer import CADViewer
from ui.label_tab import LabelTabPanel
from ui.label_feature_panel import LabeledFeaturesPanel
from ui.label_name_panel import LabelNamePanel
from ui.general_tab import GeneralTabPanel
from ui.file_tab import FileTabPanel
from ui.recognition_tab import RecognitionTabPanel
from ui.train_tab import TrainTabPanel
from ui.train_dashboard import TrainDashboardPanel


# 状态栏报错关键字：命中即额外打印到终端（stderr），方便调试。
# 标注界面里很多错误只在底部状态栏一闪而过（如"导入文件失败: ..."），
# 打印到终端后便于排查问题。
_STATUS_ERROR_KEYWORDS = (
    "失败", "错误", "异常", "没有doc对象", "未找到", "不存在", "无法",
    "Error", "Exception", "Failed", "failed", "error",
)


class LoggingStatusBar(wx.StatusBar):
    """状态栏子类：设置文本的同时，把"报错类"消息同步打印到终端。"""

    def SetStatusText(self, text, number=0):
        super().SetStatusText(text, number)
        if text and any(kw in text for kw in _STATUS_ERROR_KEYWORDS):
            print(f"[状态栏报错] {text}", file=sys.stderr)


class CAEPlatform(wx.Frame):
    def __init__(self):
        super().__init__(None, title="炎核 几何特征标注工具", size=(1600, 900))

        if not self.init_cad_env():
            return
        self.init_ai_env()
        self.init_label_env()
        self.init_train_env()

        self.icon_dir = "icons"
        if not os.path.exists(self.icon_dir):
            os.makedirs(self.icon_dir)
        icon = wx.Icon("icons/ncti.ico", wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)

        # 初始化状态栏
        self.init_status_bar()

        # 初始化主布局
        wx.CallAfter(self.init_main_layout)

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
            return True
        else:
            return False

    def init_ai_env(self):
        weights_dir = os.path.join("ai", "AAGNet_infer", "weights")
        self.pretrained_onnx_model_round = os.path.join(weights_dir, "round", "round_scatter.onnx")
        self.pretrained_onnx_model_chamfer = os.path.join(weights_dir, "chamfer", "chamfer_scatter.onnx")
        self.pretrained_onnx_model_blind_hole = os.path.join(
            weights_dir, "blindhole", "blind_hole_scatter.onnx"
        )
        self.pretrained_onnx_model_countersunk_hole = os.path.join(
            weights_dir, "countersink", "countersunk_hole_scatter.onnx"
        )
        self.stat_path_round = os.path.join(
            weights_dir, "round", "attr_stat_ncti_62k.json"
        )
        self.stat_path_chamfer = os.path.join(
            weights_dir, "chamfer", "attr_stat_data2+part_chamfer.json"
        )
        self.stat_path_blind_hole = os.path.join(
            weights_dir, "blindhole", "attr_stat_blindhole_0701.json"
        )
        self.stat_path_countersunk_hole = os.path.join(
            weights_dir, "countersink", "attr_stat_mix_v18.json"
        )

        self.pretrained_mfr_model_round = os.path.join("ai",
                                                       "brep_mfr",
                                                       "weights",
                                                       "best.ckpt")

        # 预标注功能选用的模型（选择预标注模型按钮写入）
        self.pretrain_model_path = ""
        self.pretrain_stat_path = ""
        self.pretrain_feature_name = "ai_feature"
        self.pretrain_min_faces_num = 0
        self.pretrain_max_faces_num = 9
        self.last_pretrain_model_dir = ""
        self.pre_label_batch_job = None  # 批量预标注运行时的分片任务状态，空闲时为 None

    def init_train_env(self):
        self.train_dataset_folder = ""
        self.train_available_features = []
        self.train_selected_feature = ""
        self.train_job = None  # 生成graph/训练神经网络运行时的子进程任务状态，空闲时为 None

    def init_label_env(self):
        self.selected_label_name = ""
        self.bottom_faces = {}  # {face_id: (category_id, [cylinder_face_ids])}
        self.fp_stp = ""
        # 按特征名独立计数的实例 ID，下一批次标注时自动递增
        self.feature_instance_counter = {}  # {feature_name: next_instance_id}
        self.face_to_instance = {}  # {face_id: (feature_name, instance_id)}

    def reset_label_env(self):
        """重置标注状态，在关闭文档或导入新文件时调用"""
        if hasattr(self, 'label_tab'):
            self.label_tab.stop_auto_save_timer()
        self.init_label_env()
        if hasattr(self, 'labeled_features_panel'):
            panel = self.labeled_features_panel
            panel.labeled_list.DeleteAllItems()
            panel.label_result.clear()
            panel.clear_undo_history()

    def init_status_bar(self):
        self.status_bar = LoggingStatusBar(self)
        self.SetStatusBar(self.status_bar)
        self.status_bar.SetStatusText("Kernel: OCC Mesh: GMSH")

    def init_main_layout(self):
        self.scale_factor = self.GetDPIScaleFactor()

        self.aui_manager = wx.aui.AuiManager(self)

        top_panel = wx.Panel(self)
        top_sizer = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(top_panel, wx.ID_ANY,
                                    style=wx.NB_TOP)

        self.file_tab = FileTabPanel(self.notebook, self)
        self.general_tab = GeneralTabPanel(self.notebook, self)
        self.label_tab = LabelTabPanel(self.notebook, self)
        self.recognition_tab = RecognitionTabPanel(self.notebook, self)
        self.train_tab = TrainTabPanel(self.notebook, self)

        self.notebook.AddPage(self.file_tab, "文件")
        self.notebook.AddPage(self.general_tab, "选择/显示")
        self.notebook.AddPage(self.label_tab, "标注")
        self.notebook.AddPage(self.train_tab, "训练")
        self.notebook.AddPage(self.recognition_tab, "识别")

        # 绑定选项卡切换事件
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)

        top_sizer.Add(self.notebook, 1, wx.EXPAND)
        top_panel.SetSizer(top_sizer)

        self.cad_view = CADViewer(parent=self)
        self.hwnd = int(self.cad_view.GetId())

        self.label_name_panel = LabelNamePanel(self)

        self.labeled_features_panel = LabeledFeaturesPanel(self)

        self.labeled_list = self.labeled_features_panel.labeled_list

        top_panel_height = max(140, int(140*self.scale_factor))
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
                                 Position(0))

        # 训练页中央区：内嵌曲线+日志仪表盘，平时隐藏，切到训练 tab 时替换 STP 查看器
        self.train_dashboard = TrainDashboardPanel(self)
        self.aui_manager.AddPane(self.train_dashboard,
                                 wx.aui.AuiPaneInfo().Center().
                                 CaptionVisible(False).
                                 CloseButton(False).
                                 Floatable(False).
                                 DockFixed(True).
                                 Layer(1).
                                 Position(0).
                                 Show(False))

        self.aui_manager.AddPane(self.label_name_panel,
                                 wx.aui.AuiPaneInfo().Left().
                                 Caption("特征名称").
                                 CloseButton(True).
                                 Floatable(True).
                                 DockFixed(True).
                                 Layer(1).
                                 Position(1).
                                 BestSize(300, -1).
                                 MinSize(100, 100).
                                 Show(False))

        self.aui_manager.AddPane(self.labeled_features_panel,
                                 wx.aui.AuiPaneInfo().Right().
                                 Caption("标注特征").
                                 CloseButton(True).
                                 Floatable(True).
                                 DockFixed(True).
                                 Layer(1).
                                 Position(2).
                                 BestSize(500, -1).
                                 MinSize(100, 100).
                                 Show(False))

        self.aui_manager.Update()

    def on_tab_change(self, event):
        """选项卡切换事件处理"""
        page_index = event.GetSelection()

        self.status_bar.SetStatusText(f"当前页面: {self.notebook.GetPageText(page_index)}")
        self.notebook.GetCurrentPage().SetFocus()

        is_label_tab = (page_index == 2)
        is_train_tab = (page_index == 3)
        if is_label_tab:
            if hasattr(self, 'mouse_delegate'):
                self.install_mouse_delegate()
        else:
            if hasattr(self, 'mouse_delegate') and hasattr(self.mouse_delegate, 'uninstall'):
                self.mouse_delegate.uninstall()

        self.aui_manager.GetPane(self.label_name_panel).Show(is_label_tab)
        self.aui_manager.GetPane(self.labeled_features_panel).Show(is_label_tab)

        # 训练 tab：中央显示训练仪表盘，隐藏 STP 查看器；其它 tab 反之
        self.aui_manager.GetPane(self.cad_view).Show(not is_train_tab)
        self.aui_manager.GetPane(self.train_dashboard).Show(is_train_tab)
        if is_train_tab:
            self.train_dashboard.on_show()
        else:
            self.cad_view.update_view()

        self.aui_manager.Update()

        # 跳过事件，让系统继续处理
        event.Skip()

    def bind_evt(self):
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.Bind(wx.EVT_SIZE, self.on_resize_and_move)
        self.Bind(wx.EVT_MOVE, self.on_resize_and_move)

        self.Bind(wx.EVT_MENU, self.on_undo, id=wx.ID_UNDO)
        accel = wx.AcceleratorTable([
            (wx.ACCEL_CTRL, ord('Z'), wx.ID_UNDO),
        ])
        self.SetAcceleratorTable(accel)

    def on_resize_and_move(self, event):
        self.cad_view.update_view()

    def on_undo(self, event):
        if hasattr(self, 'labeled_features_panel'):
            self.labeled_features_panel.undo()
        self.Refresh()
        self.cad_view.update_view()

    def load_icon(self, name):
        icon_path = os.path.join(self.icon_dir, f"{name}.png")
        if os.path.exists(icon_path):
            # 如果图标文件已存在，直接加载
            return wx.Bitmap(icon_path)
        else:
            icon_path = os.path.join(self.icon_dir, f"ncti.ico")
            return wx.Bitmap(icon_path)

    def bind_view(self, view):
        self.cad_view.view = view
        set_color(self)
        self.cad_view.update_doc(self)
        self.cad_view.update_view()

    def show_selection(self, obj_names, cell_ids):
        selection = self.NCTI.SelectionManager(self.doc)
        selection.ClearSelected()
        selection.ObjectNames = obj_names
        selection.CellIDs = cell_ids
        selection.SetSelected()
        self.selected_feature = [(obj_names[i], cell_id) for i, cell_id in enumerate(cell_ids)]

    def focus_selection(self, obj_names, cell_ids):
        self.show_selection(obj_names, cell_ids)
        self.status_bar.SetStatusText(f"找到{len(cell_ids)}个特征")

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
            if hasattr(self, 'label_tab'):
                self.label_tab.stop_auto_save_timer()
            if hasattr(self, 'train_dashboard'):
                self.train_dashboard.stop()
            if getattr(self, 'pre_label_batch_job', None) is not None:
                # 批量预标注分片跑在 wx.CallAfter 队列上，窗口销毁后队列里
                # 排队的下一步还会触发、访问已销毁的 self，必须先清掉任务
                # 标记（_run_batch_pre_label_step 一开始就检查这个标记）并
                # 释放批量自己占用的后台 Document。
                self.pre_label_batch_job["doc"].Delete()
                self.pre_label_batch_job = None
            self.aui_manager.UnInit()
            self.doc.Close()
            self.Destroy()
        else:
            # 用户取消，不执行关闭
            event.Veto()  # 阻止窗口被关闭

    def set_select_mode(self):
        is_select_body_check = self.general_tab.select_body.IsChecked()
        self.doc.SetSelBody(is_select_body_check)
