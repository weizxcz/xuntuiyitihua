"""标注工作台窗口——管理零件列表、筛选、切换导入。"""

import collections
import json
import logging
import os
import shutil
import threading
from datetime import date

import wx

from config.user_config import load_user_config
from core.api_client import APIClient

_logger = logging.getLogger(__name__)

_PREFS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "workspace_prefs.json")

_LABEL_STATUS_KEYS = [
    "label_round_status",
    "label_chamfer_status",
    "label_countersink_hole_status",
    "label_counterbore_hole_status",
    "label_through_hole_status",
    "label_blind_hole_status",
]

_FEATURE_CHOICES = [
    "round", "chamfer", "countersink_hole",
    "counterbore_hole", "through_hole", "blind_hole",
]
_FEATURE_SHORT = {
    "round": "Rnd",
    "chamfer": "Chm",
    "countersink_hole": "Csink",
    "counterbore_hole": "Cbore",
    "through_hole": "Thr",
    "blind_hole": "Blind",
}


def _label_summary(part):
    """返回 6 个小方块对齐列头: Rnd  Chm  Csink  Cbore  Thr  Blind"""
    shorts = list(_FEATURE_SHORT.values())
    parts = []
    for i, k in enumerate(_LABEL_STATUS_KEYS):
        sym = "●" if part.get(k) == "completed" else "○"
        parts.append(sym.center(len(shorts[i]) - 1))
    return "      ".join(parts)


_PAGE_SIZE = 200
_MAX_CACHE_SIZE = 50


