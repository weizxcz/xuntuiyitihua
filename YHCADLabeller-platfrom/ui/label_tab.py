import json
import os
from collections import defaultdict
import wx

from dialog.import_file import import_file_dialog
from function.on_new_document import new_document_function
from function.on_pre_label import select_pretrain_model, pre_label, batch_pre_label
from utils.file_finder import json_labels_path_to_step_path


_AUTO_SAVE_SUFFIX = "_auto_save.json"


class LabelTabPanel(wx.Panel):
    """标注选项卡面板"""
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.main_window = main_window
        self.last_file_dir = ""
        self.auto_save_path = ""
        self._dirty = False

        self.auto_save_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_auto_save_timer, self.auto_save_timer)

        self.init_ui()
        self.bind_events()

    def mark_dirty(self):
        self._dirty = True

    def init_ui(self):
        """初始化UI"""
        toolbar = wx.ToolBar(self, wx.ID_ANY,
                             style=wx.TB_HORIZONTAL | wx.NO_BORDER | wx.TB_FLAT | wx.TB_TEXT)
        bitmap_size = max(36, int(36 * self.main_window.scale_factor))
        toolbar.SetToolBitmapSize((bitmap_size, bitmap_size))
        toolbar_height = max(60, int(80 * self.main_window.scale_factor))
        toolbar.SetMinSize((-1, toolbar_height))
        toolbar.SetSize((-1, toolbar_height))

        self.button_import_json = wx.NewIdRef()
        self.button_import_stp = wx.NewIdRef()
        self.button_export_json = wx.NewIdRef()

        self.button_select_pretrain_model = wx.NewIdRef()
        self.button_pre_label = wx.NewIdRef()
        self.button_batch_pre_label = wx.NewIdRef()

        buttons = [
            ("导入标注stp", self.button_import_stp),
            ("导入标注json", self.button_import_json),
            ("导出标注json", self.button_export_json),
            (wx.ID_SEPARATOR, None),
            ("选择预标注模型", self.button_select_pretrain_model),
            ("预标注", self.button_pre_label),
            ("批量预标注", self.button_batch_pre_label),
        ]

        for btn in buttons:
            if btn[0] == wx.ID_SEPARATOR:
                toolbar.AddSeparator()
            else:
                icon = self.main_window.load_icon(btn[0])
                toolbar.AddTool(btn[1], btn[0], icon, shortHelp=btn[0])

        toolbar.Realize()

        # 设置标注选项卡的布局
        file_sizer = wx.BoxSizer(wx.VERTICAL)
        file_sizer.Add(toolbar, 0, wx.EXPAND)
        self.SetSizer(file_sizer)
        self.Layout()

    def bind_events(self):
        """绑定事件"""
        # 绑定按钮事件
        self.Bind(wx.EVT_TOOL, self.on_import_stp_click, id=self.button_import_stp)
        self.Bind(wx.EVT_TOOL, self.on_import_json_click, id=self.button_import_json)
        self.Bind(wx.EVT_TOOL, self.on_export_json_click, id=self.button_export_json)
        self.Bind(wx.EVT_TOOL, self.on_select_pretrain_model_click, id=self.button_select_pretrain_model)
        self.Bind(wx.EVT_TOOL, self.on_pre_label_click, id=self.button_pre_label)
        self.Bind(wx.EVT_TOOL, self.on_batch_pre_label_click, id=self.button_batch_pre_label)

    def on_import_stp_click(self, event):
        """导入待标注的STP文件，开始新的标注会话"""
        if not hasattr(self.main_window, 'doc'):
            self.main_window.status_bar.SetStatusText("没有doc对象")
            return
        try:
            filename_path = import_file_dialog(self.main_window.NCTI, self.main_window.doc)
            if filename_path:
                self.main_window.reset_label_env()
                self.main_window.fp_stp = filename_path
                self.start_new_auto_save()
                self.main_window.cad_view.update_doc(self.main_window)
                self.main_window.cad_view.update_view()
                self.main_window.status_bar.SetStatusText(f"导入待标注模型:{filename_path}")
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"导入待标注模型失败:{e}")

    def on_select_pretrain_model_click(self, event):
        select_pretrain_model(self.main_window)

    def on_pre_label_click(self, event):
        pre_label(self.main_window)

    def on_batch_pre_label_click(self, event):
        batch_pre_label(self.main_window)

    def on_export_json_click(self, event):
        dlg = wx.FileDialog(
            self,
            message="输入导出的文件",
            defaultDir=self.last_file_dir or os.path.dirname(self.main_window.fp_stp or ""),
            defaultFile=os.path.splitext(os.path.basename(self.main_window.fp_stp or ""))[0] + ".json",
            wildcard="模型文件 (*.json)|*.json",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        )

        filename_path = ""
        if dlg.ShowModal() == wx.ID_OK:
            filename_path = dlg.GetPath()
        dlg.Destroy()

        if filename_path:
            export_data = self.build_export_data()

            if export_data:
                with open(filename_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)

            if self.auto_save_path and self.auto_save_path.endswith(_AUTO_SAVE_SUFFIX):
                try:
                    os.remove(self.auto_save_path)
                except FileNotFoundError:
                    pass

            self.auto_save_path = filename_path
            self.last_file_dir = os.path.dirname(filename_path)
            self.start_auto_save_timer()

            self.main_window.status_bar.SetStatusText(f"标注已导出到: {filename_path}")

    def on_import_json_click(self, event):
        """导入标注JSON文件，同时自动查找并导入同名的STEP文件"""
        dlg = wx.FileDialog(
            self,
            message="选择标注JSON文件",
            defaultDir=self.last_file_dir,
            wildcard="JSON文件 (*.json)|*.json",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        )

        json_path = ""
        if dlg.ShowModal() == wx.ID_OK:
            json_path = dlg.GetPath()
        dlg.Destroy()

        if not json_path:
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            model_name = None
            label_data = {}

            if isinstance(data, list) and len(data) > 0:
                first_item = data[0]
                if isinstance(first_item, list) and len(first_item) == 2:
                    model_name = first_item[0]
                    label_data = first_item[1]
                elif isinstance(first_item, str):
                    model_name = first_item
                    label_data = data[1] if len(data) > 1 else {}
                elif isinstance(first_item, dict):
                    model_name = first_item.get('source_file', '')
                    label_data = first_item
            elif isinstance(data, dict):
                model_name = data.get('source_file', '')
                label_data = data

            feature_mapping = label_data.get('feature_mapping', {})
            seg = label_data.get('seg', {})
            inst = label_data.get('inst', [])
            bottom = label_data.get('bottom', {})

            step_path = json_labels_path_to_step_path(json_path)

            if model_name is None:
                self.main_window.status_bar.SetStatusText("JSON格式错误：无法解析模型名称，但继续导入模型")

            try:
                self.main_window.bind_view(new_document_function(
                    self.main_window.NCTI,
                    self.main_window.doc,
                    self.main_window.cad_view.GetHandle()
                ))

                obj_names = []
                if step_path:
                    try:
                        self.main_window.doc.RunCommand("cmd_ncti_import_file", str(step_path))
                        self.main_window.fp_stp = step_path
                        self.auto_save_path = ""
                        self.start_auto_save_timer()
                        self.main_window.cad_view.update_doc(self.main_window)
                        self.main_window.cad_view.update_view()
                        self.main_window.status_bar.SetStatusText(f"已导入模型: {step_path}")
                        obj_names = self.main_window.doc.AllNames()
                    except Exception as e:
                        self.main_window.status_bar.SetStatusText(f"导入STEP失败: {e}")
                else:
                    self.main_window.status_bar.SetStatusText("未找到STEP文件，请确认JSON位于labels/目录下")

                self._load_label_data(seg, inst, bottom, feature_mapping, obj_names)
            except Exception as e:
                self.main_window.status_bar.SetStatusText(f"导入失败: {e}")

        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"导入失败: {e}")

    def _load_label_data(self, seg, inst, bottom, feature_mapping, obj_names=None):
        """加载标注数据到UI面板"""
        if obj_names is None:
            obj_names = []
        obj_name = obj_names[0] if obj_names else ""

        # feature_mapping 是 {特征名: 编号}，反转为 {编号: 特征名} 供 seg 查表
        id_to_name = {v: k for k, v in (feature_mapping or {}).items()}

        main_window = self.main_window
        label_name_panel = main_window.label_name_panel
        labeled_features_panel = main_window.labeled_features_panel

        labeled_features_panel.labeled_list.DeleteAllItems()
        labeled_features_panel.label_result.clear()
        main_window.bottom_faces.clear()
        main_window.face_to_instance.clear()
        main_window.feature_instance_counter.clear()
        labeled_features_panel.clear_undo_history()

        # P1 修复：直接恢复 JSON 中的原始 feature_mapping 编号，不要用 get_feature_id 重排，
        # 否则跨文件导入时同一特征可能得到不同编号，训练端强校验编号一致会报错。
        for name, fid in (feature_mapping or {}).items():
            label_name_panel.feature_to_id[name] = fid
            if fid >= label_name_panel.next_id:
                label_name_panel.next_id = fid + 1
            if label_name_panel.name_list.FindString(name) == wx.NOT_FOUND:
                label_name_panel.name_list.Append(name)

        labeled_features_panel.labeled_list.Freeze()
        try:
            if inst:
                num_faces = len(inst)
                visited_faces = set()

                for i in range(num_faces):
                    if i in visited_faces:
                        continue
                    instance_faces = []
                    stack = [i]

                    while stack:
                        current = stack.pop()
                        if current in visited_faces:
                            continue
                        visited_faces.add(current)
                        instance_faces.append(current)
                        for k in range(num_faces):
                            if inst[current][k] == 1 and k not in visited_faces:
                                stack.append(k)

                    if not instance_faces:
                        continue

                    face_key = str(instance_faces[0])
                    if face_key not in seg:
                        continue
                    cat_id = int(seg[face_key])
                    feature_name = id_to_name.get(cat_id) if cat_id != 0 else None
                    if feature_name is None:
                        continue

                    bottom_list = [f for f in instance_faces if bottom.get(str(f)) == 1]
                    idx = labeled_features_panel.labeled_list.InsertItem(
                        labeled_features_panel.labeled_list.GetItemCount(), ""
                    )
                    labeled_features_panel.labeled_list.SetItem(idx, labeled_features_panel._COL_FEATURE, feature_name)
                    labeled_features_panel.labeled_list.SetItem(idx, labeled_features_panel._COL_OBJECT, obj_name)
                    labeled_features_panel.labeled_list.SetItem(
                        idx, labeled_features_panel._COL_FACE_ID,
                        ",".join(str(f) for f in sorted(instance_faces))
                    )
                    if bottom_list:
                        labeled_features_panel.labeled_list.SetItem(
                            idx, labeled_features_panel._COL_BOTTOM,
                            ",".join(str(f) for f in bottom_list)
                        )

                    if feature_name not in labeled_features_panel.label_result:
                        labeled_features_panel.label_result[feature_name] = set()
                    labeled_features_panel.label_result[feature_name].update(instance_faces)

                    labeled_features_panel._assign_feature_instance(feature_name, instance_faces)

            for face_key, is_bottom in bottom.items():
                if is_bottom != 1:
                    continue
                face_id = int(face_key)
                if face_id in main_window.face_to_instance:
                    continue
                cat_id = int(seg.get(face_key, 0))
                feature_name = id_to_name.get(cat_id) if cat_id != 0 else None
                if feature_name is None:
                    continue

                if feature_name not in labeled_features_panel.label_result:
                    labeled_features_panel.label_result[feature_name] = set()
                labeled_features_panel.label_result[feature_name].add(face_id)

                labeled_features_panel._assign_feature_instance(feature_name, [face_id])
                main_window.bottom_faces[face_id] = (cat_id, [])

        finally:
            labeled_features_panel.labeled_list.Thaw()

        total_labels = labeled_features_panel.labeled_list.GetItemCount()
        self.main_window.status_bar.SetStatusText(
            f"已加载 {total_labels} 条标注记录，{len(id_to_name)} 种特征类型"
        )

    def start_auto_save_timer(self, interval_ms=120000):
        if self.auto_save_timer.IsRunning():
            return
        self.auto_save_timer.Start(interval_ms)

    def start_new_auto_save(self):
        self.auto_save_path = ""
        self.start_auto_save_timer()

    def stop_auto_save_timer(self):
        if self.auto_save_timer.IsRunning():
            self.auto_save_timer.Stop()
            self.main_window.status_bar.SetStatusText("自动保存已关闭")

    def on_auto_save_timer(self, event):
        if not self._dirty:
            return
        if self.auto_save_path:
            self.auto_save_to_file(self.auto_save_path)
        elif self.main_window.fp_stp:
            base, _ = os.path.splitext(self.main_window.fp_stp)
            self.auto_save_path = base + _AUTO_SAVE_SUFFIX
            self.auto_save_to_file(self.auto_save_path)
        else:
            self.auto_save_timer.Stop()

    def auto_save_to_file(self, filename_path):
        export_data = self.build_export_data()
        if not export_data:
            return
        try:
            with open(filename_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            self.main_window.status_bar.SetStatusText(f"已自动保存: {filename_path}")
            self._dirty = False
        except Exception as e:
            self.main_window.status_bar.SetStatusText(f"自动保存失败: {e}")

    def build_export_data(self):
        """构建导出用的标注数据字典，返回 None 表示无数据"""
        main_window = self.main_window
        label_result = main_window.labeled_features_panel.label_result
        bottom_faces = main_window.bottom_faces
        face_to_instance = main_window.face_to_instance
        feature_mapping = main_window.label_name_panel.feature_mapping

        if not label_result and not bottom_faces:
            return None

        all_face_ids = set().union(*label_result.values(), bottom_faces.keys())
        num_faces = max(all_face_ids) + 1 if all_face_ids else 0

        if num_faces <= 0:
            return None

        seg = {str(i): 0 for i in range(num_faces)}
        inst = [[0] * num_faces for _ in range(num_faces)]

        instances = defaultdict(set)
        for fid, (fname, iid) in face_to_instance.items():
            instances[(fname, iid)].add(fid)
        for fid, (_, cyl_ids) in bottom_faces.items():
            entry = face_to_instance.get(fid)
            if entry is not None:
                fname, iid = entry
                for cyl_fid in cyl_ids:
                    instances[(fname, iid)].add(cyl_fid)

        instances = {iid: list(faces) for iid, faces in instances.items()}

        for (label_name, _), faces in instances.items():
            category_id = main_window.label_name_panel.get_feature_id(label_name)
            for fa in faces:
                seg[str(fa)] = category_id
            for i, fa in enumerate(faces):
                for fb in faces[i:]:
                    inst[fa][fb] = 1
                    inst[fb][fa] = 1

        for fid, value in bottom_faces.items():
            cat, cylinder_face_ids = value
            seg[str(fid)] = cat
            for other_fid in cylinder_face_ids:
                inst[fid][other_fid] = 1
                inst[other_fid][fid] = 1

        bottom = {str(i): 0 for i in range(num_faces)}
        for fid in bottom_faces:
            bottom[str(fid)] = 1

        return {
            "source_file": main_window.fp_stp or "",
            "feature_mapping": feature_mapping,
            "seg": seg,
            "inst": inst,
            "bottom": bottom
        }
