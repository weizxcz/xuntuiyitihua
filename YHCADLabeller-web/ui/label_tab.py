import json
import logging
import os
import threading
from collections import defaultdict
import wx

from core.api_client import APIClient
from config.user_config import load_user_config, save_user_config
from workspace.import_label_window import ImportLabelWindow
from dialog.label_params_dialog import LabelParamsDialog

_logger = logging.getLogger(__name__)


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

        self.api = APIClient()
        self._temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp")

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
        self.button_export_json = wx.NewIdRef()
        self.button_settings = wx.NewIdRef()

        buttons = [
            ("导入标注json", self.button_import_json),
            ("导出标注json", self.button_export_json),
            (wx.ID_SEPARATOR, None),
            ("设置", self.button_settings),
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
        self.Bind(wx.EVT_TOOL, self.on_import_json_click, id=self.button_import_json)
        self.Bind(wx.EVT_TOOL, self.on_export_json_click, id=self.button_export_json)
        self.Bind(wx.EVT_TOOL, self.on_settings_click, id=self.button_settings)

    def on_settings_click(self, event):
        config = load_user_config()
        dlg = wx.TextEntryDialog(self, "请输入用户ID:", "设置", value=config.get("user_id", ""))
        if dlg.ShowModal() == wx.ID_OK:
            user_id = dlg.GetValue().strip()
            if user_id:
                save_user_config({"user_id": user_id})
                self.main_window.status_bar.SetStatusText(f"用户ID已保存: {user_id}")
        dlg.Destroy()

    def _get_defaults(self):
        defaults = {}
        if self.main_window.fp_stp:
            defaults["name"] = os.path.splitext(os.path.basename(self.main_window.fp_stp))[0]
        defaults["industry"] = getattr(self.main_window, "current_industry", "")
        config = load_user_config()
        defaults["user"] = config.get("user_id", "")
        return defaults

    def _collect_params(self, title):
        """弹出参数对话框并验证，返回 params 或 None"""
        defaults = self._get_defaults()
        dlg = LabelParamsDialog(self, title=title, defaults=defaults)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return None
        params = dlg.get_params()
        dlg.Destroy()
        if not all([params["name"], params["feature_type"], params["user"]]):
            self.main_window.status_bar.SetStatusText("请填写完整参数（名称、特征类型、用户）")
            return None
        return params

    def on_export_json_click(self, event):
        export_data = self.build_export_data()
        if not export_data:
            self.main_window.status_bar.SetStatusText("没有可导出的标注数据")
            return

        # 从已标注特征中获取实际有标注数据的特征名
        label_result = self.main_window.labeled_features_panel.label_result
        feature_names = [name for name, faces in label_result.items() if faces]
        if not feature_names:
            self.main_window.status_bar.SetStatusText("没有已标注的特征")
            return

        # 弹出参数对话框（隐藏特征类型下拉框，自动填充）
        defaults = self._get_defaults()
        defaults["feature_type"] = feature_names[0] if len(feature_names) == 1 else "mix"
        dlg = LabelParamsDialog(self, title="导出标注参数", defaults=defaults)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        params = dlg.get_params()
        dlg.Destroy()
        if not all([params["name"], params["user"]]):
            self.main_window.status_bar.SetStatusText("请填写完整参数（名称、用户）")
            return

        self.main_window.status_bar.SetStatusText("正在上传标注数据到服务器...")

        def _work():
            try:
                # 每个特征分别调用 API，保存 JSON 并更新标注状态
                last_result = None
                part_id = self.main_window.current_part_id
                user = params["user"]
                for ft in feature_names:
                    last_result = self.api.save_label_json(
                        params["name"], ft,
                        params["industry"], params["user"], export_data
                    )
                    if part_id:
                        self.api.update_feature_label(
                            part_id, ft, "completed", modified_by=user
                        )
                wx.CallAfter(self._on_export_success, last_result)
            except Exception as e:
                wx.CallAfter(self._on_api_error, f"上传失败: {e}")

        threading.Thread(target=_work, daemon=True).start()

    def _on_export_success(self, result):
        path = result.get("data", {}).get("path", "")
        self.main_window.status_bar.SetStatusText(f"标注已上传到服务器: {path}")
        self.start_auto_save_timer()
        ws = getattr(self.main_window, 'workspace_window', None)
        if ws is not None:
            try:
                ws._increment_local_stats()
            except RuntimeError:
                pass

    def _on_api_error(self, msg):
        self.main_window.status_bar.SetStatusText(msg)

    def on_import_json_click(self, event):
        """打开导入标注工作台"""
        if hasattr(self.main_window, 'import_label_window') and self.main_window.import_label_window:
            self.main_window.import_label_window.Raise()
            return
        self.main_window.import_label_window = ImportLabelWindow(self.main_window)

    def _load_label_data(self, seg, inst, bottom, feature_mapping, obj_names=None):
        """加载标注数据到UI面板"""
        if obj_names is None:
            obj_names = []
        obj_name = obj_names[0] if obj_names else ""

        main_window = self.main_window
        label_name_panel = main_window.label_name_panel
        labeled_features_panel = main_window.labeled_features_panel

        labeled_features_panel.labeled_list.DeleteAllItems()
        labeled_features_panel.label_result.clear()
        main_window.bottom_faces.clear()
        main_window.face_to_instance.clear()
        main_window.feature_instance_counter.clear()
        labeled_features_panel.clear_undo_history()

        id_to_name = {v: k for k, v in feature_mapping.items()} if feature_mapping else {}

        for name in id_to_name.values():
            if name not in label_name_panel.feature_to_id:
                label_name_panel.get_feature_id(name)
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
            "part_id": str(main_window.current_part_id),
            "source_file": main_window.fp_stp or "",
            "feature_mapping": feature_mapping,
            "seg": seg,
            "inst": inst,
            "bottom": bottom
        }
