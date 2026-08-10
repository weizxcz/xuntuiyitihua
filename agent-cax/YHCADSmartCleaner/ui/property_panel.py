import wx


def create_property_panel(parent):
    """属性面板"""
    property_panel = wx.Panel(parent=parent, style=wx.SUNKEN_BORDER)
    property_panel.SetBackgroundColour(wx.WHITE)

    prop_list = wx.ListCtrl(property_panel, size=(200, -1),
                            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.SUNKEN_BORDER)

    # 添加列
    prop_list.InsertColumn(0, "属性", width=100)
    prop_list.InsertColumn(1, "值", width=100)

    # 创建布局
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(prop_list, 1, wx.EXPAND | wx.ALL, 5)
    property_panel.SetSizer(sizer)

    # 返回创建的面板，由AUI管理器统一添加
    return property_panel
