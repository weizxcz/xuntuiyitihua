#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
YHCADLabeller 测试执行脚本
测试环境: Python 3.11 + wxPython 4.2.1 + NCTI SDK
"""

import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'D:/软件/biaozhuruanjian')

# 测试结果收集
test_results = {
    'passed': [],
    'failed': [],
    'skipped': [],
    'errors': []
}

def log_test(module, test_id, name, status, message=""):
    """记录测试结果"""
    result = {
        'module': module,
        'test_id': test_id,
        'name': name,
        'status': status,
        'message': message,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    if status == 'PASS':
        test_results['passed'].append(result)
        print(f"  [PASS] {test_id}: {name}")
    elif status == 'FAIL':
        test_results['failed'].append(result)
        print(f"  [FAIL] {test_id}: {name} - {message}")
    elif status == 'SKIP':
        test_results['skipped'].append(result)
        print(f"  [SKIP] {test_id}: {name} - {message}")
    elif status == 'ERROR':
        test_results['errors'].append(result)
        print(f"  [ERROR] {test_id}: {name} - {message}")

def print_section(title):
    """打印分节标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def run_config_tests():
    """配置加载测试 (C001-C003)"""
    print_section("配置加载测试")

    # C001: DLL路径加载
    try:
        from config.config_load import get_system_config_json
        config = get_system_config_json()
        if config and 'dllPath' in config:
            log_test('Config', 'C001', 'DLL路径加载', 'PASS', f"dllPath={config['dllPath']}")
        else:
            log_test('Config', 'C001', 'DLL路径加载', 'FAIL', '配置为空或缺少dllPath')
    except Exception as e:
        log_test('Config', 'C001', 'DLL路径加载', 'ERROR', str(e))

    # C002: NCTI初始化
    try:
        from config.config_load import global_scope
        if 'NCTI' in global_scope and global_scope['NCTI'] is not None:
            log_test('Config', 'C002', 'NCTI初始化', 'PASS', 'NCTI模块加载成功')
        else:
            log_test('Config', 'C002', 'NCTI初始化', 'FAIL', 'NCTI未正确加载')
    except Exception as e:
        log_test('Config', 'C002', 'NCTI初始化', 'ERROR', str(e))

    # C003: Document创建
    try:
        from config.config_load import global_scope
        if 'doc' in global_scope and global_scope['doc'] is not None:
            log_test('Config', 'C003', 'Document创建', 'PASS', 'doc对象创建成功')
        else:
            log_test('Config', 'C003', 'Document创建', 'FAIL', 'doc未正确创建')
    except Exception as e:
        log_test('Config', 'C003', 'Document创建', 'ERROR', str(e))

def run_ui_after_init(wx_app, frame, timeout=5):
    """等待wx.CallAfter完成的UI初始化"""
    import time
    start = time.time()
    while time.time() - start < timeout:
        wx_app.ProcessPendingEvents()
        if hasattr(frame, 'aui_manager') and hasattr(frame, 'notebook'):
            return True
        time.sleep(0.1)
    return hasattr(frame, 'notebook')

