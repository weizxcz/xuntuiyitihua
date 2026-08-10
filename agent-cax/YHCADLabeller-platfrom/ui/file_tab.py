import wx

from dialog.export_file import export_file_dialog
from dialog.import_file import pick_stp_file_path
from dialog.save_ncit_file import save_ncit_file_dialog
from function.on_new_document import new_document_with_dialog, new_document_function


class FileTabPanel(wx.Panel):
    """文件选项卡面板"""
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.parent = parent
        self.init_ui()
        self.bind_events()

    def init_ui(self):
        """初始化UI"""
        # 创建文件选项卡的工具栏
        file_toolbar = wx.ToolBar(self, wx.ID_ANY,
                                  style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT )
        # 设置工具 bitmap 大小，根据缩放因子调整
        bitmap_size = max(36, int(36*self.main_window.scale_factor))  # 减小基础大小，确保在高缩放级别下不会过大
        print(f"bitmap size:{bitmap_size}")
        file_toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        # 设置工具栏的垂直尺寸，确保有足够空间显示文字和图标
        toolbar_height = max(60, int(80*self.main_window.scale_factor))  # 增加最小高度
        print(f"toolbar height:{toolbar_height}")
        file_toolbar.SetMinSize((-1, toolbar_height))
        # 设置工具栏的最佳尺寸
        file_toolbar.SetSize((-1, toolbar_height))

        self.button_new_doc = wx.NewIdRef()
        self.button_import_part = wx.NewIdRef()
        self.button_save_file = wx.NewIdRef()
        self.button_close_doc = wx.NewIdRef()
        self.button_export_file = wx.NewIdRef()

        # 文件选项卡按钮列表
        file_buttons = [
            ("创建零件", self.button_new_doc),
            (wx.ID_SEPARATOR, None),
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
                icon = self.main_window.load_icon(btn[0])
                # 直接在工具栏中添加工具，会显示图标
                file_toolbar.AddTool(btn[1], btn[0], icon, shortHelp=btn[0])

        file_toolbar.Realize()

        # 设置文件选项卡的布局
        file_sizer = wx.BoxSizer(wx.VERTICAL)
        file_sizer.Add(file_toolbar, 0, wx.EXPAND)
        self.SetSizer(file_sizer)
        self.Layout()

    def bind_events(self):
        """绑定事件"""
        # 绑定工具事件
        self.Bind(wx.EVT_TOOL, self.on_new_part_click, id=self.button_new_doc)
        self.Bind(wx.EVT_TOOL, self.on_import_part_button_click, id=self.button_import_part)
        self.Bind(wx.EVT_TOOL, self.on_save_file_click, id=self.button_save_file)
        self.Bind(wx.EVT_TOOL, self.on_close_doc_click, id=self.button_close_doc)
        self.Bind(wx.EVT_TOOL, self.on_export_file_click, id=self.button_export_file)

    def on_new_part_click(self, event):
        """创建零件按钮点击事件处理"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            self.main_window.reset_label_env()
            self.main_window.doc.Close()
            view = new_document_with_dialog(self.main_window.NCTI, self.main_window.doc, self.main_window.cad_view.GetHandle(), self.main_window.scale_factor)
            self.main_window.bind_view(view)
            self.main_window.status_bar.SetStatusText(f"新建零件文档")
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"新建零件文档失败:{e}")

    def on_import_part_button_click(self, evt):
        """导入零件：先关闭当前文档再导入，这样已加载零件A时无需先手动点
        "关闭文档"，直接点"导入"选零件B就能加载。"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            filename_path = pick_stp_file_path()
            if not filename_path:
                return

            self.main_window.reset_label_env()
            self.main_window.doc.Close()
            view = new_document_function(self.main_window.NCTI, self.main_window.doc, self.main_window.cad_view.GetHandle())
            self.main_window.bind_view(view)

            self.main_window.doc.ResetCaseResult()
            self.main_window.doc.SetCreateGeGeom(1)
            self.main_window.doc.SetImportAssemelFile(1)
            self.main_window.doc.RunCommand("cmd_ncti_import_file", str(filename_path))
            self.main_window.doc.Zoom()

            self.main_window.fp_stp = filename_path
            self.main_window.label_tab.start_new_auto_save()
            self.main_window.cad_view.update_doc(self.main_window)
            self.main_window.cad_view.update_view()
            self.main_window.status_bar.SetStatusText(f"导入模型:{filename_path}")
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"导入文件失败:{e}")

    def on_export_file_click(self, evt):
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            filename_path = export_file_dialog(self.main_window.NCTI, self.main_window.doc)
            if filename_path:
                self.main_window.status_bar.SetStatusText(f"导出模型成功:{filename_path}")
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"没有导出文件:{e}")

    def on_save_file_click(self, evt):
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            save_ncit_file_dialog(self.main_window.NCTI, self.main_window.doc)
            self.main_window.status_bar.SetStatusText(f"保存文档")
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"保存文件失败:{e}")

    def on_close_doc_click(self, evt):
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        try:
            self.main_window.reset_label_env()
            self.main_window.doc.Close()
            view = new_document_function(self.main_window.NCTI, self.main_window.doc, self.main_window.cad_view.GetHandle())
            self.main_window.bind_view(view)
            self.main_window.set_select_mode()
            self.main_window.status_bar.SetStatusText(f"关闭文档")
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"关闭文档失败:{e}")
