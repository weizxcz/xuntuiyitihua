import wx


def create_assembly_panel(parent):
    """创建左侧装配树面板"""
    assembly_panel = wx.Panel(parent=parent, style=wx.SUNKEN_BORDER)
    assembly_panel.SetBackgroundColour(wx.WHITE)

    # 创建树控件
    tree = wx.TreeCtrl(assembly_panel, size=(200, -1), style=wx.TR_DEFAULT_STYLE)

    # 添加根节点
    root = tree.AddRoot("装配体")

    # 添加子节点
    part1 = tree.AppendItem(root, "零件[OCC GMSH]")

    # 展开所有节点
    tree.ExpandAll()

    # 创建布局
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(tree, 1, wx.EXPAND | wx.ALL, 5)
    assembly_panel.SetSizer(sizer)

    # 返回创建的面板，由AUI管理器统一添加
    return assembly_panel
