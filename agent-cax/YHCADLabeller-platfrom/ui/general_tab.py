import wx

from function.on_visualize import (
    viz_attributes, viz_topology, viz_uvgrid, viz_pointcloud, viz_multiview,
)


class GeneralTabPanel(wx.Panel):
    """选择/显示选项卡面板（在原两组 CheckBox 右侧追加 5 个可视化按钮 — 移植自 YHDataConverter）。"""
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.parent = parent
        self.init_ui()
        self.bind_events()

    def init_ui(self):
        """初始化UI"""
        # 创建垂直布局管理器
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---- 单个水平工具栏：显示模式 + 选择模式 + 5 个可视化按钮（同一行）----
        toolbar_panel = wx.Panel(self)
        # 工具栏外壳：白色背景（5 个按钮嵌入此面板）
        toolbar_panel.SetBackgroundColour(wx.WHITE)
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

        # 5 个可视化按钮（追加在选择模式右侧，与原 CheckBox 共占同一行）
        viz_toolbar = wx.ToolBar(toolbar_panel, wx.ID_ANY,
                                 style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT | wx.TB_NODIVIDER)
        bitmap_size = max(36, int(36 * self.main_window.scale_factor))
        viz_toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        # 工具栏背景：白色
        viz_toolbar.SetBackgroundColour(wx.WHITE)
        # 与 file_tab 风格保持一致：显式声明高度，避免被 top_panel 截断
        viz_toolbar_height = max(60, int(80 * self.main_window.scale_factor))
        viz_toolbar.SetMinSize((-1, viz_toolbar_height))
        viz_toolbar.SetSize((-1, viz_toolbar_height))

        self.btn_viz_attrs = wx.NewIdRef()
        self.btn_viz_graph = wx.NewIdRef()
        self.btn_viz_uvgrid = wx.NewIdRef()
        self.btn_viz_pointcloud = wx.NewIdRef()
        self.btn_viz_multiview = wx.NewIdRef()

        viz_buttons = [
            ("多视图可视化", self.btn_viz_multiview),
            ("属性可视化", self.btn_viz_attrs),
            ("拓扑可视化", self.btn_viz_graph),
            ("网格可视化", self.btn_viz_uvgrid),
            ("点云可视化", self.btn_viz_pointcloud),
        ]
        for label, btn_id in viz_buttons:
            icon = self.main_window.load_icon("ncti")
            viz_toolbar.AddTool(btn_id, label, icon, shortHelp=label)
        viz_toolbar.Realize()
        self.viz_toolbar = viz_toolbar

        toolbar_sizer.Add(viz_toolbar, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        toolbar_panel.SetSizer(toolbar_sizer)
        toolbar_panel.Layout()

        main_sizer.Add(toolbar_panel, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        self.Layout()

    def bind_events(self):
        """绑定事件"""
        # 5 个可视化按钮
        self.Bind(wx.EVT_TOOL, self.on_viz_attrs, id=self.btn_viz_attrs)
        self.Bind(wx.EVT_TOOL, self.on_viz_graph, id=self.btn_viz_graph)
        self.Bind(wx.EVT_TOOL, self.on_viz_uvgrid, id=self.btn_viz_uvgrid)
        self.Bind(wx.EVT_TOOL, self.on_viz_pointcloud, id=self.btn_viz_pointcloud)
        self.Bind(wx.EVT_TOOL, self.on_viz_multiview, id=self.btn_viz_multiview)

        # 原有 checkbox 绑定
        self.show_body.Bind(wx.EVT_CHECKBOX, self.on_show_body)
        self.show_face.Bind(wx.EVT_CHECKBOX, self.on_show_face)
        self.show_edge.Bind(wx.EVT_CHECKBOX, self.on_show_edge)
        self.show_vertex.Bind(wx.EVT_CHECKBOX, self.on_show_vertex)
        self.select_body.Bind(wx.EVT_CHECKBOX, self.on_select_body)
        self.select_face.Bind(wx.EVT_CHECKBOX, self.on_select_face)
        self.select_edge.Bind(wx.EVT_CHECKBOX, self.on_select_edge)
        self.select_vertex.Bind(wx.EVT_CHECKBOX, self.on_select_vertex)

    def on_viz_attrs(self, evt):
        viz_attributes(self.main_window)
        evt.Skip()

    def on_viz_graph(self, evt):
        viz_topology(self.main_window)
        evt.Skip()

    def on_viz_uvgrid(self, evt):
        viz_uvgrid(self.main_window)
        evt.Skip()

    def on_viz_pointcloud(self, evt):
        viz_pointcloud(self.main_window)
        evt.Skip()

    def on_viz_multiview(self, evt):
        viz_multiview(self.main_window)
        evt.Skip()

    def on_show_body(self, evt):
        """显示模式 - 体 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()

        self.show_body.SetValue(state)
        self.show_face.SetValue(state)
        self.show_edge.SetValue(state)
        self.show_vertex.SetValue(state)

        if state:
            self.main_window.doc.SetVisualMode(1, 1, 1)
            self.show_face.Enable(not state)
            self.show_edge.Enable(not state)
            self.show_vertex.Enable(not state)
        else:
            self.main_window.doc.SetVisualMode(0, 0, 0)
            self.show_face.Enable(not state)
            self.show_edge.Enable(not state)
            self.show_vertex.Enable(not state)

    def on_show_face(self, evt):
        """显示模式 - 面 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        is_show_edge = self.show_edge.IsChecked()
        is_show_vertex = self.show_vertex.IsChecked()
        self.main_window.doc.SetVisualMode(int(state), int(is_show_edge), int(is_show_vertex))

    def on_show_edge(self, evt):
        """显示模式 - 线 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        is_show_face = self.show_face.IsChecked()
        is_show_vertex = self.show_vertex.IsChecked()
        self.main_window.doc.SetVisualMode(int(is_show_face), int(state), int(is_show_vertex))

    def on_show_vertex(self, evt):
        """显示模式 - 点 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        is_show_face = self.show_face.IsChecked()
        is_show_edge = self.show_edge.IsChecked()
        self.main_window.doc.SetVisualMode(int(is_show_face), int(is_show_edge), int(state))

    def on_select_body(self, evt):
        """选择模式 - 体 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.main_window.doc.SetSelBody(int(state))
        if not state:
            selection = self.main_window.NCTI.SelectionManager(self.main_window.doc)
            selection.ClearSelected()
        else:
            self.select_face.SetValue(True)
            self.select_edge.SetValue(True)
            self.select_vertex.SetValue(True)

            self.main_window.doc.SetSelFace(state)
            self.main_window.doc.SetSelLine(state)
            self.main_window.doc.SetSelVertex(state)

    def on_select_face(self, evt):
        """选择模式 - 面 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.main_window.doc.SetSelFace(state)
        if not state:
            self.main_window.doc.SetSelBody(False)
            self.select_body.SetValue(False)

    def on_select_edge(self, evt):
        """选择模式 - 线 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.main_window.doc.SetSelLine(state)
        if not state:
            self.main_window.doc.SetSelBody(False)
            self.select_body.SetValue(False)

    def on_select_vertex(self, evt):
        """选择模式 - 点 点击事件"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText(f"没有doc对象")
            return
        state = evt.IsChecked()
        self.main_window.doc.SetSelVertex(state)
        if not state:
            self.main_window.doc.SetSelBody(False)
            self.select_body.SetValue(False)