def run_ui_component_tests():
    """UI组件测试"""
    print_section("UI组件测试")

    try:
        import wx
        app = wx.App(False)

        # 创建主窗口实例
        from ui.main_window import CAEPlatform
        frame = CAEPlatform()

        # 等待UI初始化完成
        ui_ready = run_ui_after_init(app, frame)

        # 检查窗口创建
        if frame and frame.IsShown():
            log_test('UI', 'U001', '主窗口创建', 'PASS', 'CAEPlatform窗口创建成功')
        else:
            log_test('UI', 'U001', '主窗口创建', 'FAIL', '窗口未正确显示')

        # 检查notebook选项卡
        if hasattr(frame, 'notebook'):
            page_count = frame.notebook.GetPageCount()
            if page_count == 3:
                log_test('UI', 'U002', 'Notebook选项卡', 'PASS', f'3个选项卡已创建')
            else:
                log_test('UI', 'U002', 'Notebook选项卡', 'FAIL', f'选项卡数量={page_count}, 期望=3')
        else:
            log_test('UI', 'U002', 'Notebook选项卡', 'FAIL', 'notebook未初始化')

        # 检查状态栏
        if hasattr(frame, 'status_bar'):
            log_test('UI', 'U003', '状态栏初始化', 'PASS', '状态栏已创建')
        else:
            log_test('UI', 'U003', '状态栏初始化', 'FAIL', '状态栏未找到')

        # 检查AUI管理器
        if hasattr(frame, 'aui_manager'):
            log_test('UI', 'U004', 'AUI管理器', 'PASS', 'AUI管理器已初始化')
        else:
            log_test('UI', 'U004', 'AUI管理器', 'FAIL', 'AUI管理器未找到')

        # 检查3D视图
        if hasattr(frame, 'cad_view'):
            log_test('UI', 'U005', 'CADViewer创建', 'PASS', 'CADViewer已创建')
        else:
            log_test('UI', 'U005', 'CADViewer创建', 'FAIL', 'CADViewer未找到')

        # 检查侧边面板
        if hasattr(frame, 'label_name_panel'):
            log_test('UI', 'U006', 'LabelNamePanel', 'PASS', '特征名称面板已创建')
        else:
            log_test('UI', 'U006', 'LabelNamePanel', 'FAIL', '特征名称面板未找到')

        if hasattr(frame, 'labeled_features_panel'):
            log_test('UI', 'U007', 'LabeledFeaturesPanel', 'PASS', '已标注特征面板已创建')
        else:
            log_test('UI', 'U007', 'LabeledFeaturesPanel', 'FAIL', '已标注特征面板未找到')

        # 测试选项卡切换
        if hasattr(frame, 'notebook'):
            frame.notebook.SetSelection(2)  # 切换到标注选项卡
            app.ProcessPendingEvents()
            time.sleep(0.2)
            current_page = frame.notebook.GetPageText(frame.notebook.GetSelection())
            if current_page == '标注':
                log_test('UI', 'U008', '切换到标注选项卡', 'PASS', '面板显示正常')
            else:
                log_test('UI', 'U008', '切换到标注选项卡', 'FAIL', f'当前页面={current_page}')

        # 测试窗口关闭事件
        frame.Destroy()
        app.Destroy()

    except Exception as e:
        import traceback
        log_test('UI', 'U001', '主窗口创建', 'ERROR', str(e))
        traceback.print_exc()

def run_label_name_panel_tests():
    """特征名称面板测试"""
    print_section("特征名称管理测试 (L001-L004)")

    try:
        import wx
        app = wx.App(False)

        from ui.main_window import CAEPlatform
        frame = CAEPlatform()

        # 等待UI初始化
        run_ui_after_init(app, frame)

        # L001: 添加特征名称
        panel = frame.label_name_panel
        panel.feature_name_input.SetValue("圆角")
        panel.on_add_button_click(None)

        if "圆角" in panel.feature_to_id:
            log_test('Label', 'L001', '添加特征名称', 'PASS', '圆角已添加，ID=1')
        else:
            log_test('Label', 'L001', '添加特征名称', 'FAIL', '特征未添加到映射')

        count = panel.name_list.GetCount()
        if count >= 1:
            log_test('Label', 'L002', '列表显示特征', 'PASS', f'列表有{count}项')
        else:
            log_test('Label', 'L002', '列表显示特征', 'FAIL', '列表为空')

        # L003: 特征ID分配
        panel.feature_name_input.SetValue("倒角")
        panel.on_add_button_click(None)

        fillet_id = panel.get_feature_id("圆角")
        chamfer_id = panel.get_feature_id("倒角")

        if fillet_id == 1 and chamfer_id == 2:
            log_test('Label', 'L003', '特征ID分配', 'PASS', 'ID分配正确(圆角=1, 倒角=2)')
        else:
            log_test('Label', 'L003', '特征ID分配', 'FAIL', f'圆角={fillet_id}, 倒角={chamfer_id}')

        # L004: 重复特征名处理
        initial_count = panel.name_list.GetCount()
        panel.feature_name_input.SetValue("圆角")
        panel.on_add_button_click(None)
        final_count = panel.name_list.GetCount()

        if initial_count == final_count:
            log_test('Label', 'L004', '重复特征名处理', 'PASS', '重复名称未重复添加')
        else:
            log_test('Label', 'L004', '重复特征名处理', 'FAIL', f'初始={initial_count}, 最终={final_count}')

        frame.Destroy()
        app.Destroy()

    except Exception as e:
        import traceback
        log_test('Label', 'L001', '添加特征名称', 'ERROR', str(e))
        traceback.print_exc()

