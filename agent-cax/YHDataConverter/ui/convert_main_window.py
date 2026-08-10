import os

import wx
import wx.aui

from config.config_load import global_scope
from function.on_category_file import set_color
from ui.viewer import CADViewer
from ui.file_tab import FileTabPanel
from ui.general_tab import GeneralTabPanel
from ui.convert_tab import ConvertTabPanel


class ConvertPlatform(wx.Frame):
    def __init__(self):
        super().__init__(None, title="GeoConv - 几何数据转换工具", size=(1200, 800))

        if not self.init_cad_env():
            return

        self.icon_dir = "icons"
        if not os.path.exists(self.icon_dir):
            os.makedirs(self.icon_dir)
        icon = wx.Icon("icons/ncti.ico", wx.BITMAP_TYPE_ICO)
        self.SetIcon(icon)

        self.init_status_bar()

        wx.CallAfter(self.init_main_layout)
        wx.CallAfter(self.bind_evt)

        self.Centre()
        self.Show()

    def init_cad_env(self):
        global global_scope
        if "NCTI" in global_scope:
            self.NCTI = global_scope["NCTI"]
            self.doc = global_scope["doc"]
            self.fp_stp = ""
            return True
        else:
            return False

    def reset_label_env(self):
        self.fp_stp = ""

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
        self.convert_tab = ConvertTabPanel(self.notebook, self)

        self.notebook.AddPage(self.file_tab, "文件")
        self.notebook.AddPage(self.general_tab, "选择/显示")
        self.notebook.AddPage(self.convert_tab, "转换")

        self.label_tab = self.convert_tab

        top_sizer.Add(self.notebook, 1, wx.EXPAND)
        top_panel.SetSizer(top_sizer)

        self.cad_view = CADViewer(parent=self)

        top_panel_height = max(100, int(100 * self.scale_factor))
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

        self.aui_manager.Update()

    def bind_evt(self):
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_SIZE, self.on_resize)

    def on_resize(self, event):
        event.Skip()
        self.cad_view.update_view()

    def load_icon(self, name):
        icon_path = os.path.join(self.icon_dir, f"{name}.png")
        if os.path.exists(icon_path):
            return wx.Bitmap(icon_path)
        else:
            icon_path = os.path.join(self.icon_dir, "ncti.ico")
            return wx.Bitmap(icon_path)

    def bind_view(self, view):
        if view is None:
            return
        self.cad_view.view = view
        self.view = view
        set_color(self)
        self.cad_view.update_doc(self)
        self.cad_view.update_view()

    def on_close(self, event):
        dlg = wx.MessageDialog(
            self,
            message="确定要退出程序吗？",
            caption="确认退出",
            style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        )
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            self.aui_manager.UnInit()
            self.doc.Close()
            self.Destroy()
        else:
            event.Veto()

    def set_select_mode(self):
        is_select_body_check = self.general_tab.select_body.IsChecked()
        self.doc.SetSelBody(is_select_body_check)
