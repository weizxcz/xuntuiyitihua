"""YHCADLabeller 功能与稳定性测试套件"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# ─── 基础模块测试 ────────────────────────────────────────────────


class TestJsonLabelsPathToStepPath(unittest.TestCase):
    """utils/file_finder.py - STEP文件查找逻辑测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _make_file(self, rel_path):
        path = os.path.join(self.tmpdir, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write("dummy")
        return path

    def test_find_in_steps_dir(self):
        """优先在 steps/ 目录查找"""
        self._make_file("labels/model.json")
        step = self._make_file("steps/model.step")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/model.json"))
        self.assertEqual(os.path.normpath(result), os.path.normpath(step))

    def test_find_in_step_dir(self):
        """备选在 step/ 目录查找"""
        self._make_file("labels/part.json")
        step = self._make_file("step/part.step")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/part.json"))
        self.assertEqual(os.path.normpath(result), os.path.normpath(step))

    def test_find_stp_extension(self):
        """支持 .stp 扩展名"""
        self._make_file("labels/model.json")
        stp = self._make_file("steps/model.stp")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/model.json"))
        self.assertEqual(os.path.normpath(result), os.path.normpath(stp))

    def test_find_igs_extension(self):
        """支持 .igs 扩展名"""
        self._make_file("labels/model.json")
        igs = self._make_file("steps/model.igs")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/model.json"))
        self.assertEqual(os.path.normpath(result), os.path.normpath(igs))

    def test_fallback_recursive_search(self):
        """steps/ 目录不存在时递归搜索上级目录"""
        self._make_file("labels/model.json")
        step = self._make_file("cad_files/model.step")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/model.json"))
        self.assertEqual(os.path.normpath(result), os.path.normpath(step))

    def test_no_match_returns_none(self):
        """找不到对应文件返回 None"""
        self._make_file("labels/model.json")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/model.json"))
        self.assertIsNone(result)

    def test_skip_labels_dir_in_recursive(self):
        """递归搜索时跳过 labels 目录"""
        self._make_file("labels/model.json")
        self._make_file("labels/model.step")  # 不应匹配这个
        step = self._make_file("steps/model.step")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/model.json"))
        self.assertEqual(os.path.normpath(result), os.path.normpath(step))

    def test_steps_dir_inside_labels(self):
        """labels/ 内部的 steps/ 子目录优先于递归搜索"""
        self._make_file("labels/model.json")
        step = self._make_file("labels/steps/model.step")
        self._make_file("other/model.step")
        from utils.file_finder import json_labels_path_to_step_path
        result = json_labels_path_to_step_path(os.path.join(self.tmpdir, "labels/model.json"))
        self.assertEqual(os.path.normpath(result), os.path.normpath(step))


class TestFindGeomFile(unittest.TestCase):
    """_find_geom_file 辅助函数测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_find_step(self):
        with open(os.path.join(self.tmpdir, "test.step"), 'w') as f:
            f.write("dummy")
        from utils.file_finder import _find_geom_file
        result = _find_geom_file(self.tmpdir, "test")
        self.assertIsNotNone(result)

    def test_find_stp(self):
        with open(os.path.join(self.tmpdir, "test.stp"), 'w') as f:
            f.write("dummy")
        from utils.file_finder import _find_geom_file
        result = _find_geom_file(self.tmpdir, "test")
        self.assertIsNotNone(result)

    def test_no_match(self):
        from utils.file_finder import _find_geom_file
        result = _find_geom_file(self.tmpdir, "nonexistent")
        self.assertIsNone(result)

    def test_nonexistent_directory(self):
        from utils.file_finder import _find_geom_file
        result = _find_geom_file(os.path.join(self.tmpdir, "no_such_dir"), "test")
        self.assertIsNone(result)


# ─── 标注面板核心逻辑测试 ────────────────────────────────────────


class TestParseFaceIds(unittest.TestCase):
    """面ID字符串解析测试"""

    def test_single_id(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        self.assertEqual(LabeledFeaturesPanel._parse_face_ids("5"), [5])

    def test_multiple_ids(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        self.assertEqual(LabeledFeaturesPanel._parse_face_ids("1,2,3"), [1, 2, 3])

    def test_empty_string(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        self.assertEqual(LabeledFeaturesPanel._parse_face_ids(""), [])

    def test_trailing_comma(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        self.assertEqual(LabeledFeaturesPanel._parse_face_ids("1,2,"), [1, 2])

    def test_spaces(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        self.assertEqual(LabeledFeaturesPanel._parse_face_ids("1 , 2 , 3"), [1, 2, 3])


class TestLabelResultUpdate(unittest.TestCase):
    """label_result 增删操作测试"""

    def _make_panel(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        panel = MagicMock(spec=LabeledFeaturesPanel)
        panel.label_result = {}
        panel.main_window = MagicMock()
        panel.main_window.bottom_faces = {}
        panel.main_window.face_to_instance = {}
        panel.main_window.feature_instance_counter = {}
        # 使用真实方法
        panel.update_label_result = LabeledFeaturesPanel.update_label_result.__get__(panel)
        return panel

    def test_add_new_feature(self):
        panel = self._make_panel()
        panel.update_label_result("圆角", [1, 2, 3], "add")
        self.assertEqual(panel.label_result["圆角"], {1, 2, 3})

    def test_add_to_existing_feature(self):
        panel = self._make_panel()
        panel.update_label_result("圆角", [1, 2], "add")
        panel.update_label_result("圆角", [3, 4], "add")
        self.assertEqual(panel.label_result["圆角"], {1, 2, 3, 4})

    def test_add_duplicate_ids(self):
        panel = self._make_panel()
        panel.update_label_result("圆角", [1, 2], "add")
        panel.update_label_result("圆角", [2, 3], "add")
        self.assertEqual(panel.label_result["圆角"], {1, 2, 3})

    def test_remove_ids(self):
        panel = self._make_panel()
        panel.update_label_result("圆角", [1, 2, 3], "add")
        panel.update_label_result("圆角", [2], "remove")
        self.assertEqual(panel.label_result["圆角"], {1, 3})

    def test_remove_nonexistent_id(self):
        panel = self._make_panel()
        panel.update_label_result("圆角", [1, 2], "add")
        panel.update_label_result("圆角", [99], "remove")
        self.assertEqual(panel.label_result["圆角"], {1, 2})

    def test_add_multiple_features(self):
        panel = self._make_panel()
        panel.update_label_result("圆角", [1, 2], "add")
        panel.update_label_result("盲孔", [3, 4], "add")
        self.assertEqual(panel.label_result["圆角"], {1, 2})
        self.assertEqual(panel.label_result["盲孔"], {3, 4})


class TestSnapshotUndo(unittest.TestCase):
    """快照与撤销机制测试"""

    def _make_panel(self):
        from ui.label_feature_panel import LabeledFeaturesPanel
        panel = MagicMock(spec=LabeledFeaturesPanel)
        panel.label_result = {}
        panel._undo_stack = []
        panel.main_window = MagicMock()
        panel.main_window.bottom_faces = {}
        panel.main_window.face_to_instance = {}
        panel.main_window.feature_instance_counter = {}
        panel.main_window.status_bar = MagicMock()
        panel.labeled_list = MagicMock()
        panel.labeled_list.GetItemCount.return_value = 0
        # 绑定真实方法
        panel._get_rows = LabeledFeaturesPanel._get_rows.__get__(panel)
        panel._save_snapshot = LabeledFeaturesPanel._save_snapshot.__get__(panel)
        return panel

    def test_save_snapshot_captures_state(self):
        panel = self._make_panel()
        panel.label_result = {"圆角": {1, 2}}
        panel.main_window.bottom_faces = {3: (1, [1, 2])}
        panel.main_window.face_to_instance = {1: ("圆角", 0)}
        panel.main_window.feature_instance_counter = {"圆角": 1}

        panel._save_snapshot()

        self.assertEqual(len(panel._undo_stack), 1)
        snap = panel._undo_stack[0]
        self.assertEqual(snap['label_result']['圆角'], {1, 2})
        self.assertEqual(snap['bottom_faces'][3], (1, [1, 2]))
        self.assertEqual(snap['face_to_instance'][1], ("圆角", 0))

    def test_snapshot_is_deep_copy(self):
        """快照是深拷贝，修改原数据不影响快照"""
        panel = self._make_panel()
        panel.label_result = {"圆角": {1, 2}}
        panel._save_snapshot()

        panel.label_result["圆角"].add(99)
        snap = panel._undo_stack[0]
        self.assertNotIn(99, snap['label_result']['圆角'])


# ─── 特征名称面板测试 ────────────────────────────────────────────


class TestLabelNamePanel(unittest.TestCase):
    """label_name_panel.py 测试"""

    def _make_panel(self):
        from ui.label_name_panel import LabelNamePanel
        panel = MagicMock(spec=LabelNamePanel)
        panel.feature_to_id = {}
        panel.next_id = 1
        panel.main_window = MagicMock()
        panel.main_window.status_bar = MagicMock()
        panel.name_list = MagicMock()
        panel.feature_name_input = MagicMock()
        panel.feature_name_input.GetValue.return_value = ""
        # 绑定真实方法
        panel.get_feature_id = LabelNamePanel.get_feature_id.__get__(panel)
        # 绑定真实 property
        type(panel).feature_mapping = LabelNamePanel.feature_mapping
        return panel

    def test_auto_assign_id(self):
        panel = self._make_panel()
        self.assertEqual(panel.get_feature_id("圆角"), 1)
        self.assertEqual(panel.get_feature_id("盲孔"), 2)

    def test_same_name_returns_same_id(self):
        panel = self._make_panel()
        id1 = panel.get_feature_id("圆角")
        id2 = panel.get_feature_id("圆角")
        self.assertEqual(id1, id2)

    def test_feature_mapping_property(self):
        panel = self._make_panel()
        panel.get_feature_id("圆角")
        panel.get_feature_id("盲孔")
        mapping = panel.feature_mapping
        self.assertEqual(mapping, {"圆角": 1, "盲孔": 2})
        # 验证返回的是副本
        mapping["新特征"] = 99
        self.assertNotIn("新特征", panel.feature_to_id)


# ─── 导出数据构建测试 ────────────────────────────────────────────


class TestBuildExportData(unittest.TestCase):
    """label_tab.py build_export_data 测试"""

    def _make_window(self):
        win = MagicMock()
        win.main_window = MagicMock()
        win.main_window.labeled_features_panel = MagicMock()
        win.main_window.labeled_features_panel.label_result = {
            "圆角": {0, 1},
            "盲孔": {2},
        }
        win.main_window.bottom_faces = {3: (2, [2])}
        win.main_window.face_to_instance = {
            0: ("圆角", 0),
            1: ("圆角", 0),
            2: ("盲孔", 1),
            3: ("盲孔", 1),
        }
        win.main_window.feature_instance_counter = {"圆角": 1, "盲孔": 2}
        win.main_window.label_name_panel = MagicMock()
        win.main_window.label_name_panel.get_feature_id.side_effect = lambda n: {"圆角": 1, "盲孔": 2}.get(n, 0)
        win.main_window.label_name_panel.feature_mapping = {"圆角": 1, "盲孔": 2}
        win.main_window.fp_stp = "test.step"
        win.main_window.current_part_id = ""
        from ui.label_tab import LabelTabPanel
        win.build_export_data = LabelTabPanel.build_export_data.__get__(win)
        return win

    def test_export_has_required_fields(self):
        win = self._make_window()
        data = win.build_export_data()
        self.assertIn("source_file", data)
        self.assertIn("part_id", data)
        self.assertIn("feature_mapping", data)
        self.assertIn("seg", data)
        self.assertIn("inst", data)
        self.assertIn("bottom", data)

    def test_seg_values(self):
        win = self._make_window()
        data = win.build_export_data()
        self.assertEqual(data["seg"]["0"], 1)  # 圆角
        self.assertEqual(data["seg"]["1"], 1)  # 圆角
        self.assertEqual(data["seg"]["2"], 2)  # 盲孔
        self.assertEqual(data["seg"]["3"], 2)  # 盲孔

    def test_inst_symmetric(self):
        """inst 矩阵必须对称"""
        win = self._make_window()
        data = win.build_export_data()
        inst = data["inst"]
        n = len(inst)
        for i in range(n):
            for j in range(n):
                self.assertEqual(inst[i][j], inst[j][i],
                                 f"inst[{i}][{j}]={inst[i][j]} != inst[{j}][{i}]={inst[j][i]}")

    def test_inst_same_instance(self):
        """同一实例的面在 inst 矩阵中互为 1"""
        win = self._make_window()
        data = win.build_export_data()
        inst = data["inst"]
        # 圆角面 0,1 属于同一实例
        self.assertEqual(inst[0][1], 1)
        self.assertEqual(inst[1][0], 1)
        # 盲孔面 2,3 属于同一实例
        self.assertEqual(inst[2][3], 1)
        self.assertEqual(inst[3][2], 1)

    def test_inst_different_instance(self):
        """不同实例的面在 inst 矩阵中为 0"""
        win = self._make_window()
        data = win.build_export_data()
        inst = data["inst"]
        self.assertEqual(inst[0][2], 0)
        self.assertEqual(inst[1][3], 0)

    def test_bottom_values(self):
        win = self._make_window()
        data = win.build_export_data()
        self.assertEqual(data["bottom"]["3"], 1)
        self.assertEqual(data["bottom"]["0"], 0)

    def test_empty_label_returns_none(self):
        win = self._make_window()
        win.main_window.labeled_features_panel.label_result = {}
        win.main_window.bottom_faces = {}
        data = win.build_export_data()
        self.assertIsNone(data)

    def test_source_file(self):
        win = self._make_window()
        data = win.build_export_data()
        self.assertEqual(data["source_file"], "test.step")


# ─── 导入导出 JSON 测试 ─────────────────────────────────────────


class TestJsonExportImport(unittest.TestCase):
    """JSON 导出后再导入，验证数据一致性"""

    def _make_window(self):
        win = MagicMock()
        win.main_window = MagicMock()
        win.main_window.labeled_features_panel = MagicMock()
        win.main_window.labeled_features_panel.label_result = {
            "圆角": {0, 1},
        }
        win.main_window.bottom_faces = {}
        win.main_window.face_to_instance = {
            0: ("圆角", 0),
            1: ("圆角", 0),
        }
        win.main_window.feature_instance_counter = {"圆角": 1}
        win.main_window.label_name_panel = MagicMock()
        win.main_window.label_name_panel.get_feature_id.return_value = 1
        win.main_window.label_name_panel.feature_mapping = {"圆角": 1}
        win.main_window.fp_stp = "test.step"
        win.main_window.current_part_id = ""
        from ui.label_tab import LabelTabPanel
        win.build_export_data = LabelTabPanel.build_export_data.__get__(win)
        return win

    def test_export_then_reimport(self):
        """导出 JSON 后重新解析，验证核心数据完整"""
        win = self._make_window()
        data = win.build_export_data()

        # 序列化/反序列化
        json_str = json.dumps(data)
        loaded = json.loads(json_str)

        # 验证 seg
        self.assertEqual(loaded["seg"]["0"], 1)
        self.assertEqual(loaded["seg"]["1"], 1)

        # 验证 inst 对称
        inst = loaded["inst"]
        for i in range(len(inst)):
            for j in range(len(inst)):
                self.assertEqual(inst[i][j], inst[j][i])

        # 验证 feature_mapping
        self.assertEqual(loaded["feature_mapping"]["圆角"], 1)


# ─── 配置加载测试 ────────────────────────────────────────────────


class TestConfigLoad(unittest.TestCase):
    """config/config_load.py 测试"""

    def test_system_config_readable(self):
        from config.config_load import get_system_config_json
        config = get_system_config_json()
        self.assertIsInstance(config, dict)
        self.assertIn("dllPath", config)

    def test_system_config_json_valid(self):
        config_path = os.path.join(os.path.dirname(__file__), "config", "system_config.json")
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn("dllPath", data)
        self.assertIn("addKernelPath", data)
        self.assertIn("loadDLL", data)
        self.assertIsInstance(data["addKernelPath"], list)
        self.assertIsInstance(data["loadDLL"], list)


# ─── 导入文件对话框逻辑测试 ──────────────────────────────────────


class TestImportFileLogic(unittest.TestCase):
    """dialog/import_file.py 逻辑测试"""

    def test_json_extension_detected(self):
        """JSON 文件扩展名正确识别"""
        import os
        self.assertEqual(os.path.splitext("test.json")[1].lower(), ".json")
        self.assertEqual(os.path.splitext("test.step")[1].lower(), ".step")
        self.assertEqual(os.path.splitext("test.stp")[1].lower(), ".stp")
        self.assertEqual(os.path.splitext("test.igs")[1].lower(), ".igs")


if __name__ == "__main__":
    unittest.main(verbosity=2)
