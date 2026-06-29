import wx

from utils.reindex import IndexManager


class FeaturesDialog(wx.Dialog):
    """特征列表对话框"""
    def __init__(self, parent, main_frame, obj_names, cell_ids, scale_factor=1):
        """初始化特征列表对话框
        
        Args:
            parent: 父窗口
            main_frame: 主框架
            obj_names: 对象名称列表
            cell_ids: 面ID列表
            scale_factor: 缩放因子
        """
        wx.Dialog.__init__(self, parent, title="特征列表",
                          size=(int(600 * scale_factor), int(400 * scale_factor)),
                          style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        
        self.main_frame = main_frame
        self.obj_names = obj_names
        self.cell_ids = cell_ids
        self.scale_factor = scale_factor
        
        # 创建复选框状态字典，存储每个项的选中状态
        self.checkbox_states = {}
        
        # 初始化feature_list，用于存储选中的特征
        self.feature_list = []
        
        # 创建索引管理器
        self.index_manager = IndexManager(main_frame.doc, obj_names[0], cell_ids)
        
        # 初始化UI
        self._init_ui()

        # 绑定事件
        self._bind_events()
        
    def _init_ui(self):
        """初始化用户界面"""
        # 创建垂直布局管理器
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 使用ListCtrl替代TreeCtrl，实现带有复选框的列表
        self.list_ctrl = wx.ListCtrl(
            self, 
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN
        )

        self.draw_list_ctrl(self.cell_ids)

        # 添加列表控件到布局
        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 5)
        
        # 创建水平布局用于按钮
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.select_all_button = wx.Button(self, label="全选")
        self.deselect_all_button = wx.Button(self, label="取消全选")
        self.remove_face_button = wx.Button(self, label="移除面")
        self.add_face_button = wx.Button(self, label="添加面")
        self.find_face_by_name_button = wx.Button(self, label="名称找面")
        self.find_name_by_face_button = wx.Button(self, label="面找名称")

        self.remove_feature_button = wx.Button(self, label="清理")

        button_sizer.Add(self.select_all_button, 0, wx.ALL, 5)
        button_sizer.Add(self.deselect_all_button, 0, wx.ALL, 5)
        button_sizer.Add(self.remove_face_button, 0, wx.ALL, 5)
        button_sizer.Add(self.add_face_button, 0, wx.ALL, 5)
        button_sizer.Add(self.find_face_by_name_button, 0, wx.ALL, 5)
        button_sizer.Add(self.find_name_by_face_button, 0, wx.ALL, 5)
        button_sizer.Add(self.remove_feature_button, 0, wx.ALL, 5)
        
        # 添加按钮布局到主布局
        main_sizer.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        
        # 设置对话框布局
        self.SetSizer(main_sizer)
        self.Layout()
        self.Centre()
    
    def _bind_events(self):
        """绑定事件"""
        # 使用EVT_LEFT_DOWN事件，确保每次点击都能触发状态切换
        self.list_ctrl.Bind(wx.EVT_LEFT_DOWN, self.on_item_click)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.select_all_button.Bind(wx.EVT_BUTTON, self.on_select_all_face)
        self.deselect_all_button.Bind(wx.EVT_BUTTON, self.on_deselect_all_face)
        self.remove_face_button.Bind(wx.EVT_BUTTON, self.on_remove_face)
        self.find_face_by_name_button.Bind(wx.EVT_BUTTON, self.on_find_face_by_name)
        self.find_name_by_face_button.Bind(wx.EVT_BUTTON, self.on_find_name_by_face)
        self.add_face_button.Bind(wx.EVT_BUTTON, self.on_add_face)
        self.remove_feature_button.Bind(wx.EVT_BUTTON, self.on_remove_feature)

    def draw_list_ctrl(self, cell_ids):
        self.list_ctrl.ClearAll()

        # 添加列表列
        self.list_ctrl.InsertColumn(0, "选择", width=60)
        self.list_ctrl.InsertColumn(1, "对象名称", width=200)
        self.list_ctrl.InsertColumn(2, "面ID", width=100)

        # 填充特征数据
        item_index = 0
        for i, cell_id in enumerate(cell_ids):
            # 使用☑字符作为选中状态，□作为未选中状态
            self.list_ctrl.Append(["☑", self.obj_names[i], cell_id])
            # 初始化复选框状态为选中
            self.checkbox_states[item_index] = True
            item_index += 1
    
    def on_item_click(self, event):
        """列表项点击事件，用于切换复选框状态"""
        # 使用HitTest获取点击的位置
        pos = event.GetPosition()
        item, flags = self.list_ctrl.HitTest(pos)
        
        if item >= 0:
            # 切换复选框状态
            self.checkbox_states[item] = not self.checkbox_states[item]
            # 更新显示
            check_char = "☑" if self.checkbox_states[item] else "□"
            self.list_ctrl.SetItem(item, 0, check_char)
            # 确保事件继续传播，以便其他事件处理器也能响应
            event.Skip()

    def process_feature_list(self):
        """处理选中状态，更新feature_list"""
        # 清空现有列表
        self.feature_list.clear()

        # 遍历所有列表项
        item_count = self.list_ctrl.GetItemCount()

        for i in range(item_count):
            # 获取当前行的状态和数据
            check_char = self.list_ctrl.GetItem(i, 0).GetText()
            obj_name = self.list_ctrl.GetItem(i, 1).GetText()
            cell_id_str = self.list_ctrl.GetItem(i, 2).GetText()

            try:
                cell_id = int(cell_id_str)
                # 构建键值对
                feature_item = (obj_name, cell_id)

                if check_char == "☑":
                    # 添加到feature_list，避免重复
                    if feature_item not in self.feature_list:
                        self.feature_list.append(feature_item)
            except ValueError:
                # 如果转换失败，跳过该行
                continue

    def on_close(self, evt):
        """关闭事件"""
        # 处理选中状态，更新feature_list
        self.process_feature_list()
        self.main_frame.selected_feature = self.feature_list
        self.Destroy()

    def on_add_face(self, event):
        """添加面事件"""
        selection = self.main_frame.NCTI.SelectionManager(self.main_frame.doc)
        obj_name_list = selection.ObjectNames
        cell_id_list = selection.CellIDs
        item_index = len(self.checkbox_states)
        if obj_name_list and cell_id_list:
            for i, cell_id in enumerate(cell_id_list):
                # 使用☑字符作为选中状态，□作为未选中状态
                self.list_ctrl.Append(["☑", self.obj_names[i], cell_id])
                self.list_ctrl.SetItemData(item_index, item_index)  # 只存储索引
                # 初始化复选框状态为选中
                self.checkbox_states[item_index] = True
                item_index += 1
                self.index_manager.add_cell([cell_id])

    def highlight_face_name(self):
        """高亮显示选中的面名称"""
        selection = self.main_frame.NCTI.SelectionManager(self.main_frame.doc)
        obj_name_list = selection.ObjectNames
        cell_id_list = selection.CellIDs
        if obj_name_list and cell_id_list:
            self.highlight_item(obj_name_list[0], cell_id_list)

    def on_select_all_face(self, event):
        """全选事件"""
        cell_ids = []
        obj_names = []
        # 遍历所有列表项
        item_count = self.list_ctrl.GetItemCount()
        for i in range(item_count):
            # 使用☑字符作为选中状态，□作为未选中状态
            self.list_ctrl.SetItem(i, 0, "☑")
            # 初始化复选框状态为选中
            self.checkbox_states[i] = True
            self.list_ctrl.SetItemBackgroundColour(i, wx.Colour(255, 255, 150))
            cell_ids.append(int(self.list_ctrl.GetItem(i, 2).GetText()))
            obj_names.append(self.list_ctrl.GetItem(i, 1).GetText())
        self.main_frame.focus_selection(obj_names, cell_ids)

    def on_deselect_all_face(self, event):
        """全不选事件"""
        # 遍历所有列表项
        item_count = self.list_ctrl.GetItemCount()
        for i in range(item_count):
            # 使用□字符作为未选中状态
            self.list_ctrl.SetItem(i, 0, "□")
            # 初始化复选框状态为未选中
            self.checkbox_states[i] = False
            self.list_ctrl.SetItemBackgroundColour(i, wx.Colour(255, 255, 255))

    def on_remove_face(self, event):
        """移除未选中的面"""
        # 从后向前遍历，避免索引变化问题
        item_count = self.list_ctrl.GetItemCount()
        
        for i in range(item_count - 1, -1, -1):
            # 获取当前行的复选框状态
            check_char = self.list_ctrl.GetItem(i, 0).GetText()
            
            # 检查是否未选中
            if check_char == "☑":
                # 移除该行
                cell_id_str = self.list_ctrl.GetItem(i, 2).GetText()
                cell_id = int(cell_id_str)
                self.list_ctrl.DeleteItem(i)

                # 同时从checkbox_states中移除
                if i in self.checkbox_states:
                    del self.checkbox_states[i]
                # 更新剩余项的索引
                for j in range(i, item_count - 1):
                    if j + 1 in self.checkbox_states:
                        self.checkbox_states[j] = self.checkbox_states.pop(j + 1)
                self.index_manager.remove_cell([cell_id])

    def on_find_face_by_name(self, event):
        """查找并高亮选中的面"""
        selected_obj_names = []
        selected_cell_ids = []
        
        # 遍历所有列表项
        item_count = self.list_ctrl.GetItemCount()
        
        for i in range(item_count):
            # 获取当前行的复选框状态
            check_char = self.list_ctrl.GetItem(i, 0).GetText()
            
            # 检查是否选中
            if check_char == "☑":
                # 获取对象名称和cell_id
                obj_name = self.list_ctrl.GetItem(i, 1).GetText()
                cell_id_str = self.list_ctrl.GetItem(i, 2).GetText()
                
                try:
                    cell_id = int(cell_id_str)
                    selected_obj_names.append(obj_name)
                    selected_cell_ids.append(cell_id)
                except ValueError:
                    # 如果转换失败，跳过该行
                    continue
        
        # 调用main_frame.focus_selection高亮对应的面
        if selected_obj_names and selected_cell_ids:
            self.main_frame.focus_selection(selected_obj_names, selected_cell_ids)

    def on_find_name_by_face(self, event):
        self.highlight_face_name()

    def on_remove_feature(self, event):
        """移除选中的特征"""
        # 收集要移除的面
        to_remove_cell_ids = []
        object_names = []
        
        # 从后向前遍历，避免索引变化问题
        item_count = self.list_ctrl.GetItemCount()
        
        for i in range(item_count - 1, -1, -1):
            # 获取当前行的复选框状态
            check_char = self.list_ctrl.GetItem(i, 0).GetText()
            
            # 检查是否未选中
            if check_char == "☑":
                # 获取对象名称和cell_id
                obj_name = self.list_ctrl.GetItem(i, 1).GetText()
                cell_id_str = self.list_ctrl.GetItem(i, 2).GetText()
                
                try:
                    cell_id = int(cell_id_str)
                    to_remove_cell_ids.append(cell_id)
                    object_names.append(obj_name)
                    
                    # 移除该行
                    self.list_ctrl.DeleteItem(i)
                    # 同时从checkbox_states中移除
                    if i in self.checkbox_states:
                        del self.checkbox_states[i]
                    # 更新剩余项的索引
                    for j in range(i, item_count - 1):
                        if j + 1 in self.checkbox_states:
                            self.checkbox_states[j] = self.checkbox_states.pop(j + 1)
                except ValueError:
                    # 如果转换失败，跳过该行
                    continue
        
        # 调用doc.RunCommand方法移除stp的面
        if to_remove_cell_ids and object_names:
            # 使用第一个对象名称
            self.main_frame.doc.RunCommand("cmd_ncti_remove_features", object_names[0], to_remove_cell_ids)
            self.index_manager.remove_cell(to_remove_cell_ids)

        self.index_manager.reindex()
        self.draw_list_ctrl(self.index_manager.cell_ids)

    def highlight_item(self, obj_name, cell_ids):
        """高亮显示匹配的列表项
        
        Args:
            obj_name (str): 要匹配的对象名称
            cell_ids (list): 要匹配的面ID列表
        """
        # 如果cell_ids为空，直接退出函数
        if not cell_ids:
            return
        
        # 遍历所有列表项
        item_count = self.list_ctrl.GetItemCount()
        
        for i in range(item_count):
            # 获取当前行的对象名称和cell_id
            current_obj_name = self.list_ctrl.GetItem(i, 1).GetText()
            current_cell_id_str = self.list_ctrl.GetItem(i, 2).GetText()
            
            try:
                # 转换为整数进行比较
                current_cell_id = int(current_cell_id_str)
                
                # 检查是否匹配
                if current_obj_name == obj_name and current_cell_id in cell_ids:
                    # 选中该行
                    self.list_ctrl.Select(i)
                    # 确保该行可见
                    self.list_ctrl.EnsureVisible(i)
                    # 设置焦点到该行
                    self.list_ctrl.SetItemState(i, wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED, 
                                          wx.LIST_STATE_FOCUSED | wx.LIST_STATE_SELECTED)
                    # 高亮显示该行
                    self.list_ctrl.SetItemBackgroundColour(i, wx.Colour(255, 255, 150))
                    # 行前更改为"☑"
                    self.list_ctrl.SetItem(i, 0, "☑")
                    # 更新复选框状态
                    self.checkbox_states[i] = True
                    # 如果只有一个元素，找到后可以退出
                    if len(cell_ids) == 1:
                        break
            except ValueError:
                # 如果转换失败，跳过该行
                continue

def show_features_dialog(main_frame: wx.Frame, obj_names, cell_ids, scale_factor:float=1):
    """显示特征列表对话框"""
    if not cell_ids:
        return None
    
    # 创建并显示对话框
    dialog = FeaturesDialog(None, main_frame, obj_names, cell_ids, scale_factor)
    dialog.Show()
