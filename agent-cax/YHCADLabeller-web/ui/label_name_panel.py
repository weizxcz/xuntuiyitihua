import wx


_PRESET_FEATURES = [
    "round", "chamfer", "countersink_hole",
    "counterbore_hole", "through_hole", "blind_hole",
]


class LabelNamePanel(wx.Panel):
    """特征名称编辑面板"""
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.feature_to_id = {}  # 用户定义的特征名→ID映射 {name: id}
        self.next_id = 1          # 下一个可分配的ID（从1开始）
        self.init_ui()
        self.bind_events()

    def init_ui(self):
        feature_sizer = wx.BoxSizer(wx.VERTICAL)

        # 已添加的特征列表
        self.name_list = wx.ListBox(self, wx.ID_ANY, size=(-1, 200))
        feature_sizer.Add(self.name_list, 1, wx.EXPAND | wx.ALL, 5)

        # 预设特征列表（多选）
        self.preset_list = wx.ListBox(self, wx.ID_ANY, size=(-1, 120),
                                      style=wx.LB_EXTENDED,
                                      choices=_PRESET_FEATURES)
        feature_sizer.Add(self.preset_list, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        # 按钮
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add = wx.Button(self, wx.ID_ANY, "添加")
        self.btn_remove = wx.Button(self, wx.ID_ANY, "移除")
        button_sizer.Add(self.btn_add, 0, wx.ALL, 5)
        button_sizer.Add(self.btn_remove, 0, wx.ALL, 5)
        feature_sizer.Add(button_sizer, 0, wx.ALIGN_CENTER)

        self.SetSizer(feature_sizer)
        self.Layout()

    def bind_events(self):
        """绑定事件"""
        self.Bind(wx.EVT_BUTTON, self.on_add_button_click, self.btn_add)
        self.Bind(wx.EVT_BUTTON, self.on_remove_button_click, self.btn_remove)
        self.Bind(wx.EVT_LISTBOX, self.on_list_select, self.name_list)

    def get_feature_id(self, name):
        """获取特征名对应的ID，如果不存在则自动分配一个新ID"""
        if name not in self.feature_to_id:
            self.feature_to_id[name] = self.next_id
            self.next_id += 1
        return self.feature_to_id[name]

    @property
    def feature_mapping(self):
        """对外暴露的特征映射字典"""
        return self.feature_to_id.copy()

    def on_add_button_click(self, event):
        """将预设列表中选中的特征添加到上方列表"""
        indices = self.preset_list.GetSelections()
        if not indices:
            self.main_window.status_bar.SetStatusText("请先在下方选择要添加的特征")
            return
        first_added = -1
        duplicates = []
        for idx in indices:
            name = self.preset_list.GetString(idx)
            if name in self.feature_to_id:
                duplicates.append(name)
                continue
            self.get_feature_id(name)
            pos = self.name_list.Append(name)
            if first_added < 0:
                first_added = pos
        # 取消预设列表的选中状态
        for i in self.preset_list.GetSelections():
            self.preset_list.Deselect(i)
        # 更新状态栏
        if first_added >= 0:
            self.name_list.SetSelection(first_added)
            self.main_window.selected_label_name = self.name_list.GetString(first_added)
            self.main_window.status_bar.SetStatusText("已添加特征")
        elif duplicates:
            self.main_window.status_bar.SetStatusText("⚠ 已添加该特征")

    def on_remove_button_click(self, event):
        """移除按钮点击事件"""
        selected_index = self.name_list.GetSelection()
        if selected_index != wx.NOT_FOUND:
            name = self.name_list.GetString(selected_index)
            # 从映射中移除
            if name in self.feature_to_id:
                del self.feature_to_id[name]
            self.name_list.Delete(selected_index)

    def on_list_select(self, event):
        """列表选择事件"""
        selected_index = event.GetSelection()
        if selected_index != wx.NOT_FOUND:
            self.main_window.selected_label_name = event.GetString()
