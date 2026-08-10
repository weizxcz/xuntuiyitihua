from collections import deque

import wx


class LabeledFeaturesPanel(wx.Panel):
    """已标注特征面板"""
    # 列表列索引常量
    _COL_FEATURE = 0
    _COL_OBJECT = 1
    _COL_FACE_ID = 2
    _COL_BOTTOM = 3
    _COL_ACTION = 4  # [+] 按钮列

    _MAX_UNDO = 50

    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        self.NCTI = self.main_window.NCTI
        self.doc = self.main_window.doc
        self.label_result = {}
        self._undo_stack = deque(maxlen=self._MAX_UNDO)
        self.init_ui()
        self.bind_events()

    def init_ui(self):
        labeled_sizer = wx.BoxSizer(wx.VERTICAL)

        self.btn_add = wx.Button(self, wx.ID_ANY, "标注")
        self.btn_bottom = wx.Button(self, wx.ID_ANY, "标注底面")
        self.btn_show = wx.Button(self, wx.ID_ANY, "高亮")
        self.btn_batch_label = wx.Button(self, wx.ID_ANY, "批量标注")
        self.btn_batch_bottom = wx.Button(self, wx.ID_ANY, "批量标注底面")
        self.btn_remove = wx.Button(self, wx.ID_ANY, "移除")

        # 以最宽按钮"批量标注底面"为基准统一宽度
        ref_width, _ = self.btn_batch_bottom.GetTextExtent(
            self.btn_batch_bottom.GetLabel())
        btn_width = ref_width + int(28 * self.main_window.scale_factor)

        for btn in (self.btn_add, self.btn_bottom, self.btn_show,
                    self.btn_batch_label, self.btn_batch_bottom, self.btn_remove):
            btn.SetMinSize((btn_width, -1))

        grid = wx.GridSizer(2, 3, 3, 3)
        grid.Add(self.btn_add, 0, wx.EXPAND)
        grid.Add(self.btn_bottom, 0, wx.EXPAND)
        grid.Add(self.btn_show, 0, wx.EXPAND)
        grid.Add(self.btn_batch_label, 0, wx.EXPAND)
        grid.Add(self.btn_batch_bottom, 0, wx.EXPAND)
        grid.Add(self.btn_remove, 0, wx.EXPAND)
        labeled_sizer.Add(grid, 0, wx.ALIGN_CENTER | wx.ALL, 3)

        self.label_name = wx.StaticText(self, wx.ID_ANY, "已标注特征列表:")
        labeled_sizer.Add(self.label_name, 0, wx.ALL, 5)
        self.labeled_list = wx.ListCtrl(self, wx.ID_ANY, size=(-1, 300), style=wx.LC_REPORT)
        self.labeled_list.InsertColumn(self._COL_FEATURE, "特征")
        self.labeled_list.InsertColumn(self._COL_OBJECT, "对象")
        self.labeled_list.InsertColumn(self._COL_FACE_ID, "面ID")
        self.labeled_list.InsertColumn(self._COL_BOTTOM, "底面")
        self.labeled_list.InsertColumn(self._COL_ACTION, "[+]")
        self.labeled_list.SetColumnWidth(self._COL_FEATURE, 70)
        self.labeled_list.SetColumnWidth(self._COL_OBJECT, 70)
        self.labeled_list.SetColumnWidth(self._COL_FACE_ID, 140)
        self.labeled_list.SetColumnWidth(self._COL_BOTTOM, 90)
        self.labeled_list.SetColumnWidth(self._COL_ACTION, 90)
        labeled_sizer.Add(self.labeled_list, 1, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(labeled_sizer)
        self.Layout()

    def bind_events(self):
        self.Bind(wx.EVT_BUTTON, self.on_add_button_click, self.btn_add)
        self.Bind(wx.EVT_BUTTON, self.on_remove_button_click, self.btn_remove)
        self.Bind(wx.EVT_BUTTON, self.on_show_button_click, self.btn_show)
        self.Bind(wx.EVT_BUTTON, self.on_batch_label_button_click, self.btn_batch_label)
        self.Bind(wx.EVT_BUTTON, self.on_bottom_button_click, self.btn_bottom)
        self.Bind(wx.EVT_BUTTON, self.on_batch_bottom_button_click, self.btn_batch_bottom)
        self.labeled_list.Bind(wx.EVT_LEFT_DOWN, self.on_list_left_down)

    # ─── 公共工具方法 ───────────────────────────────────────────────

    def get_selected_cell_ids_and_names(self):
        selection = self.NCTI.SelectionManager(self.doc)
        return selection.ObjectNames, selection.CellIDs

    @staticmethod
    def _parse_face_ids(cell_id_str):
        """解析逗号分隔的面ID字符串"""
        return [int(x) for x in cell_id_str.split(",") if x.strip()]

    def _assign_feature_instance(self, feature_name, cell_ids):
        """为给定特征名分配新的实例批次 ID，并将所有面映射到该实例"""
        counter = self.main_window.feature_instance_counter
        inst_id = counter.get(feature_name, 0)
        for cid in cell_ids:
            self.main_window.face_to_instance[cid] = (feature_name, inst_id)
        counter[feature_name] = inst_id + 1
        return inst_id

    def _append_faces_to_row(self, row_index, cell_ids, column):
        existing_str = self.labeled_list.GetItemText(row_index, column)
        existing_ids = self._parse_face_ids(existing_str) if existing_str else []
        merged_ids = sorted(set(existing_ids) | set(cell_ids))
        self.labeled_list.SetItem(row_index, column, ",".join(str(cid) for cid in merged_ids))
        return merged_ids

    def _sync_bottom_to_face_ids(self, row_index, cell_ids):
        """将底面ID同步到面ID列（如果该底面不在面ID中）"""
        face_id_str = self.labeled_list.GetItemText(row_index, self._COL_FACE_ID)
        existing_face_ids = self._parse_face_ids(face_id_str) if face_id_str else []
        missing = [cid for cid in cell_ids if cid not in existing_face_ids]
        if missing:
            self._append_faces_to_row(row_index, missing, self._COL_FACE_ID)

    def _add_row(self, label_name, obj_name, face_ids, bottom_ids=None):
        name = obj_name[0] if obj_name else ""
        idx = self.labeled_list.InsertItem(self.labeled_list.GetItemCount(), "")
        self.labeled_list.SetItem(idx, self._COL_FEATURE, label_name)
        self.labeled_list.SetItem(idx, self._COL_OBJECT, name)
        face_id_str = ",".join(str(f) for f in face_ids) if face_ids else ""
        bottom_str = ",".join(str(b) for b in (bottom_ids or [])) if bottom_ids else ""
        self.labeled_list.SetItem(idx, self._COL_FACE_ID, face_id_str)
        self.labeled_list.SetItem(idx, self._COL_BOTTOM, bottom_str)
        self.labeled_list.SetItemData(idx, 0)

    def _get_instance_face_ids(self, feature_name, inst_id):
        """获取属于同一特征名和实例批次的所有面ID"""
        return [
            f for f, (fname, iid) in self.main_window.face_to_instance.items()
            if fname == feature_name and iid == inst_id
        ]

    def _resolve_inst_id(self, face_ids):
        """从一批面ID中获取所属实例批次ID，取第一个有记录的"""
        for fid in face_ids:
            if fid in self.main_window.face_to_instance:
                return self.main_window.face_to_instance[fid][1]
        return 0

    def _get_rows(self):
        rows = []
        for i in range(self.labeled_list.GetItemCount()):
            rows.append((
                self.labeled_list.GetItemText(i, self._COL_FEATURE),
                self.labeled_list.GetItemText(i, self._COL_OBJECT),
                self.labeled_list.GetItemText(i, self._COL_FACE_ID),
                self.labeled_list.GetItemText(i, self._COL_BOTTOM),
            ))
        return rows

    def _save_snapshot(self):
        snapshot = {
            'label_result': {k: set(v) for k, v in self.label_result.items()},
            'bottom_faces': {k: (v[0], list(v[1])) for k, v in self.main_window.bottom_faces.items()},
            'face_to_instance': dict(self.main_window.face_to_instance),
            'feature_instance_counter': dict(self.main_window.feature_instance_counter),
            'rows': self._get_rows(),
        }
        self._undo_stack.append(snapshot)

    def undo(self):
        if not self._undo_stack:
            self.main_window.status_bar.SetStatusText("没有可撤销的操作")
            return

        snapshot = self._undo_stack.pop()

        self.label_result = snapshot['label_result']
        self.main_window.bottom_faces = snapshot['bottom_faces']
        self.main_window.face_to_instance = snapshot['face_to_instance']
        self.main_window.feature_instance_counter = snapshot['feature_instance_counter']

        self.labeled_list.DeleteAllItems()
        self.labeled_list.Freeze()
        try:
            for feature, obj, face_id, bottom in snapshot['rows']:
                self._add_row(feature, [obj], [] if not face_id else self._parse_face_ids(face_id),
                              [] if not bottom else self._parse_face_ids(bottom))
        finally:
            self.labeled_list.Thaw()

        self.main_window.status_bar.SetStatusText(f"已撤销 (剩余 {len(self._undo_stack)} 步)")
        self._mark_label_dirty()

    def clear_undo_history(self):
        self._undo_stack.clear()

    # ─── 事件处理 ──────────────────────────────────────────────────

    def on_list_left_down(self, event):
        rel_x = event.GetX()
        abs_x = rel_x + self.labeled_list.GetScrollPos(wx.HORIZONTAL)
        row_index, _ = self.labeled_list.HitTest((rel_x, event.GetY()))
        if row_index == wx.NOT_FOUND:
            event.Skip()
            return

        col_widths = [self.labeled_list.GetColumnWidth(i) for i in range(5)]
        cum_width = 0
        col = -1
        for i, w in enumerate(col_widths):
            if abs_x < cum_width + w:
                col = i
                break
            cum_width += w

        if col == self._COL_ACTION:
            screen_pos = self.labeled_list.ClientToScreen((rel_x, event.GetY()))
            self._show_add_face_menu(row_index, screen_pos)
        event.Skip()

    def _show_add_face_menu(self, row_index, screen_pos):
        """在指定屏幕位置显示添加面的弹出菜单"""
        menu = wx.Menu()
        id_face = wx.NewIdRef()
        id_bottom = wx.NewIdRef()
        menu.Append(id_face, "添加到 面ID")
        menu.Append(id_bottom, "添加到 底面")

        def on_menu_add_face(cmd):
            col = self._COL_FACE_ID if cmd == id_face else self._COL_BOTTOM
            _, cell_ids = self.get_selected_cell_ids_and_names()
            if cell_ids:
                self._save_snapshot()
                self._add_faces_to_row(row_index, col, cell_ids)
            else:
                self.main_window.status_bar.SetStatusText(f"请先在3D视图中选择面，再点击[+]添加")

        self.Bind(wx.EVT_MENU, lambda e: on_menu_add_face(id_face), id=id_face)
        self.Bind(wx.EVT_MENU, lambda e: on_menu_add_face(id_bottom), id=id_bottom)

        self.PopupMenu(menu, self.ScreenToClient(screen_pos))
        menu.Destroy()
        self.Unbind(wx.EVT_MENU, id=id_face)
        self.Unbind(wx.EVT_MENU, id=id_bottom)

    def on_add_button_click(self, event):
        obj_name, cell_ids = self.get_selected_cell_ids_and_names()
        selected_label_name = self.main_window.selected_label_name

        if not cell_ids:
            return

        self._save_snapshot()
        self.update_label_result(selected_label_name, cell_ids, "add")
        self._assign_feature_instance(selected_label_name, cell_ids)
        self._add_row(selected_label_name, obj_name, cell_ids)
        self.main_window.status_bar.SetStatusText(f"已标注 {len(cell_ids)} 个面")
        self._mark_label_dirty()

    def _add_faces_to_row(self, row_index, col, cell_ids):
        """向指定行的指定列追加面"""
        label_name = self.labeled_list.GetItemText(row_index, self._COL_FEATURE)
        self._append_faces_to_row(row_index, cell_ids, col)
        self.update_label_result(label_name, cell_ids, "add")

        if col == self._COL_FACE_ID:
            face_id_str = self.labeled_list.GetItemText(row_index, self._COL_FACE_ID)
            orig_face_ids = self._parse_face_ids(face_id_str) if face_id_str else []
            inst_id = self._resolve_inst_id(orig_face_ids)
            for cid in cell_ids:
                self.main_window.face_to_instance[cid] = (label_name, inst_id)

        elif col == self._COL_BOTTOM:
            self._sync_bottom_to_face_ids(row_index, cell_ids)
            face_id_str = self.labeled_list.GetItemText(row_index, self._COL_FACE_ID)
            orig_face_ids = self._parse_face_ids(face_id_str) if face_id_str else []
            inst_id = self._resolve_inst_id(orig_face_ids)
            for cid in orig_face_ids:
                self.main_window.face_to_instance[cid] = (label_name, inst_id)
            for cid in cell_ids:
                self.main_window.face_to_instance[cid] = (label_name, inst_id)
            category_id = self.main_window.label_name_panel.get_feature_id(label_name)
            bottom_str = self.labeled_list.GetItemText(row_index, self._COL_BOTTOM)
            existing_bottom_ids = self._parse_face_ids(bottom_str) if bottom_str else []
            for cid in cell_ids:
                if cid not in self.main_window.bottom_faces:
                    self.main_window.face_to_instance[cid] = (label_name, inst_id)
                    self.main_window.bottom_faces[cid] = (category_id, existing_bottom_ids)

        label = "面ID" if col == self._COL_FACE_ID else "底面"
        self.main_window.status_bar.SetStatusText(f"[+]已向第{row_index + 1}行追加{len(cell_ids)}个{label}")
        self._mark_label_dirty()

    def on_batch_label_button_click(self, event):
        obj_name, cell_ids = self.get_selected_cell_ids_and_names()
        selected_label_name = self.main_window.selected_label_name

        if not cell_ids:
            self.main_window.status_bar.SetStatusText("请先选择面")
            return

        self._save_snapshot()
        self.update_label_result(selected_label_name, cell_ids, "add")
        # 批量标注：每个面各自分配独立的实例ID
        counter = self.main_window.feature_instance_counter
        for cid in cell_ids:
            inst_id = counter.get(selected_label_name, 0)
            self.main_window.face_to_instance[cid] = (selected_label_name, inst_id)
            counter[selected_label_name] = inst_id + 1

        name = obj_name[0] if obj_name else ""
        self.labeled_list.Freeze()
        try:
            for cid in cell_ids:
                idx = self.labeled_list.InsertItem(self.labeled_list.GetItemCount(), "")
                self.labeled_list.SetItem(idx, self._COL_FEATURE, selected_label_name)
                self.labeled_list.SetItem(idx, self._COL_OBJECT, name)
                self.labeled_list.SetItem(idx, self._COL_FACE_ID, str(cid))
                self.labeled_list.SetItem(idx, self._COL_BOTTOM, "")
        finally:
            self.labeled_list.Thaw()

        self.main_window.status_bar.SetStatusText(f"已批量标注 {len(cell_ids)} 个面")
        self._mark_label_dirty()

    def on_bottom_button_click(self, event):
        """标注底面：单个面匹配到已有标注行的底面列"""
        _, cell_ids = self.get_selected_cell_ids_and_names()

        if not cell_ids:
            self.main_window.status_bar.SetStatusText("请先在3D视图中选择面")
            return

        if len(cell_ids) > 1:
            self.main_window.status_bar.SetStatusText("标注底面只能选择一个面")
            return

        cid = cell_ids[0]
        self._save_snapshot()

        face_to_row = {}
        for i in range(self.labeled_list.GetItemCount()):
            face_id_str = self.labeled_list.GetItemText(i, self._COL_FACE_ID)
            for fid in self._parse_face_ids(face_id_str):
                if fid not in face_to_row:
                    face_to_row[fid] = i

        row = face_to_row.get(cid)
        if row is None:
            self.main_window.status_bar.SetStatusText("未找到匹配的标注行")
            return

        self._apply_bottom_face(row, cid)

        self.main_window.status_bar.SetStatusText(f"已标注底面: 面{cid}")
        self._mark_label_dirty()

    def _apply_bottom_face(self, row, cid):
        """将单个面标记为底面并更新关联数据"""
        self.labeled_list.Freeze()
        try:
            self._append_faces_to_row(row, [cid], self._COL_BOTTOM)
            label_name = self.labeled_list.GetItemText(row, self._COL_FEATURE)
            category_id = self.main_window.label_name_panel.get_feature_id(label_name)
            inst_id = self.main_window.face_to_instance.get(cid, (label_name, 0))[1]
            cylinder_face_ids = self._get_instance_face_ids(label_name, inst_id)
            if cid not in self.main_window.bottom_faces:
                self.main_window.bottom_faces[cid] = (category_id, cylinder_face_ids)
        finally:
            self.labeled_list.Thaw()

    def on_batch_bottom_button_click(self, event):
        """批量标注底面：将选中的面自动匹配到已有标注行的底面列"""
        _, cell_ids = self.get_selected_cell_ids_and_names()

        if not cell_ids:
            self.main_window.status_bar.SetStatusText("请先在3D视图中选择面")
            return

        self._save_snapshot()

        # 预构建 face_id -> row_index 查找表
        face_to_row = {}
        for i in range(self.labeled_list.GetItemCount()):
            face_id_str = self.labeled_list.GetItemText(i, self._COL_FACE_ID)
            for fid in self._parse_face_ids(face_id_str):
                if fid not in face_to_row:
                    face_to_row[fid] = i

        matched = 0
        for cid in cell_ids:
            row = face_to_row.get(cid)
            if row is None:
                continue
            self._apply_bottom_face(row, cid)
            matched += 1

        self.main_window.status_bar.SetStatusText(
            f"已匹配 {matched} 个底面（共选中 {len(cell_ids)} 个面）"
        )
        self._mark_label_dirty()

    def on_remove_button_click(self, event):
        selected_indices = []
        item = -1
        while True:
            item = self.labeled_list.GetNextItem(item, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if item == -1:
                break
            selected_indices.append(item)

        if not selected_indices:
            return

        self._save_snapshot()

        for idx in sorted(selected_indices, reverse=True):
            cell_id_str = self.labeled_list.GetItemText(idx, self._COL_FACE_ID)
            bottom_str = self.labeled_list.GetItemText(idx, self._COL_BOTTOM)
            all_cell_ids = self._parse_face_ids(cell_id_str)
            bottom_ids = self._parse_face_ids(bottom_str)
            label_name = self.labeled_list.GetItemText(idx, self._COL_FEATURE)
            self.labeled_list.DeleteItem(idx)
            all_ids = list(dict.fromkeys(all_cell_ids + bottom_ids))
            if all_ids:
                self.update_label_result(label_name, all_ids, "remove")
            for cid in all_ids:
                self.main_window.face_to_instance.pop(cid, None)
                self.main_window.bottom_faces.pop(cid, None)

        self._mark_label_dirty()

    def on_show_button_click(self, event):
        selected_obj_names = []
        selected_cell_ids = []
        item = -1
        while True:
            item = self.labeled_list.GetNextItem(item, wx.LIST_NEXT_ALL, wx.LIST_STATE_SELECTED)
            if item == -1:
                break
            obj_name = self.labeled_list.GetItemText(item, self._COL_OBJECT)
            face_id_str = self.labeled_list.GetItemText(item, self._COL_FACE_ID)
            bottom_str = self.labeled_list.GetItemText(item, self._COL_BOTTOM)
            if not face_id_str and not bottom_str:
                continue
            face_ids = self._parse_face_ids(face_id_str)
            selected_obj_names.extend([obj_name] * len(face_ids))
            selected_cell_ids.extend(face_ids)
            if bottom_str:
                bottom_ids = self._parse_face_ids(bottom_str)
                selected_obj_names.extend([obj_name] * len(bottom_ids))
                selected_cell_ids.extend(bottom_ids)

        if selected_obj_names and selected_cell_ids:
            combined = list(zip(selected_obj_names, selected_cell_ids))
            unique_combined = list(dict.fromkeys(combined))
            if unique_combined:
                unique_obj_names, unique_cell_ids = zip(*unique_combined)
                self.main_window.focus_selection(list(unique_obj_names), list(unique_cell_ids))

    def update_label_result(self, label_name: str, cell_ids: list, method: str = "add"):
        if label_name not in self.label_result:
            self.label_result[label_name] = set()
        if method == "add":
            self.label_result[label_name].update(cell_ids)
        else:
            self.label_result[label_name].difference_update(cell_ids)

    def _mark_label_dirty(self):
        if hasattr(self.main_window, 'label_tab'):
            self.main_window.label_tab.mark_dirty()
