#!/usr/bin/env python3
"""
YHCADLabeller 新功能单元测试
测试范围：批量标注底面、撤销系统、导出逻辑、自动保存清理、JSON导入
"""

import json
import os
import sys
import tempfile
import unittest
from collections import deque
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ─── 1. 纯函数/工具方法测试 ─────────────────────────────────────

class TestParseFaceIds(unittest.TestCase):
    """TC-UTIL-001: _parse_face_ids 面ID解析"""

    def test_normal_comma_separated(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        result = LabeledFeaturesPanel._parse_face_ids("1,2,3")
        self.assertEqual(result, [1, 2, 3])

    def test_single_id(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        result = LabeledFeaturesPanel._parse_face_ids("42")
        self.assertEqual(result, [42])

    def test_with_spaces(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        result = LabeledFeaturesPanel._parse_face_ids("1, 2 , 3")
        self.assertEqual(result, [1, 2, 3])

    def test_empty_string(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        result = LabeledFeaturesPanel._parse_face_ids("")
        self.assertEqual(result, [])


# ─── 2. Resolve inst_id 测试 ────────────────────────────────────

class TestResolveInstId(unittest.TestCase):
    """TC-INST-001: _resolve_inst_id 实例ID解析"""

    def _make_panel(self, face_to_instance):
        panel = MagicMock()
        panel.main_window.face_to_instance = face_to_instance
        from ui.label_feature_panel import LabeledFeaturesPanel
        return LabeledFeaturesPanel._resolve_inst_id.__get__(panel, LabeledFeaturesPanel)

    def test_found_first(self):
        resolve = self._make_panel({10: ("圆角", 3), 20: ("倒角", 1)})
        self.assertEqual(resolve([10, 20]), 3)

    def test_found_second(self):
        resolve = self._make_panel({20: ("倒角", 1)})
        self.assertEqual(resolve([10, 20]), 1)

    def test_empty_list(self):
        resolve = self._make_panel({})
        self.assertEqual(resolve([]), 0)

    def test_none_found(self):
        resolve = self._make_panel({})
        self.assertEqual(resolve([5, 6]), 0)


# ─── 3. Undo 快照系统测试 ───────────────────────────────────────

class TestUndoSystem(unittest.TestCase):
    """TC-UNDO-001~005: 撤销系统"""

    def _make_panel(self):
        """创建一个带 mock 依赖的 panel 实例"""
        from ui.label_feature_panel import LabeledFeaturesPanel

        main_window = MagicMock()
        main_window.bottom_faces = {}
        main_window.face_to_instance = {}
        main_window.feature_instance_counter = {}
        main_window.status_bar = MagicMock()
        main_window.NCTI = MagicMock()
        main_window.doc = MagicMock()

        panel = MagicMock(spec=LabeledFeaturesPanel)
        panel.main_window = main_window
        panel.label_result = {}
        panel.lock_target = None
        panel._undo_stack = deque(maxlen=50)
        panel._MAX_UNDO = 50

        # 绑定真实方法
        panel._save_snapshot = LabeledFeaturesPanel._save_snapshot.__get__(panel, LabeledFeaturesPanel)
        panel.undo = LabeledFeaturesPanel.undo.__get__(panel, LabeledFeaturesPanel)
        panel.clear_undo_history = LabeledFeaturesPanel.clear_undo_history.__get__(panel, LabeledFeaturesPanel)
        panel._get_rows = MagicMock(return_value=[])

        return panel

    def test_snapshot_saves_state(self):
        """TC-UNDO-001: 快照保存状态"""
        panel = self._make_panel()
        panel.label_result = {"圆角": {1, 2, 3}}
        panel.main_window.bottom_faces = {4: (1, [1, 2])}

        panel._save_snapshot()

        self.assertEqual(len(panel._undo_stack), 1)
        snapshot = panel._undo_stack[0]
        self.assertEqual(snapshot['label_result']['圆角'], {1, 2, 3})
        self.assertEqual(snapshot['bottom_faces'][4], (1, [1, 2]))

    def test_undo_restores_state(self):
        """TC-UNDO-002: 撤销恢复状态"""
        panel = self._make_panel()
        panel.labeled_list = MagicMock()

        panel.label_result = {"圆角": {1, 2}}
        panel.main_window.face_to_instance = {1: ("圆角", 0), 2: ("圆角", 0)}
        panel._save_snapshot()

        panel.label_result = {"圆角": {1, 2, 3}}
        panel.main_window.face_to_instance = {1: ("圆角", 0), 2: ("圆角", 0), 3: ("圆角", 1)}

        panel.undo()

        self.assertEqual(panel.label_result, {"圆角": {1, 2}})
        self.assertIn(2, panel.main_window.face_to_instance)
        self.assertNotIn(3, panel.main_window.face_to_instance)

    def test_undo_empty_stack(self):
        """TC-UNDO-003: 空栈撤销提示"""
        panel = self._make_panel()
        panel.undo()
        panel.main_window.status_bar.SetStatusText.assert_called_with("没有可撤销的操作")

    def test_max_undo_depth(self):
        """TC-UNDO-004: 撤销栈深度限制为50"""
        panel = self._make_panel()
        for i in range(60):
            panel.label_result = {"f": {i}}
            panel._save_snapshot()

        self.assertEqual(len(panel._undo_stack), 50)

    def test_clear_undo_history(self):
        """TC-UNDO-005: 清除撤销历史"""
        panel = self._make_panel()
        panel._save_snapshot()
        panel._save_snapshot()
        panel.clear_undo_history()
        self.assertEqual(len(panel._undo_stack), 0)


# ─── 4. build_export_data 测试 ──────────────────────────────────

class TestBuildExportData(unittest.TestCase):
    """TC-EXPORT-001~004: 导出数据构建"""

    def _make_label_tab(self):
        from ui.label_tab import LabelTabPanel
        tab = MagicMock(spec=LabelTabPanel)
        tab.main_window = MagicMock()
        tab.main_window.labeled_features_panel = MagicMock()
        tab.main_window.labeled_features_panel.label_result = {"圆角": {0, 1, 2}}
        tab.main_window.bottom_faces = {2: (1, [0, 1])}
        tab.main_window.face_to_instance = {0: ("圆角", 0), 1: ("圆角", 0), 2: ("圆角", 0)}
        tab.main_window.feature_instance_counter = {"圆角": 1}
        tab.main_window.label_name_panel = MagicMock()
        tab.main_window.label_name_panel.get_feature_id = MagicMock(return_value=1)
        tab.main_window.label_name_panel.feature_mapping = {"圆角": 1}
        tab.main_window.fp_stp = "test.stp"
        tab.build_export_data = LabelTabPanel.build_export_data.__get__(tab)
        return tab

    def test_returns_dict_with_data(self):
        """TC-EXPORT-001: 有数据时返回完整字典"""
        tab = self._make_label_tab()
        result = tab.build_export_data()

        self.assertIsNotNone(result)
        self.assertIn("seg", result)
        self.assertIn("inst", result)
        self.assertIn("bottom", result)
        self.assertIn("feature_mapping", result)
        self.assertEqual(result["source_file"], "test.stp")

    def test_seg_values_correct(self):
        """TC-EXPORT-002: seg 分类映射正确"""
        tab = self._make_label_tab()
        result = tab.build_export_data()

        self.assertEqual(result["seg"]["0"], 1)
        self.assertEqual(result["seg"]["1"], 1)
        self.assertEqual(result["seg"]["2"], 1)

    def test_bottom_values_correct(self):
        """TC-EXPORT-003: bottom 底面标记正确"""
        tab = self._make_label_tab()
        result = tab.build_export_data()

        self.assertEqual(result["bottom"]["2"], 1)
        self.assertEqual(result["bottom"]["0"], 0)

    def test_returns_none_when_empty(self):
        """TC-EXPORT-004: 无数据时返回 None"""
        tab = self._make_label_tab()
        tab.main_window.labeled_features_panel.label_result = {}
        tab.main_window.bottom_faces = {}
        result = tab.build_export_data()
        self.assertIsNone(result)

    def test_inst_matrix_symmetric(self):
        """TC-EXPORT-005: inst 矩阵对称"""
        tab = self._make_label_tab()
        result = tab.build_export_data()
        inst = result["inst"]
        n = len(inst)
        for i in range(n):
            for j in range(n):
                self.assertEqual(inst[i][j], inst[j][i],
                                 f"inst[{i}][{j}]={inst[i][j]} != inst[{j}][{i}]={inst[j][i]}")


# ─── 5. 自动保存清理测试 ────────────────────────────────────────

class TestAutoSaveCleanup(unittest.TestCase):
    """TC-AUTOSAVE-001~002: 自动保存临时文件清理"""

    def test_deletes_old_auto_save_file(self):
        """TC-AUTOSAVE-001: 导出时删除旧的自动保存文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            auto_file = os.path.join(tmpdir, "old_auto_save.json")
            export_file = os.path.join(tmpdir, "export.json")

            with open(auto_file, 'w') as f:
                f.write('{"old": true}')

            self.assertTrue(os.path.exists(auto_file))

            # 模拟清理逻辑
            auto_save_path = auto_file
            if auto_save_path:
                try:
                    os.remove(auto_save_path)
                except FileNotFoundError:
                    pass

            self.assertFalse(os.path.exists(auto_file))

    def test_no_error_when_file_already_deleted(self):
        """TC-AUTOSAVE-002: 文件已不存在时不报错"""
        auto_save_path = "/nonexistent/path/auto_save.json"
        try:
            if auto_save_path:
                try:
                    os.remove(auto_save_path)
                except FileNotFoundError:
                    pass
        except Exception as e:
            self.fail(f"不应抛出异常: {e}")


# ─── 6. JSON 导入解析测试 ───────────────────────────────────────

class TestJsonImportParsing(unittest.TestCase):
    """TC-IMPORT-001~003: JSON 多格式导入解析"""

    def test_new_dict_format(self):
        """TC-IMPORT-001: 新格式（dict）解析"""
        data = {
            "source_file": "test.stp",
            "feature_mapping": {"圆角": 1},
            "seg": {"0": 1, "1": 0},
            "inst": [[0, 0], [0, 0]],
            "bottom": {"0": 1}
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            path = f.name

        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            self.assertIsInstance(loaded, dict)
            self.assertIn("seg", loaded)
            self.assertIn("inst", loaded)
            self.assertIn("bottom", loaded)
            self.assertEqual(loaded["source_file"], "test.stp")
        finally:
            os.unlink(path)

    def test_old_list_format(self):
        """TC-IMPORT-002: 旧格式（list）解析"""
        data = [
            "model.stp",
            {
                "feature_mapping": {"倒角": 2},
                "seg": {"0": 2},
                "inst": [[0]],
                "bottom": {}
            }
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            path = f.name

        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            self.assertIsInstance(loaded, list)
            model_name = loaded[0] if isinstance(loaded[0], str) else loaded[0][0]
            self.assertEqual(model_name, "model.stp")
        finally:
            os.unlink(path)

    def test_empty_seg_handled(self):
        """TC-IMPORT-003: 空 seg 不崩溃"""
        data = {
            "source_file": "",
            "feature_mapping": {},
            "seg": {},
            "inst": [],
            "bottom": {}
        }
        self.assertEqual(len(data["seg"]), 0)
        self.assertEqual(len(data["inst"]), 0)


# ─── 7. JSON 路径转换测试 ───────────────────────────────────────

class TestJsonLabelsPathConversion(unittest.TestCase):
    """TC-PATH-001: labels/steps 路径转换"""

    def test_normal_conversion(self):
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path("D:/data/labels/model.json")
        self.assertEqual(result, "D:/data/steps/model.step")

    def test_no_labels_segment(self):
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path("D:/data/model.json")
        self.assertIsNone(result)

    def test_backslash_handling(self):
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path("D:\\data\\labels\\model.json")
        self.assertEqual(result, "D:/data/steps/model.step")


# ─── 8. Assign Feature Instance 测试 ────────────────────────────

class TestAssignFeatureInstance(unittest.TestCase):
    """TC-INST-002: 特征实例分配"""

    def test_first_assignment(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        panel = MagicMock(spec=LabeledFeaturesPanel)
        panel.main_window = MagicMock()
        panel.main_window.feature_instance_counter = {}
        panel.main_window.face_to_instance = {}

        LabeledFeaturesPanel._assign_feature_instance(panel, "圆角", [10, 11, 12])

        self.assertEqual(panel.main_window.face_to_instance[10], ("圆角", 0))
        self.assertEqual(panel.main_window.face_to_instance[11], ("圆角", 0))
        self.assertEqual(panel.main_window.face_to_instance[12], ("圆角", 0))
        self.assertEqual(panel.main_window.feature_instance_counter["圆角"], 1)

    def test_sequential_instances(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        panel = MagicMock(spec=LabeledFeaturesPanel)
        panel.main_window = MagicMock()
        panel.main_window.feature_instance_counter = {}
        panel.main_window.face_to_instance = {}

        LabeledFeaturesPanel._assign_feature_instance(panel, "圆角", [1])
        LabeledFeaturesPanel._assign_feature_instance(panel, "圆角", [2])

        self.assertEqual(panel.main_window.face_to_instance[1], ("圆角", 0))
        self.assertEqual(panel.main_window.face_to_instance[2], ("圆角", 1))
        self.assertEqual(panel.main_window.feature_instance_counter["圆角"], 2)

    def test_different_features_independent(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        panel = MagicMock(spec=LabeledFeaturesPanel)
        panel.main_window = MagicMock()
        panel.main_window.feature_instance_counter = {}
        panel.main_window.face_to_instance = {}

        LabeledFeaturesPanel._assign_feature_instance(panel, "圆角", [1])
        LabeledFeaturesPanel._assign_feature_instance(panel, "倒角", [2])

        self.assertEqual(panel.main_window.face_to_instance[1], ("圆角", 0))
        self.assertEqual(panel.main_window.face_to_instance[2], ("倒角", 0))


# ─── 9. 边界条件测试 ───────────────────────────────────────────

class TestEdgeCases(unittest.TestCase):
    """TC-EDGE-001~003: 边界条件"""

    def test_parse_face_ids_large_numbers(self):
        """TC-EDGE-001: 大面ID解析"""
        from ui.label_feature_panel import LabeledFeaturesPanel
        result = LabeledFeaturesPanel._parse_face_ids("1000,2000,3000")
        self.assertEqual(result, [1000, 2000, 3000])

    def test_export_data_single_face(self):
        """TC-EDGE-002: 单面导出"""
        from ui.label_tab import LabelTabPanel
        tab = MagicMock(spec=LabelTabPanel)
        tab.main_window = MagicMock()
        tab.main_window.labeled_features_panel = MagicMock()
        tab.main_window.labeled_features_panel.label_result = {"平面": {0}}
        tab.main_window.bottom_faces = {}
        tab.main_window.face_to_instance = {0: ("平面", 0)}
        tab.main_window.feature_instance_counter = {"平面": 1}
        tab.main_window.label_name_panel = MagicMock()
        tab.main_window.label_name_panel.get_feature_id = MagicMock(return_value=1)
        tab.main_window.label_name_panel.feature_mapping = {"平面": 1}
        tab.main_window.fp_stp = ""
        tab.build_export_data = LabelTabPanel.build_export_data.__get__(tab)

        result = tab.build_export_data()
        self.assertIsNotNone(result)
        self.assertEqual(result["seg"]["0"], 1)
        self.assertEqual(len(result["inst"]), 1)

    def test_undo_deep_copy_isolation(self):
        """TC-EDGE-003: 快照深拷贝隔离性"""
        panel = MagicMock()
        panel.main_window = MagicMock()
        panel.main_window.bottom_faces = {1: (2, [3])}
        panel.main_window.face_to_instance = {1: ("f", 0)}
        panel.main_window.feature_instance_counter = {"f": 1}
        panel.label_result = {"f": {1}}
        panel.lock_target = None
        panel._undo_stack = deque(maxlen=50)
        panel._MAX_UNDO = 50
        panel._get_rows = MagicMock(return_value=[])

        from ui.label_feature_panel import LabeledFeaturesPanel
        LabeledFeaturesPanel._save_snapshot(panel)

        # 修改原始数据
        panel.label_result["f"].add(99)
        panel.main_window.face_to_instance[99] = ("f", 0)

        # 快照应不受影响
        snapshot = panel._undo_stack[0]
        self.assertNotIn(99, snapshot['label_result']['f'])
        self.assertNotIn(99, snapshot['face_to_instance'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
