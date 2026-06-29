import wx


_FEATURE_TYPES = ["round", "chamfer", "countersink_hole", "counterbore_hole", "through_hole", "blind_hole"]


class LabelParamsDialog(wx.Dialog):
    def __init__(self, parent, title="标注参数", defaults=None, show_feature_type=True):
        super().__init__(parent, title=title, size=(400, 280 if show_feature_type else 230))
        defaults = defaults or {}

        sizer = wx.BoxSizer(wx.VERTICAL)

        rows = 3 if not show_feature_type else 4
        grid = wx.FlexGridSizer(rows, 2, 8, 8)
        grid.AddGrowableCol(1, 1)

        grid.Add(wx.StaticText(self, label="零件名称:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.text_name = wx.TextCtrl(self, value=defaults.get("name", ""))
        grid.Add(self.text_name, 1, wx.EXPAND)

        if show_feature_type:
            ft_default = defaults.get("feature_type", "")
            if ft_default:
                # 有预设值时显示为只读文本
                grid.Add(wx.StaticText(self, label="特征类型:"), 0, wx.ALIGN_CENTER_VERTICAL)
                self.text_feature_display = wx.TextCtrl(self, value=ft_default, style=wx.TE_READONLY)
                grid.Add(self.text_feature_display, 1, wx.EXPAND)
                self.choice_feature = None
            else:
                # 无预设值时显示下拉框（导入场景）
                grid.Add(wx.StaticText(self, label="特征类型:"), 0, wx.ALIGN_CENTER_VERTICAL)
                self.choice_feature = wx.Choice(self, choices=_FEATURE_TYPES)
                default_ft = defaults.get("feature_type", "")
                if default_ft in _FEATURE_TYPES:
                    self.choice_feature.SetSelection(_FEATURE_TYPES.index(default_ft))
                grid.Add(self.choice_feature, 1, wx.EXPAND)
        else:
            self.choice_feature = None

        grid.Add(wx.StaticText(self, label="行业:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.text_industry = wx.TextCtrl(self, value=defaults.get("industry", ""))
        grid.Add(self.text_industry, 1, wx.EXPAND)

        grid.Add(wx.StaticText(self, label="用户:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.text_user = wx.TextCtrl(self, value=defaults.get("user", ""))
        grid.Add(self.text_user, 1, wx.EXPAND)

        sizer.Add(grid, 1, wx.ALL | wx.EXPAND, 15)

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.SetSizer(sizer)
        self.Centre()

    def get_params(self):
        if self.choice_feature:
            ft_idx = self.choice_feature.GetSelection()
            feature_type = _FEATURE_TYPES[ft_idx] if ft_idx >= 0 else ""
        else:
            feature_type = ""
        return {
            "name": self.text_name.GetValue().strip(),
            "feature_type": feature_type,
            "industry": self.text_industry.GetValue().strip(),
            "user": self.text_user.GetValue().strip(),
        }