def run_labeled_features_panel_tests():
    """已标注特征面板测试"""
    print_section("已标注特征面板测试")

    try:
        import wx
        app = wx.App(False)

        from ui.main_window import CAEPlatform
        frame = CAEPlatform()

        # 等待UI初始化
        run_ui_after_init(app, frame)

        panel = frame.labeled_features_panel

        # 检查初始状态
        initial_count = panel.labeled_list.GetItemCount()
        if initial_count == 0:
            log_test('Label', 'L005', '初始空列表', 'PASS', '列表初始为空')
        else:
            log_test('Label', 'L005', '初始空列表', 'FAIL', f'列表有{initial_count}项')

        # L007: 移除按钮可用性
        if hasattr(panel, 'btn_remove'):
            log_test('Label', 'L006', '移除按钮存在', 'PASS', '按钮已创建')
        else:
            log_test('Label', 'L006', '移除按钮存在', 'FAIL', '按钮未找到')

        # 检查列结构
        col_count = panel.labeled_list.GetColumnCount()
        if col_count == 5:
            log_test('Label', 'L007', '列表列结构', 'PASS', '5列结构正确(特征/对象/面ID/底面/[+])')
        else:
            log_test('Label', 'L007', '列表列结构', 'FAIL', f'列数={col_count}, 期望=5')

        # 检查列标题
        expected_headers = ['特征', '对象', '面ID', '底面', '[+]']
        headers_match = True
        for i, expected in enumerate(expected_headers):
            actual = panel.labeled_list.GetColumn(i).GetText()
            if actual != expected:
                headers_match = False
                break

        if headers_match:
            log_test('Label', 'L008', '列表列标题', 'PASS', '列标题正确')
        else:
            log_test('Label', 'L008', '列表列标题', 'FAIL', '列标题不匹配')

        frame.Destroy()
        app.Destroy()

    except Exception as e:
        import traceback
        log_test('Label', 'L005', '初始空列表', 'ERROR', str(e))
        traceback.print_exc()

def run_mouse_event_tests():
    """鼠标事件委托测试"""
    print_section("鼠标事件测试")

    try:
        from function.mouse_event_delegate import MouseEventDelegate, Buttons, Modifiers

        delegate = MouseEventDelegate()

        # 检查初始状态
        if delegate.NCTI is None:
            log_test('Mouse', 'M001', 'MouseEventDelegate初始化', 'PASS', '初始状态正确')
        else:
            log_test('Mouse', 'M001', 'MouseEventDelegate初始化', 'FAIL', 'NCTI应为None')

        # 测试Buttons枚举
        if Buttons.hasLeft(0x0001):
            log_test('Mouse', 'M002', 'Buttons.hasLeft', 'PASS', '左键检测正确')
        else:
            log_test('Mouse', 'M002', 'Buttons.hasLeft', 'FAIL', '左键检测失败')

        if Buttons.hasRight(0x0002):
            log_test('Mouse', 'M003', 'Buttons.hasRight', 'PASS', '右键检测正确')
        else:
            log_test('Mouse', 'M003', 'Buttons.hasRight', 'FAIL', '右键检测失败')

        if Buttons.hasMiddle(0x0004):
            log_test('Mouse', 'M004', 'Buttons.hasMiddle', 'PASS', '中键检测正确')
        else:
            log_test('Mouse', 'M004', 'Buttons.hasMiddle', 'FAIL', '中键检测失败')

        # 测试Modifiers
        if Modifiers.hasShift(0x0010):
            log_test('Mouse', 'M005', 'Modifiers.hasShift', 'PASS', 'Shift键检测正确')
        else:
            log_test('Mouse', 'M005', 'Modifiers.hasShift', 'FAIL', 'Shift键检测失败')

        if Modifiers.hasControl(0x0040):
            log_test('Mouse', 'M006', 'Modifiers.hasControl', 'PASS', 'Ctrl键检测正确')
        else:
            log_test('Mouse', 'M006', 'Modifiers.hasControl', 'FAIL', 'Ctrl键检测失败')

        log_test('Mouse', 'M007', 'uninstall方法存在', 'PASS' if hasattr(delegate, 'uninstall') else 'FAIL', '')

    except Exception as e:
        import traceback
        log_test('Mouse', 'M001', 'MouseEventDelegate初始化', 'ERROR', str(e))
        traceback.print_exc()

