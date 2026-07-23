import wx
import os
from function.on_find_fillet_by_ai import find_feature_by_ai
from dialog.show_features import show_features_dialog
from function.on_remove_feature import remove_feature

class RecognitionTabPanel(wx.Panel):
    """识别选项卡面板"""
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.parent = parent
        self.init_ui()
        self.bind_events()

    def init_ui(self):
        """初始化UI"""
        # 创建识别选项卡的工具栏
        recognition_toolbar = wx.ToolBar(self, wx.ID_ANY,
                                         style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)
        bitmap_size = max(36, int(36 * self.main_window.scale_factor))
        recognition_toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        toolbar_height = max(60, int(80 * self.main_window.scale_factor))
        recognition_toolbar.SetMinSize((-1, toolbar_height))
        recognition_toolbar.SetSize((-1, toolbar_height))

        self.button_find_fillet_ai = wx.NewIdRef()
        self.button_find_chamfer_ai = wx.NewIdRef()
        self.button_find_countersunk_hole_ai = wx.NewIdRef()
        self.button_find_blind_hole_ai = wx.NewIdRef()
        self.button_remove_feature = wx.NewIdRef()
        self.button_export_feature = wx.NewIdRef()

        # 1. 识别功能按钮
        recognition_buttons = [
            ("AI圆角识别", self.button_find_fillet_ai),
            ("AI倒角识别", self.button_find_chamfer_ai),
            ("AI沉头孔识别", self.button_find_countersunk_hole_ai),
            ("AI盲孔识别", self.button_find_blind_hole_ai),
        ]

        for btn in recognition_buttons:
            # 还原 smartcleaner 中的原始图表加载逻辑：
            # AI沉头孔识别映射为 "混合盲孔识别"，AI盲孔识别映射为 "AI盲孔识别"
            # 它们没有对应的png图标文件时会自适应降级为应用默认图标 (ncti.ico)
            if btn[0] == "AI圆角识别":
                icon_name = "AI圆角识别"
            elif btn[0] == "AI倒角识别":
                icon_name = "AI倒角识别"
            elif btn[0] == "AI沉头孔识别":
                icon_name = "混合盲孔识别"
            else:
                icon_name = "AI盲孔识别"

            icon = self.main_window.load_icon(icon_name)
            recognition_toolbar.AddTool(btn[1], btn[0], icon, shortHelp=btn[0])

        # 2. 分隔线与特征操作按钮
        recognition_toolbar.AddSeparator()

        icon_remove = self.main_window.load_icon("移除特征")
        recognition_toolbar.AddTool(self.button_remove_feature, "移除特征", icon_remove, shortHelp="移除特征")

        icon_export = self.main_window.load_icon("导出")
        recognition_toolbar.AddTool(self.button_export_feature, "导出特征", icon_export, shortHelp="导出特征")

        recognition_toolbar.Realize()

        # 设置识别选项卡的布局
        recognition_sizer = wx.BoxSizer(wx.VERTICAL)
        recognition_sizer.Add(recognition_toolbar, 0, wx.EXPAND)
        self.SetSizer(recognition_sizer)
        self.Layout()

    def bind_events(self):
        """绑定事件"""
        self.Bind(wx.EVT_TOOL, self.on_find_fillet_by_ai_click, id=self.button_find_fillet_ai)
        self.Bind(wx.EVT_TOOL, self.on_find_chamfer_by_ai_click, id=self.button_find_chamfer_ai)
        self.Bind(wx.EVT_TOOL, self.on_find_countersunk_hole_by_ai_click, id=self.button_find_countersunk_hole_ai)
        self.Bind(wx.EVT_TOOL, self.on_find_blind_hole_by_ai_click, id=self.button_find_blind_hole_ai)
        self.Bind(wx.EVT_TOOL, self.on_remove_feature_click, id=self.button_remove_feature)
        self.Bind(wx.EVT_TOOL, self.on_export_feature_click, id=self.button_export_feature)

    def show_recognition_progress(self, feature_name):
        self.main_window.status_bar.SetStatusText(f"正在执行 {feature_name}...")
        self.main_window.status_bar.Refresh()
        self.main_window.status_bar.Update()

    def on_find_fillet_by_ai_click(self, evt):
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText("没有doc对象")
            return
        self.show_recognition_progress("AI圆角识别")
        cell_ids, obj_names, _, _, _ = find_feature_by_ai(
            self.main_window.NCTI, self.main_window.doc,
            weight_path=self.main_window.pretrained_onnx_model_round,
            min_faces_num=0,
            max_faces_num=9,
            stat_path=self.main_window.stat_path_round,
            use_onnx=True
        )
        if cell_ids:
            self.main_window.show_selection(obj_names, cell_ids)
            self.main_window.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个倒圆角面")
            show_features_dialog(self.main_window, obj_names, cell_ids)
        else:
            wx.MessageBox("没有找到倒圆角面", "圆角识别", wx.OK | wx.ICON_INFORMATION)
            self.main_window.status_bar.SetStatusText("没有找到倒圆角面")

    def on_find_chamfer_by_ai_click(self, evt):
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText("没有doc对象")
            return
        self.show_recognition_progress("AI倒角识别")
        cell_ids, obj_names, _, _, _ = find_feature_by_ai(
            self.main_window.NCTI, self.main_window.doc,
            weight_path=self.main_window.pretrained_onnx_model_chamfer,
            stat_path=self.main_window.stat_path_chamfer,
            min_faces_num=0,
            max_faces_num=9,
            use_onnx=True
        )
        if cell_ids:
            self.main_window.show_selection(obj_names, cell_ids)
            self.main_window.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个倒角面")
            show_features_dialog(self.main_window, obj_names, cell_ids)
        else:
            wx.MessageBox("没有找到倒角面", "倒角识别", wx.OK | wx.ICON_INFORMATION)
            self.main_window.status_bar.SetStatusText("没有找到倒角面")

    def on_find_blind_hole_by_ai_click(self, evt):
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText("没有doc对象")
            return
        self.show_recognition_progress("AI盲孔识别")
        cell_ids, obj_names, _, _, _ = find_feature_by_ai(
            self.main_window.NCTI, self.main_window.doc,
            weight_path=self.main_window.pretrained_onnx_model_blind_hole,
            stat_path=self.main_window.stat_path_blind_hole,
            feature_name="blind_hole",
            min_faces_num=2,
            max_faces_num=5,
            use_onnx=True
        )
        if cell_ids:
            self.main_window.show_selection(obj_names, cell_ids)
            self.main_window.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个盲孔面")
            show_features_dialog(self.main_window, obj_names, cell_ids)
        else:
            wx.MessageBox("没有找到盲孔", "盲孔识别", wx.OK | wx.ICON_INFORMATION)
            self.main_window.status_bar.SetStatusText("没有找到盲孔")

    def on_find_countersunk_hole_by_ai_click(self, evt):
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText("没有doc对象")
            return
        self.show_recognition_progress("AI沉头孔识别")
        cell_ids, obj_names, _, _, _ = find_feature_by_ai(
            self.main_window.NCTI, self.main_window.doc,
            weight_path=self.main_window.pretrained_onnx_model_countersunk_hole,
            stat_path=self.main_window.stat_path_countersunk_hole,
            feature_name="countersunk_hole",
            min_faces_num=2,
            max_faces_num=8,
            use_onnx=True
        )
        if cell_ids:
            self.main_window.show_selection(obj_names, cell_ids)
            self.main_window.status_bar.SetStatusText(f"共查找到{len(cell_ids)}个沉头孔/沉孔面")
            show_features_dialog(self.main_window, obj_names, cell_ids)
        else:
            wx.MessageBox("没有找到沉头孔/沉孔", "沉头孔/沉孔识别", wx.OK | wx.ICON_INFORMATION)
            self.main_window.status_bar.SetStatusText("没有找到沉头孔/沉孔")

    def sync_selected_feature(self):
        """同步选中特征状态"""
        selection = self.main_window.NCTI.SelectionManager(self.main_window.doc)
        if selection.ObjectNames and selection.CellIDs:
            self.main_window.selected_feature = list(zip(selection.ObjectNames, selection.CellIDs))

    def on_remove_feature_click(self, evt):
        """移除特征点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText("没有doc对象")
            return
        self.sync_selected_feature()
        ret = remove_feature(self.main_window.doc, self.main_window.selected_feature)
        if ret:
            selection = self.main_window.NCTI.SelectionManager(self.main_window.doc)
            selection.ClearSelected()
            self.main_window.status_bar.SetStatusText("移除特征成功")
        else:
            self.main_window.status_bar.SetStatusText("没有特征被移除")
        self.main_window.cad_view.update_view()

    def on_export_feature_click(self, evt):
        """导出特征点击事件"""
        import tempfile
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText("没有doc对象")
            return

        self.sync_selected_feature()

        if not self.main_window.selected_feature:
            wx.MessageBox("请先选择要导出的特征", "导出特征", wx.OK | wx.ICON_INFORMATION)
            self.main_window.status_bar.SetStatusText("请先选择要导出的特征")
            return

        obj_names = set(f[0] for f in self.main_window.selected_feature)
        if len(obj_names) > 1:
            wx.MessageBox("暂不支持跨对象导出，请选择同一对象的面", "导出特征", wx.OK | wx.ICON_INFORMATION)
            self.main_window.status_bar.SetStatusText("暂不支持跨对象导出")
            return

        obj_name = self.main_window.selected_feature[0][0]
        cell_id_list = [f[1] for f in self.main_window.selected_feature]

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

        all_face = self.main_window.doc.FindAllFaces(obj_name)

        # 选中了全部面时直接导出，无需走删除-恢复流程
        if set(cell_id_list) == set(all_face):
            self.main_window.doc.RunCommand("cmd_ncti_export_file", file_path, obj_name)
            self.main_window.status_bar.SetStatusText(f"导出特征成功: {file_path}")
            return

        fd, temp_path = tempfile.mkstemp(suffix=".stp")
        os.close(fd)

        try:
            self.main_window.doc.RunCommand("cmd_ncti_export_file", temp_path, obj_name)

            unselected_face = list(set(all_face) - set(cell_id_list))
            self.main_window.doc.RunCommand("cmd_ncti_remove_faces", obj_name, unselected_face)
            self.main_window.doc.RunCommand("cmd_ncti_export_file", file_path, obj_name)

            self._reopen_and_import(temp_path)

            try:
                os.remove(temp_path)
            except OSError:
                pass

            self.main_window.status_bar.SetStatusText(f"导出特征成功: {file_path}")
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"导出特征失败: {e}")
            try:
                self._reopen_and_import(temp_path)
                os.remove(temp_path)
            except Exception:
                wx.MessageBox(
                    f"文档恢复失败，临时备份保存在:\n{temp_path}",
                    "导出特征",
                    wx.OK | wx.ICON_WARNING
                )

    def _reopen_and_import(self, path):
        from function.on_new_document import new_document_function
        self.main_window.doc.Close()
        view = new_document_function(self.main_window.NCTI, self.main_window.doc, self.main_window.cad_view.GetHandle())
        self.main_window.bind_view(view)
        self.main_window.set_select_mode()
        self.main_window.doc.RunCommand("cmd_ncti_import_file", path)
        self.main_window.doc.Zoom()
