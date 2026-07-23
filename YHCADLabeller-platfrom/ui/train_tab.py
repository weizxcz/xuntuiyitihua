import wx

from function.on_train import (
    select_dataset_folder, select_train_feature, generate_graph, train_model,
)
from function.on_convert_model import convert_model_to_onnx


class TrainTabPanel(wx.Panel):
    """训练选项卡面板：模型架构选择 + 数据集/训练特征/生成graph/训练神经网络工具栏。"""
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.parent = parent
        self.init_ui()
        self.bind_events()

    def init_ui(self):
        """初始化UI"""
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        toolbar_panel = wx.Panel(self)
        toolbar_panel.SetBackgroundColour(wx.WHITE)
        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 模型架构组：下拉菜单，目前只有 AAGNet，后续增加模型时再补选项
        model_group = wx.StaticBoxSizer(wx.StaticBox(toolbar_panel, wx.ID_ANY, "模型架构"), wx.HORIZONTAL)
        self.model_choice = wx.ComboBox(
            toolbar_panel, wx.ID_ANY, value="AAGNet", choices=["AAGNet"], style=wx.CB_READONLY
        )
        model_group.Add(self.model_choice, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar_sizer.Add(model_group, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar_sizer.AddSpacer(20)

        train_toolbar = wx.ToolBar(toolbar_panel, wx.ID_ANY,
                                   style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT | wx.TB_NODIVIDER)
        bitmap_size = max(36, int(36 * self.main_window.scale_factor))
        train_toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        toolbar_height = max(60, int(80 * self.main_window.scale_factor))
        train_toolbar.SetMinSize((-1, toolbar_height))
        train_toolbar.SetSize((-1, toolbar_height))
        train_toolbar.SetBackgroundColour(wx.WHITE)
        # 按钮间距过窄的问题：默认 packing 只有几像素，这里放宽一些
        train_toolbar.SetToolPacking(14)
        train_toolbar.SetToolSeparation(24)
        train_toolbar.SetMargins(8, 4)

        self.button_select_dataset = wx.NewIdRef()
        self.button_select_feature = wx.NewIdRef()
        self.button_generate_graph = wx.NewIdRef()
        self.button_train_model = wx.NewIdRef()
        self.button_convert_model = wx.NewIdRef()

        # 按钮分两组，用分隔线隔开：数据准备 / 执行
        # （曲线与日志已内嵌在训练页中央区，无需独立按钮）
        icon = self.main_window.load_icon("数据集")
        train_toolbar.AddTool(self.button_select_dataset, "数据集", icon, shortHelp="数据集")
        icon = self.main_window.load_icon("选择训练特征")
        train_toolbar.AddTool(self.button_select_feature, "选择训练特征", icon, shortHelp="选择训练特征")

        train_toolbar.AddSeparator()

        icon = self.main_window.load_icon("生成graph")
        train_toolbar.AddTool(self.button_generate_graph, "生成graph", icon, shortHelp="生成graph")
        icon = self.main_window.load_icon("训练神经网络")
        train_toolbar.AddTool(self.button_train_model, "训练神经网络", icon, shortHelp="训练神经网络")
        train_toolbar.AddTool(self.button_convert_model, "模型转换", icon, shortHelp="将 PTH 权重转换为 ONNX")

        train_toolbar.Realize()

        toolbar_sizer.Add(train_toolbar, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)

        toolbar_panel.SetSizer(toolbar_sizer)
        toolbar_panel.Layout()

        main_sizer.Add(toolbar_panel, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)
        self.Layout()

    def bind_events(self):
        """绑定事件"""
        self.Bind(wx.EVT_TOOL, self.on_select_dataset_click, id=self.button_select_dataset)
        self.Bind(wx.EVT_TOOL, self.on_select_feature_click, id=self.button_select_feature)
        self.Bind(wx.EVT_TOOL, self.on_generate_graph_click, id=self.button_generate_graph)
        self.Bind(wx.EVT_TOOL, self.on_train_model_click, id=self.button_train_model)
        self.Bind(wx.EVT_TOOL, self.on_convert_model_click, id=self.button_convert_model)

    def on_select_dataset_click(self, evt):
        select_dataset_folder(self.main_window)

    def on_select_feature_click(self, evt):
        select_train_feature(self.main_window)

    def on_generate_graph_click(self, evt):
        generate_graph(self.main_window)

    def on_train_model_click(self, evt):
        train_model(self.main_window)

    def on_convert_model_click(self, evt):
        convert_model_to_onnx(self.main_window)
