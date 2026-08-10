"""导入标注工作台窗口——浏览已保存的标注JSON，选择导入。"""

import logging
import os
import shutil
import threading

import wx

from config.user_config import load_user_config
from core.api_client import APIClient

_logger = logging.getLogger(__name__)



class ImportLabelWindow(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="导入标注", size=(720, 480))
        self.main_window = parent
        self.api = APIClient()
        self._items = []
        self._temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp")
        self._user_id = load_user_config().get("user_id", "")

        self.init_ui()
        self._load_industries()
        self._apply_filters()

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Centre()
        self.Show()

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ---- 筛选栏 ----
        f = wx.FlexGridSizer(rows=2, cols=4, vgap=4, hgap=8)
        f.AddGrowableCol(1)
        f.AddGrowableCol(3)

        f.Add(wx.StaticText(panel, label="行业:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.combo_industry = wx.ComboBox(panel, value="全部", style=wx.CB_DROPDOWN)
        self.combo_industry.Bind(wx.EVT_COMBOBOX, self._on_industry_changed)
        f.Add(self.combo_industry, 1, wx.EXPAND)

        f.Add(wx.StaticText(panel, label="特征类型:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.combo_feature = wx.ComboBox(panel, value="全部", style=wx.CB_DROPDOWN, choices=[
            "全部", "round", "chamfer", "countersink_hole",
            "counterbore_hole", "through_hole", "blind_hole",
        ])
        f.Add(self.combo_feature, 1, wx.EXPAND)

        f.Add(wx.StaticText(panel, label="user:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.text_user = wx.TextCtrl(panel, value=self._user_id)
        f.Add(self.text_user, 1, wx.EXPAND)

        self.btn_load = wx.Button(panel, label="加载")
        self.btn_load.Bind(wx.EVT_BUTTON, lambda e: self._apply_filters())
        f.Add(self.btn_load, 0)

        vbox.Add(f, 0, wx.EXPAND | wx.ALL, 8)

        # ---- 列表 ----
        self.list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        font = self.list_ctrl.GetFont()
        font.SetPointSize(font.GetPointSize() + 1)
        self.list_ctrl.SetFont(font)
        self.list_ctrl.AppendColumn("文件名", width=260)
        self.list_ctrl.AppendColumn("行业", width=120)
        self.list_ctrl.AppendColumn("特征类型", width=120)
        self.list_ctrl.AppendColumn("user", width=120)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_item_activated)
        vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- 底部 ----
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_import = wx.Button(panel, label="导入")
        self.btn_import.Bind(wx.EVT_BUTTON, lambda e: self._on_item_activated(e))
        bottom.Add(self.btn_import, 0, wx.RIGHT, 12)
        self.status_text = wx.StaticText(panel, label="就绪")
        bottom.Add(self.status_text, 1, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(bottom, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(vbox)

    # ---- 筛选 ----

    def _apply_filters(self):
        self._items = []
        self._load_list()

    def _get_user(self):
        return self.text_user.GetValue().strip()

    def _load_list(self):
        self.status_text.SetLabel("加载列表...")

        user = self._get_user()
        if not user:
            self.status_text.SetLabel("请输入 user")
            return

        industry = self.combo_industry.GetValue()
        feature = self.combo_feature.GetValue()
        if industry == "全部":
            industry = None
        if feature == "全部":
            feature = None

        def _work():
            try:
                items = self.api.list_saved_json(
                    user=user, industry=industry, feature_type=feature,
                )
                wx.CallAfter(self._on_list_loaded, items)
            except Exception as e:
                wx.CallAfter(self._on_error, str(e))

        threading.Thread(target=_work, daemon=True).start()

    def _on_list_loaded(self, items):
        self._items = items
        self._populate_list()
        self.status_text.SetLabel(f"已加载 {len(self._items)} 条")

    def _on_error(self, err):
        self.status_text.SetLabel(f"加载失败: {err}")

    def _populate_list(self):
        self.list_ctrl.Freeze()
        try:
            self.list_ctrl.DeleteAllItems()
            for item in self._items:
                idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), item.get("name", ""))
                self.list_ctrl.SetItem(idx, 1, item.get("industry") or "")
                self.list_ctrl.SetItem(idx, 2, item.get("feature_type") or "")
                self.list_ctrl.SetItem(idx, 3, item.get("user") or "")
        finally:
            self.list_ctrl.Thaw()

    def _load_industries(self):
        """从后端 get_filter_options 接口加载行业列表"""

        def _work():
            try:
                data = self.api.get_filter_options()
                wx.CallAfter(self._on_industries_loaded, data.get("industries", []))
            except Exception:
                pass  # 加载失败不影响主流程

        threading.Thread(target=_work, daemon=True).start()

    def _on_industries_loaded(self, industries):
        cur = self.combo_industry.GetValue()
        self.combo_industry.Clear()
        self.combo_industry.Append("全部")
        for ind in industries:
            self.combo_industry.Append(ind)
        self.combo_industry.SetValue(cur if cur in industries or cur == "全部" else "全部")

    def _on_industry_changed(self, event):
        self._apply_filters()

    # ---- 导入 ----

    def _on_item_activated(self, event):
        sel = self.list_ctrl.GetFirstSelected()
        if sel < 0:
            return
        item = self._items[sel]
        self._do_import(item)

    def _do_import(self, item):
        name = item.get("name", "")
        feature_type = item.get("feature_type", "")
        industry = item.get("industry", "")
        user = item.get("user", "")

        self.status_text.SetLabel(f"正在导入: {name} ...")

        def _work():
            try:
                result = self.api.import_label_json(name, feature_type, industry, user)
                wx.CallAfter(self._on_import_success, result, name)
            except Exception as e:
                wx.CallAfter(self._on_error, f"导入失败: {e}")

        threading.Thread(target=_work, daemon=True).start()

    def _on_import_success(self, result, name):
        metadata = result["metadata"]
        file_bytes = result["file"]
        filename = result.get("filename", "imported.step")

        temp_dir = self._temp_dir
        os.makedirs(temp_dir, exist_ok=True)
        step_path = os.path.join(temp_dir, filename)
        with open(step_path, "wb") as f:
            f.write(file_bytes)

        try:
            mw = self.main_window
            mw.recreate_document()

            mw.import_step(step_path)
            if "part_id" in metadata:
                mw.current_part_id = metadata["part_id"]

            obj_names = mw.doc.AllNames()
            feature_mapping = metadata.get("feature_mapping", {})
            seg = metadata.get("seg", {})
            inst = metadata.get("inst", [])
            bottom = metadata.get("bottom", {})

            # 复用 label_tab 的加载方法（含左侧面板同步 + 右侧面板填充）
            label_tab = mw.label_tab
            label_tab._load_label_data(seg, inst, bottom, feature_mapping, obj_names)

            mw.status_bar.SetStatusText(f"已导入标注和模型: {filename}")
            self.status_text.SetLabel(f"已导入: {name}")
            self.Close()
        except Exception as e:
            self.status_text.SetLabel(f"导入失败: {e}")
            _logger.exception("导入失败: %s", filename)
            try:
                os.remove(step_path)
            except OSError:
                pass

    def _on_close(self, event):
        try:
            if os.path.isdir(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception as e:
            _logger.warning("清理临时文件失败: %s", e)
        if hasattr(self.main_window, 'import_label_window'):
            self.main_window.import_label_window = None
        self.Destroy()