class WorkspaceWindow(wx.Frame):
    def __init__(self, main_window):
        super().__init__(main_window, title="标注工作台", size=(860, 560))
        self.main_window = main_window
        self.api = APIClient()
        self._all_parts = []
        self._displayed_parts = []
        self._current_part_id = None
        self._step_cache = collections.OrderedDict()
        self._downloading = False
        self._cancel_event = threading.Event()
        self._temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "temp")
        self._active_filters = {}
        self._has_more = False
        self._loading = False
        self._today_completed = self._load_local_stats()
        self._user_id = load_user_config().get("user_id", "")

        self.init_ui()

        self._load_filter_options()

        prefs = self._load_prefs()
        if prefs.get("industry"):
            self.combo_industry.SetValue(prefs["industry"])
        if prefs.get("product_type"):
            self.combo_product_type.SetValue(prefs["product_type"])
        self._apply_filters()
        self._load_stats()

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Centre()
        self.Show()

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # ---- 统计栏 ----
        stats_bar = wx.BoxSizer(wx.HORIZONTAL)
        self.stats_label = wx.StaticText(panel, label="今日完成: --")
        font_stats = self.stats_label.GetFont()
        font_stats.SetPointSize(font_stats.GetPointSize() + 2)
        self.stats_label.SetFont(font_stats)
        stats_bar.Add(self.stats_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        vbox.Add(stats_bar, 0, wx.EXPAND | wx.TOP, 6)

        # ---- 筛选栏 ----
        f = wx.FlexGridSizer(rows=3, cols=4, vgap=4, hgap=8)
        f.AddGrowableCol(1)
        f.AddGrowableCol(3)

        f.Add(wx.StaticText(panel, label="行业:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.combo_industry = wx.ComboBox(panel, value="全部", style=wx.CB_DROPDOWN)
        self.combo_industry.Bind(wx.EVT_COMBOBOX, self._on_industry_changed)
        f.Add(self.combo_industry, 1, wx.EXPAND)

        f.Add(wx.StaticText(panel, label="产品类型:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.combo_product_type = wx.ComboBox(panel, value="全部", style=wx.CB_DROPDOWN)
        f.Add(self.combo_product_type, 1, wx.EXPAND)

        f.Add(wx.StaticText(panel, label="几何特征:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.combo_feature = wx.ComboBox(panel, value="全部", style=wx.CB_DROPDOWN, choices=[
            "全部"] + _FEATURE_CHOICES)
        f.Add(self.combo_feature, 1, wx.EXPAND)

        f.Add(wx.StaticText(panel, label="搜索已加载:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.search_ctrl = wx.TextCtrl(panel)
        self.search_ctrl.Bind(wx.EVT_TEXT, self._on_search)
        f.Add(self.search_ctrl, 1, wx.EXPAND)

        self.btn_load = wx.Button(panel, label="加载")
        self.btn_load.Bind(wx.EVT_BUTTON, self._on_load_click)
        f.Add(self.btn_load, 0)
        self.btn_load_more = wx.Button(panel, label="加载更多")
        self.btn_load_more.Bind(wx.EVT_BUTTON, self._on_load_more)
        self.btn_load_more.Disable()
        f.Add(self.btn_load_more, 0)

        vbox.Add(f, 0, wx.EXPAND | wx.ALL, 8)

        # ---- 零件列表 ----
        self.list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        font = self.list_ctrl.GetFont()
        font.SetPointSize(font.GetPointSize() + 1)
        self.list_ctrl.SetFont(font)
        self.list_ctrl.AppendColumn("文件名", width=260)
        self.list_ctrl.AppendColumn("行业", width=80)
        self.list_ctrl.AppendColumn("产品类型", width=130)
        self.list_ctrl.AppendColumn("Rnd  Chm  Csink  Cbore  Thr  Blind", width=240)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_part_activated)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_part_selected)
        vbox.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        # ---- 底部按钮 + 状态 ----
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_import = wx.Button(panel, label="导入")
        self.btn_import.Bind(wx.EVT_BUTTON, lambda e: self._on_part_activated(e))
        bottom.Add(self.btn_import, 0, wx.RIGHT, 12)
        self.btn_cancel = wx.Button(panel, label="取消下载")
        self.btn_cancel.Bind(wx.EVT_BUTTON, self._on_cancel_download)
        self.btn_cancel.Hide()
        bottom.Add(self.btn_cancel, 0, wx.RIGHT, 12)
        self.status_text = wx.StaticText(panel, label="就绪")
        bottom.Add(self.status_text, 1, wx.ALIGN_CENTER_VERTICAL)
        vbox.Add(bottom, 0, wx.EXPAND | wx.ALL, 8)

        panel.SetSizer(vbox)

    def _set_error_status(self, msg):
        """设置状态栏错误文本，同时打印到终端。"""
        self.status_text.SetLabel(msg)
        print(f"[工作台错误] {msg}")

    def _on_load_click(self, event):
        self._save_prefs()
        self._apply_filters()

    def _apply_filters(self):
        industry = self.combo_industry.GetValue()
        product_type = self.combo_product_type.GetValue()
        feature = self.combo_feature.GetValue()

        self._active_filters = {}
        if industry and industry != "全部":
            self._active_filters["industry"] = industry
        if product_type and product_type != "全部":
            self._active_filters["product_type"] = product_type

        if feature and feature != "全部":
            self._active_filters[f"has_{feature}"] = "true"

        self._all_parts = []
        self._displayed_parts = []
        self._has_more = False
        self.btn_load_more.Disable()
        self._load_next_page()

    def _load_next_page(self):
        if self._loading:
            return
        self._loading = True
        self.status_text.SetLabel("加载零件列表...")
        self.btn_load_more.Disable()

        skip = len(self._all_parts)
        filters = dict(self._active_filters)

        def _work():
            try:
                parts = self.api.get_parts(
                    skip=skip, limit=_PAGE_SIZE,
                    **filters,
                )
                wx.CallAfter(self._on_page_loaded, parts)
            except Exception as e:
                wx.CallAfter(self._on_page_load_error, str(e))

        threading.Thread(target=_work, daemon=True).start()

    def _on_page_loaded(self, parts):
        self._loading = False
        old_count = len(self._all_parts)
        self._all_parts.extend(parts)
        self._has_more = len(parts) >= _PAGE_SIZE
        self.btn_load_more.Enable(self._has_more)

        keyword = self.search_ctrl.GetValue().strip().lower()
        if not keyword and old_count > 0:
            self._displayed_parts = list(self._all_parts)
            self._append_items(parts)
        else:
            self._apply_keyword_filter()
            self._populate_list(self._displayed_parts)
        self.status_text.SetLabel(f"已加载 {len(self._all_parts)} 条")

    def _on_load_more(self, event):
        self._load_next_page()

    def _on_page_load_error(self, err):
        self._loading = False
        self.btn_load_more.Enable(self._has_more)
        self._set_error_status(f"加载失败: {err}")

    def _populate_list(self, parts):
        self.list_ctrl.Freeze()
        try:
            self.list_ctrl.DeleteAllItems()
            for p in parts:
                self._insert_list_item(p)
        finally:
            self.list_ctrl.Thaw()

    def _on_search(self, event):
        self._apply_keyword_filter()
        self._populate_list(self._displayed_parts)

    def _load_filter_options(self):
        def _work():
            try:
                data = self.api.get_filter_options()
                wx.CallAfter(self._on_filter_options_loaded, data)
            except Exception as e:
                wx.CallAfter(self._set_error_status, f"加载筛选选项失败: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _on_filter_options_loaded(self, data):
        industries = data.get("industries", [])
        product_types = data.get("product_types", [])
        for combo, opts in [(self.combo_industry, industries), (self.combo_product_type, product_types)]:
            cur = combo.GetValue()
            combo.Clear()
            combo.Append("全部")
            combo.AppendItems(opts)
            combo.SetValue(cur if cur in opts or cur == "全部" else "全部")

    def _on_industry_changed(self, event):
        industry = self.combo_industry.GetValue()
        if industry == "全部":
            industry = None
        self.combo_product_type.SetValue("全部")

        def _work():
            try:
                data = self.api.get_filter_options(industry=industry)
                wx.CallAfter(self._update_product_type_options, data.get("product_types", []))
            except Exception as e:
                wx.CallAfter(self._set_error_status, f"加载产品类型失败: {e}")
        threading.Thread(target=_work, daemon=True).start()

    def _update_product_type_options(self, product_types):
        cur = self.combo_product_type.GetValue()
        self.combo_product_type.Clear()
        self.combo_product_type.Append("全部")
        self.combo_product_type.AppendItems(product_types)
        self.combo_product_type.SetValue(cur if cur in product_types or cur == "全部" else "全部")

    def _apply_keyword_filter(self):
        keyword = self.search_ctrl.GetValue().strip().lower()
        if not keyword:
            self._displayed_parts = list(self._all_parts)
        else:
            self._displayed_parts = [
                p for p in self._all_parts
                if keyword in p.get("name", "").lower()
            ]

    def _append_items(self, parts):
        self.list_ctrl.Freeze()
        try:
            for p in parts:
                self._insert_list_item(p)
        finally:
            self.list_ctrl.Thaw()

    def _insert_list_item(self, part):
        idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), part.get("name", ""))
        self.list_ctrl.SetItem(idx, 1, part.get("industry") or "")
        self.list_ctrl.SetItem(idx, 2, part.get("product_type") or "")
        self.list_ctrl.SetItem(idx, 3, _label_summary(part))
        if part.get("id") == self._current_part_id:
            self.list_ctrl.Select(idx)
            self.list_ctrl.Focus(idx)

    def _on_part_selected(self, event):
        sel = self.list_ctrl.GetFirstSelected()
        if 0 <= sel < len(self._displayed_parts):
            p = self._displayed_parts[sel]
            cur = " (当前)" if p.get("id") == self._current_part_id else ""
            self.status_text.SetLabel(f"{p.get('name', '')} (ID: {p['id']}){cur}")

    def _on_part_activated(self, event):
        sel = self.list_ctrl.GetFirstSelected()
        if sel < 0 or self._downloading:
            return
        self._load_part(self._displayed_parts[sel])

    def _load_part(self, part):
        part_id = part["id"]
        part_name = part.get("name", "unknown")

        if part_id in self._step_cache and os.path.exists(self._step_cache[part_id]):
            self._do_import(self._step_cache[part_id], part_id, part_name, part)
            return

        self._downloading = True
        self._cancel_event.clear()
        self.btn_cancel.Show()
        self.status_text.SetLabel(f"正在下载: {part_name} ...")

        cancel = self._cancel_event

        def _work():
            try:
                temp_dir = self._temp_dir
                os.makedirs(temp_dir, exist_ok=True)
                step_path = self.api.send_solid_file(part_id, temp_dir, cancel_event=cancel)
                if cancel.is_set():
                    return
                # LRU: 淘汰最早的缓存条目
                while len(self._step_cache) >= _MAX_CACHE_SIZE:
                    _, old_path = self._step_cache.popitem(last=False)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass
                self._step_cache[part_id] = step_path
                wx.CallAfter(self._do_import, step_path, part_id, part_name, part)
            except Exception as e:
                if not cancel.is_set():
                    wx.CallAfter(self._on_download_error, str(e))

        threading.Thread(target=_work, daemon=True).start()

    def _on_download_error(self, err):
        self._downloading = False
        self.btn_cancel.Hide()
        self._set_error_status(f"下载失败: {err}")
        _logger.error("下载失败: %s", err)

    def _on_cancel_download(self, event):
        if self._downloading:
            self._cancel_event.set()
            self._downloading = False
            self.btn_cancel.Hide()
            self.status_text.SetLabel("下载已取消")

    def _do_import(self, step_path, part_id, part_name, part):
        self._downloading = False
        self.btn_cancel.Hide()
        try:
            mw = self.main_window
            mw.import_step(step_path)
            mw.current_industry = part.get("industry", "")
            mw.current_part_id = part_id

            self._current_part_id = part_id
            self.status_text.SetLabel(f"已加载: {part_name} (ID: {part_id})")

            self.Close()
        except (AttributeError, TypeError) as e:
            self._set_error_status(f"导入出错（内部错误）: {e}")
            _logger.exception("导入编程错误")
        except Exception as e:
            self._set_error_status(f"导入失败: {e}")
            _logger.exception("导入失败")

    @staticmethod
    def _load_prefs():
        try:
            if os.path.exists(_PREFS_PATH):
                with open(_PREFS_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_prefs(self):
        prefs = self._load_prefs()
        prefs["industry"] = self.combo_industry.GetValue()
        prefs["product_type"] = self.combo_product_type.GetValue()
        self._save_prefs_raw(prefs)

    # ---- 统计 ----

    def _load_stats(self):
        def _work():
            try:
                data = self.api.get_stats(user=self._user_id)
                wx.CallAfter(self._on_stats_loaded, data)
            except Exception:
                wx.CallAfter(self._on_stats_loaded, None)

        threading.Thread(target=_work, daemon=True).start()

    def _on_stats_loaded(self, data):
        if data is None:
            self._refresh_stats_label(today=self._today_completed, total=None)
            return
        total_count = 0
        if isinstance(data, dict):
            total_count = data.get("total_count", data.get("count", 0))
        elif isinstance(data, (int, float)):
            total_count = int(data)
        self._refresh_stats_label(today=self._today_completed, total=total_count)

    def _refresh_stats_label(self, today, total=None):
        parts = [f"今日完成: {today}"]
        if total is not None:
            parts.append(f"总计: {total}")
        self.stats_label.SetLabel("  |  ".join(parts))

    def _load_local_stats(self):
        prefs = self._load_prefs()
        ts = prefs.get("today_stats", {})
        if ts.get("date") == str(date.today()):
            return ts.get("count", 0)
        return 0

    def _increment_local_stats(self):
        self._today_completed += 1
        prefs = self._load_prefs()
        prefs["today_stats"] = {"date": str(date.today()), "count": self._today_completed}
        self._save_prefs_raw(prefs)
        self._refresh_stats_label(today=self._today_completed, total=None)

    def _save_prefs_raw(self, prefs):
        try:
            os.makedirs(os.path.dirname(_PREFS_PATH), exist_ok=True)
            with open(_PREFS_PATH, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _on_close(self, event):
        self._save_prefs()
        # 清理临时文件
        try:
            if os.path.isdir(self._temp_dir):
                shutil.rmtree(self._temp_dir, ignore_errors=True)
        except Exception as e:
            _logger.warning("清理临时文件失败: %s", e)
        self._step_cache.clear()
        if hasattr(self.main_window, "workspace_window"):
            self.main_window.workspace_window = None
        self.Destroy()
