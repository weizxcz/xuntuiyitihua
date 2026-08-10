import os

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


class CAEPlatform(wx.Frame):
    def __init__(self):
        super().__init__(None, title="炎核 几何特征标注工具", size=(1600, 900))

        if not self.init_cad_env():
            return
        self.init_ai_env()
        self.init_label_env()

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
        self.pretrained_model_round = os.path.join("ai",
                                                   "AAGNet_infer",
                                                   "weights",
                                                   "weight_round.pth")
        self.stat_path = os.path.join("ai",
                                      "AAGNet_infer",
                                      "weights",
                                      "attr_stat_ncti_62k.json")
        self.infer_method = "AAG"

        self.pretrained_mfr_model_round = os.path.join("ai",
                                                       "brep_mfr",
                                                       "weights",
                                                       "best.ckpt")
    def init_label_env(self):
        self.selected_label_name = ""
        self.bottom_faces = {}  # {face_id: (category_id, [cylinder_face_ids])}
        self.fp_stp = ""
        self.workspace_window = None
        self.current_industry = ""
        self.current_part_id = ""
        # 按特征名独立计数的实例 ID，下一批次标注时自动递增
        self.feature_instance_counter = {}  # {feature_name: next_instance_id}
        self.face_to_instance = {}  # {face_id: (feature_name, instance_id)}

    def reset_label_env(self):
        """重置标注状态，在关闭文档或导入新文件时调用"""
        if hasattr(self, 'label_tab'):
            self.label_tab.stop_auto_save_timer()
        # 仅清理 temp 目录下的临时 STP 文件，不删除用户的原始文件
        if self.fp_stp and os.path.normpath(self.fp_stp).startswith(
                os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp"))
        ):
            try:
                os.remove(self.fp_stp)
            except Exception:
                pass
        self.init_label_env()
        if hasattr(self, 'label_name_panel') and self.label_name_panel.name_list.GetCount() > 0:
            self.label_name_panel.name_list.SetSelection(0)
            self.selected_label_name = self.label_name_panel.name_list.GetString(0)
        if hasattr(self, 'labeled_features_panel'):
            panel = self.labeled_features_panel
            panel.labeled_list.DeleteAllItems()
            panel.label_result.clear()
            panel.clear_undo_history()

    def recreate_document(self, geom="OCC", cons="DCM", grid="GMSH"):
        """清空当前文档并重建视图，返回新 view 对象。"""
        self.doc.New(geom, cons, grid)
        view = self.NCTI.View(self.doc.ID)
        view.CreateWindow(self.cad_view.GetHandle())
        view.SetWindowVis(True, self.doc.ID)
        self.doc.SetCreateGeGeom(1)
        self.doc.Zoom()
        self.bind_view(view)
        return view

    def import_step(self, step_path):
        """导入 STEP 文件到 3D 视图，由 WorkspaceWindow 调用。"""
        self.reset_label_env()
        self.doc.ResetCaseResult()
        self.doc.SetCreateGeGeom(1)
        self.doc.SetImportAssemelFile(1)
        self.doc.RunCommand("cmd_ncti_import_file", str(step_path))
        self.doc.Zoom()
        self.fp_stp = step_path
        self.label_tab.start_new_auto_save()
        self.cad_view.update_doc(self)
        self.cad_view.update_view()

    def init_status_bar(self):
        self.status_bar = self.CreateStatusBar()
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

        self.notebook.AddPage(self.file_tab, "文件")
        self.notebook.AddPage(self.general_tab, "选择/显示")
        self.notebook.AddPage(self.label_tab, "标注")

        # 绑定选项卡切换事件
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.on_tab_change)

        top_sizer.Add(self.notebook, 1, wx.EXPAND)
        top_panel.SetSizer(top_sizer)

        self.cad_view = CADViewer(parent=self)
        self.hwnd = int(self.cad_view.GetId())

        self.label_name_panel = LabelNamePanel(self)

        self.labeled_features_panel = LabeledFeaturesPanel(self)

        self.labeled_list = self.labeled_features_panel.labeled_list

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
                                 Position(0))

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
        if is_label_tab:
            if hasattr(self, 'mouse_delegate'):
                self.install_mouse_delegate()
        else:
            if hasattr(self, 'mouse_delegate') and hasattr(self.mouse_delegate, 'uninstall'):
                self.mouse_delegate.uninstall()

        self.aui_manager.GetPane(self.label_name_panel).Show(is_label_tab)
        self.aui_manager.GetPane(self.labeled_features_panel).Show(is_label_tab)
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
            if self.workspace_window:
                self.workspace_window.Destroy()
            self.aui_manager.UnInit()
            self.doc.Close()
            self.Destroy()
        else:
            # 用户取消，不执行关闭
            event.Veto()  # 阻止窗口被关闭

    def set_select_mode(self):
        is_select_body_check = self.general_tab.select_body.IsChecked()
        self.doc.SetSelBody(is_select_body_check)