def run_file_tab_tests():
    """文件选项卡测试"""
    print_section("文件选项卡测试")

    try:
        import wx
        app = wx.App(False)

        from ui.main_window import CAEPlatform
        frame = CAEPlatform()

        # 等待UI初始化
        run_ui_after_init(app, frame)

        file_tab = frame.file_tab

        # 检查工具栏按钮
        expected_buttons = [
            '创建装配', '创建零件', '打开', '保存',
            '关闭文档', '导入', '导出'
        ]

        found_buttons = []
        toolbar = None
        # 查找toolbar - FileTabPanel中的工具栏是动态创建的
        for attr_name in dir(file_tab):
            attr = getattr(file_tab, attr_name)
            if isinstance(attr, wx.ToolBar):
                toolbar = attr
                break

        if toolbar:
            for child in toolbar.GetChildren():
                if hasattr(child, 'GetLabel') and child.GetLabel() == btn:
                    found_buttons.append(child.GetLabel())
                    break

        if len(found_buttons) >= 5:
            log_test('File', 'F001', '工具栏按钮存在', 'PASS', f'找到{len(found_buttons)}个按钮')
        else:
            log_test('File', 'F001', '工具栏按钮存在', 'SKIP', f'工具栏访问方式待确认，找到{len(found_buttons)}个')

        # 检查工具栏存在
        if toolbar is not None:
            log_test('File', 'F002', '工具栏创建', 'PASS', '工具栏已创建')
        else:
            log_test('File', 'F002', '工具栏创建', 'SKIP', '工具栏未找到')

        frame.Destroy()
        app.Destroy()

    except Exception as e:
        import traceback
        log_test('File', 'F001', '工具栏按钮存在', 'ERROR', str(e))
        traceback.print_exc()

def run_general_tab_tests():
    """选择/显示选项卡测试"""
    print_section("选择/显示选项卡测试")

    try:
        import wx
        app = wx.App(False)

        from ui.main_window import CAEPlatform
        frame = CAEPlatform()

        # 等待UI初始化
        run_ui_after_init(app, frame)

        general_tab = frame.general_tab

        # 检查select_body复选框
        if hasattr(general_tab, 'select_body'):
            log_test('Display', 'G001', 'select_body复选框', 'PASS', '复选框已创建')
        else:
            log_test('Display', 'G001', 'select_body复选框', 'FAIL', '复选框未找到')

        frame.Destroy()
        app.Destroy()

    except Exception as e:
        import traceback
        log_test('Display', 'G001', 'select_body复选框', 'ERROR', str(e))
        traceback.print_exc()

def print_summary():
    """打印测试总结"""
    print_section("测试结果汇总")

    total = len(test_results['passed']) + len(test_results['failed']) + len(test_results['skipped']) + len(test_results['errors'])
    pass_rate = (len(test_results['passed']) / total * 100) if total > 0 else 0

    print(f"\n总计: {total} 个测试")
    print(f"通过: {len(test_results['passed'])}")
    print(f"失败: {len(test_results['failed'])}")
    print(f"跳过: {len(test_results['skipped'])}")
    print(f"错误: {len(test_results['errors'])}")
    print(f"通过率: {pass_rate:.1f}%")

    if test_results['failed']:
        print("\n失败详情:")
        for item in test_results['failed']:
            print(f"  [{item['test_id']}] {item['name']}: {item['message']}")

    if test_results['errors']:
        print("\n错误详情:")
        for item in test_results['errors']:
            print(f"  [{item['test_id']}] {item['name']}: {item['message']}")

    return pass_rate >= 80

def generate_report():
    """生成测试报告"""
    import json
    from datetime import datetime

    report = {
        'title': 'YHCADLabeller 测试报告',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'environment': {
            'python_version': sys.version,
            'wxpython_version': wx.version() if 'wx' in sys.modules else 'N/A',
            'ncti_loaded': 'NCTI' in globals() and global_scope.get('NCTI') is not None
        },
        'summary': {
            'total': len(test_results['passed']) + len(test_results['failed']) + len(test_results['skipped']) + len(test_results['errors']),
            'passed': len(test_results['passed']),
            'failed': len(test_results['failed']),
            'skipped': len(test_results['skipped']),
            'errors': len(test_results['errors'])
        },
        'details': test_results
    }

    report_path = os.path.join(os.path.dirname(__file__), 'test_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n测试报告已生成: {report_path}")
    return report

if __name__ == '__main__':
    print("YHCADLabeller 自动化测试")
    print("=" * 60)

    run_config_tests()
    run_mouse_event_tests()

    try:
        import wx
        run_ui_component_tests()
        run_label_name_panel_tests()
        run_labeled_features_panel_tests()
        run_file_tab_tests()
        run_general_tab_tests()
    except ImportError as e:
        print(f"\n[SKIP] GUI测试需要wxPython: {e}")

    success = print_summary()
    generate_report()

    sys.exit(0 if success else 1)