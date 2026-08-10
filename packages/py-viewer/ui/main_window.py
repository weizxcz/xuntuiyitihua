"""主窗口模块"""
import sys
import os
import io
import ctypes
import importlib
import traceback
import wx
import wx.aui

from config import init_NCTI_Config


class ConsoleOutputWriter:
    """自定义输出写入器 - 同时输出到控制台和 wx 面板"""

    def __init__(self, console_callback=None):
        """
        Args:
            console_callback: 回调函数，用于将输出发送到 wx 面板
        """
        self.console_callback = console_callback
        self.buffer = ""

    def write(self, text):
        """写入文本"""
        self.buffer += text
        # 输出到控制台
        sys.__stdout__.write(text)
        sys.__stdout__.flush()
        # 发送到 wx 面板
        if self.console_callback:
            wx.CallAfter(self.console_callback, text)

    def flush(self):
        """刷新缓冲区"""
        if self.buffer:
            self.buffer = ""


class MainWindow(wx.Frame):
    """主窗口"""

    def __init__(self, NCTI, doc, dll_path: str):
        super().__init__(None, title="炎核 AI 画图工具 V1.0", size=(1200, 800))

        self.HWND = -1
        self.NCTI = NCTI
        self.doc = doc
        self.view = None
        self.dll_path = dll_path
        self.YH = None
        self.yh_doc = None

        # 初始化 AI 服务
        from services.ai_service import AIService
        self.ai_service = AIService()

        # 创建菜单
        self.init_menu()

        # 初始化主布局
        self.init_main_layout()

        self.HWND = self.view_panel.GetHandle()
        self.Centre()
        self.Show()
        self.Layout()

    def init_main_layout(self):
        """初始化主布局"""
        self.aui_manager = wx.aui.AuiManager(self)

        # 右侧 AI 聊天面板（包含 AI 助手和脚本编辑器两个 Tab）
        from ui.chat_panel import AIChatPanel
        self.chat_panel = AIChatPanel(self, self.ai_service, run_script_callback=self.run_sketch_script)
        self.aui_manager.AddPane(self.chat_panel,
                                 wx.aui.AuiPaneInfo().Right().
                                 CaptionVisible(False).Floatable(True).DockFixed(False).
                                 Layer(1).Position(0).BestSize(500, 600))

        # 中心 3D 视图
        self.view_panel = wx.Panel(self, style=wx.SUNKEN_BORDER)
        self.view_panel.SetBackgroundColour(wx.Colour(200, 220, 255))
        self.aui_manager.AddPane(self.view_panel,
                                 wx.aui.AuiPaneInfo().Center().
                                 CaptionVisible(False).CloseButton(False).
                                 Floatable(False).DockFixed(True).
                                 Layer(2).Position(0).MaximizeButton(False).PinButton(False).Movable(False))

        self.aui_manager.Update()

    def init_menu(self):
        """初始化菜单栏"""
        menubar = wx.MenuBar()
        self.SetMenuBar(menubar)

    def init_yh(self):
        """初始化 YH 模块"""
        if self.YH is not None:
            return self.YH

        dllpath = self.dll_path
        os.chdir(dllpath)

        if dllpath not in sys.path:
            sys.path.insert(0, dllpath)

        os.add_dll_directory(dllpath + "/OCC")
        ctypes.CDLL(dllpath + "/ncti_doc_occ.dll")
        ctypes.CDLL(dllpath + "/ncti_occ_plugin.dll")
        ctypes.CDLL(dllpath + "/ncti_command.dll")
        ctypes.CDLL(dllpath + "/yh_command.dll")
        ctypes.CDLL(dllpath + "/yh_object.dll")

        self.YH = importlib.import_module("yh_python")
        self.YH.Init(dllpath)
        return self.YH

    def on_create_doc(self, event):
        """创建文档"""
        # 如果文档已存在，不再创建
        if self.doc.ID != -1:
            return
        if -1 != self.HWND:
            self.init_yh()
            self.yh_doc = self.YH.YHDocument()
            self.yh_doc.NewPart()
            self.doc.ID = self.yh_doc.GetID()

            # 只在第一次创建视图
            if self.view is None:
                self.view = self.NCTI.View(self.doc.ID)
                self.view.CreateWindow(self.HWND)
            width, height = self.view_panel.GetSize()
            self.view.SetWindowVis(True, self.doc.ID)
            self.view.SetGeometry(0, 0, width, height)
            self.doc.Update()
            self.doc.Zoom()

    def ensure_yh_doc_exists(self):
        """确保 yh_doc 存在，如果不存在则创建（不调用 NewPart，避免清空画布）"""
        if self.yh_doc is None:
            self.yh_doc = self.YH.YHDocument(self.doc)
            # 不调用 NewPart()，保留现有画布内容

    def on_close_doc(self, event):
        """关闭文档"""
        self.doc.Close()
        # 清理关联
        self.yh_doc = None
        self.doc.ID = -1
        # 清理视图，下次创建文档时会重新创建
        self.view = None

    def on_import_file(self, event):
        """导入文件"""
        if -1 == self.doc.ID:
            wx.MessageBox("请先新建文档！", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        with wx.FileDialog(self, message="选取导入模型",
                          wildcard="Stp Files (*.stp)|*.stp|Step Files (*.step)|*.step|IGS Files (*.igs)|*.igs",
                          style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.doc.RunCommand("cmd_ncti_import_file", dlg.GetPath())
                self.doc.Zoom()

    def on_zoom(self, event):
        """缩放"""
        self.doc.Zoom()
        self.view.SetViewMode(0)

    def on_clean(self, event):
        """清理"""
        self.doc.Clear()
        self.doc.ResetCaseResult()

    def on_run_sketch_script(self, event):
        """运行草图脚本"""
        if -1 == self.doc.ID:
            self.on_create_doc(None)
        dlg = wx.TextEntryDialog(self, "请输入草图脚本代码:", "运行草图脚本")
        if dlg.ShowModal() == wx.ID_OK:
            script = dlg.GetValue()
            if script.strip():
                output, error, status = self.run_sketch_script(script)
                if output and not error:
                    wx.MessageBox(f"执行成功:\n{output}", "结果", wx.OK | wx.ICON_INFORMATION)
                elif error:
                    wx.MessageBox(f"执行失败:\n{error}", "错误", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def run_sketch_script(self, script: str, description: str = "", show_error: bool = True, output_callback=None):
        """执行脚本

        Args:
            script: 脚本代码
            description: 脚本描述
            show_error: 是否显示错误弹窗，默认 True。AI 自动执行时设为 False
            output_callback: 输出回调函数，用于将 print 输出发送到 wx 面板

        Returns:
            tuple: (output, error, status) - 输出内容、错误信息和文档状态
        """
        output = ""
        error = ""
        status = None

        try:
            # 确保 yh_doc 存在
            if self.yh_doc is None:
                if self.doc.ID == -1:
                    self.on_create_doc(None)
                else:
                    self.ensure_yh_doc_exists()

            YH = self.init_yh()
            if YH is None:
                error = "YH 模块初始化失败！"
                if output_callback:
                    wx.CallAfter(output_callback, error)
                return output, error, status

            if self.yh_doc is None:
                self.yh_doc = self.YH.YHDocument()
                if self.doc.ID == -1:
                    self.yh_doc.NewPart()
                    self.doc.ID = self.yh_doc.GetID()

            output_buffer = io.StringIO()
            # 创建自定义输出写入器，同时输出到控制台、缓冲区和 wx 面板
            console_writer = ConsoleOutputWriter(console_callback=output_callback)
            old_stdout = sys.stdout
            sys.stdout = console_writer

            try:
                global_scope = {
                    "NCTI": self.NCTI, "doc": self.doc,
                    "YH": self.YH,
                    "print": print, "len": len, "str": str, "int": int,
                    "float": float, "list": list, "dict": dict, "tuple": tuple,
                }
                exec(script, global_scope)
                output = output_buffer.getvalue()
                print(f"\n脚本执行完成。输出:\n{output}")
                if description:
                    print(f"脚本执行成功：{description}")
                else:
                    print("脚本执行成功")
                self.doc.Update()
                self.doc.Zoom()

                # 脚本执行成功后，获取文档状态
                status = self.capture_document_status()
                print(status)
                print(f"\n[文档状态] 对象总数：{status['document']['total_objects']}, 名称：{status['document']['object_names']}")
            finally:
                sys.stdout = old_stdout

        except Exception as e:
            tb_str = traceback.format_exc()
            error = tb_str
            # 错误也通过回调输出到面板
            if output_callback:
                wx.CallAfter(output_callback, f"\n{tb_str}")
            else:
                print(tb_str)

        return output, error, status

    def run_sketch_script_http(self, script: str, description: str = "") -> tuple:
        """HTTP 接口调用的脚本执行方法

        Args:
            script: 脚本代码
            description: 脚本描述

        Returns:
            tuple: (output, error, status) - 输出内容、错误信息和文档状态
        """
        return self.run_sketch_script(script, description, show_error=False)

    def capture_document_status(self) -> dict:
        """捕获当前文档状态（仅用 doc API，不含网格和相机）

        Returns:
            dict: 状态 JSON 对象
        """
        from datetime import datetime

        status = {
            "timestamp": datetime.now().isoformat(),
            "document": {
                "id": self.doc.ID if self.doc else -1,
                "is_modified": False,
                "total_objects": 0,
                "object_names": []
            },
            "scene": {
                "root": {
                    "type": "Root",
                    "children": []
                },
                "objects": {}
            },
            "modeling": {
                "objects": []
            },
            "sketch": {
                "is_open": False,
                "active_sketch": None,
                "geometry_list": [],
                "constraints_list": [],
                "is_solved": False,
                "is_fully_constrained": False
            },
            "selection": {
                "selected_objects": [],
                "selected_cell_ids": [],
                "selected_count": 0
            }
        }
        if not self.doc or self.doc.ID == -1:
            return status
        # 文档级信息
        try:
            status["document"]["is_modified"] = bool(self.doc.IsModified())
            object_names = self.doc.AllNames()
            if object_names:
                status["document"]["object_names"] = list(object_names)
                status["document"]["total_objects"] = len(object_names)
        except Exception as e:
            print(f"获取文档信息失败：{e}")

        # 场景信息
        try:
            if hasattr(self.doc, 'Scene') and status["document"]["object_names"]:
                scene_children = []
                for obj_name in status["document"]["object_names"]:
                    try:
                        scene_info = self.doc.Scene(obj_name)
                        if scene_info:
                            scene_children.append(obj_name)
                            status["scene"]["objects"][obj_name] = {
                                "type": scene_info.get("type", "Unknown"),
                                "parent": scene_info.get("parent"),
                                "transform": scene_info.get("transform", [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0])
                            }
                    except Exception as e:
                        print(f"获取场景信息 {obj_name} 失败：{e}")
                status["scene"]["root"]["children"] = scene_children
        except Exception as e:
            print(f"获取场景信息失败：{e}")

        # 建模信息（拓扑和包围盒）
        try:
            for obj_name in status["document"]["object_names"]:
                obj_info = {"name": obj_name}
                try:
                    # 拓扑信息
                    topo_info = self.doc.GetTopoNb(obj_name)
                    if topo_info:
                        obj_info["topology"] = {
                            "vertices": topo_info.get("vertices", 0),
                            "edges": topo_info.get("edges", 0),
                            "faces": topo_info.get("faces", 0)
                        }
                except Exception as e:
                    print(f"获取拓扑信息 {obj_name} 失败：{e}")

                try:
                    # 包围盒信息
                    bbox = self.doc.GetBoundingBox([obj_name])
                    if bbox:
                        obj_info["bounding_box"] = {
                            "min": bbox.get("min", [0, 0, 0]),
                            "max": bbox.get("max", [0, 0, 0])
                        }
                except Exception as e:
                    print(f"获取包围盒信息 {obj_name} 失败：{e}")

                if obj_info.get("topology") or obj_info.get("bounding_box"):
                    status["modeling"]["objects"].append(obj_info)
        except Exception as e:
            print(f"获取建模信息失败：{e}")

        # 草图状态（通过 YH.YHDocument 获取）
        try:
            # 使用已有的 self.yh_doc，或者创建新的 yh_doc
            yh_doc = self.yh_doc
            if yh_doc is None and self.YH and self.doc and self.doc.ID != -1:
                # 创建 yh_doc 并关联到当前文档
                yh_doc = self.YH.YHDocument(self.doc)
                # 注意：这里不调用 NewPart()，避免清空画布

            if yh_doc:
                skt = yh_doc.GetActivitySketch()
                if skt:
                    status["sketch"]["is_open"] = True
                    status["sketch"]["active_sketch"] = skt.ObjectName() if hasattr(skt, 'ObjectName') else None

                    # 获取几何元素列表 - 使用 GetAllDisplayObjects()
                    try:
                        def get_all_attributes(obj, max_depth=2, current_depth=0):
                            """递归获取对象的所有属性"""
                            if current_depth >= max_depth:
                                return obj

                            attrs = {}
                            # 先确保获取 ObjectName 和 ObjectType
                            if hasattr(obj, 'ObjectName'):
                                try:
                                    attrs['ObjectName'] = obj.ObjectName()
                                except:
                                    pass
                            if hasattr(obj, 'ObjectType'):
                                try:
                                    attrs['ObjectType'] = obj.ObjectType()
                                except:
                                    pass

                            # 获取对象的所有可调用和属性
                            for attr_name in dir(obj):
                                # 跳过私有属性和特殊方法
                                if attr_name.startswith('_'):
                                    continue
                                # 已经处理过的跳过
                                if attr_name in ['ObjectName', 'ObjectType']:
                                    continue
                                try:
                                    attr_value = getattr(obj, attr_name)
                                    # 如果是可调用方法，跳过
                                    if callable(attr_value):
                                        continue
                                    # 处理属性值
                                    if attr_value is None:
                                        attrs[attr_name] = None
                                    elif isinstance(attr_value, (int, float, str, bool)):
                                        attrs[attr_name] = attr_value
                                    elif isinstance(attr_value, (list, tuple)):
                                        # 递归处理列表/元组中的对象
                                        attrs[attr_name] = [
                                            get_all_attributes(item, max_depth, current_depth + 1)
                                            if hasattr(item, '__dict__') or hasattr(item, 'ObjectType')
                                            else item for item in attr_value
                                        ]
                                    elif hasattr(attr_value, '__dict__') or hasattr(attr_value, 'ObjectType'):
                                        # 递归处理嵌套对象
                                        attrs[attr_name] = get_all_attributes(attr_value, max_depth, current_depth + 1)
                                    else:
                                        attrs[attr_name] = str(attr_value)
                                except Exception as e:
                                    # 某些属性可能无法访问，跳过
                                    attrs[attr_name] = f"<无法访问：{e}>"
                            return attrs

                        all_geo = skt.GetAllDisplayObjects() if hasattr(skt, 'GetAllDisplayObjects') else []
                        if all_geo:
                            for obj in all_geo:
                                # 获取对象的所有属性（包含 name 和 type）
                                all_attrs = get_all_attributes(obj, max_depth=2)
                                status["sketch"]["geometry_list"].append(all_attrs)
                    except Exception as e:
                        print(f"获取几何信息失败：{e}")

                    # 获取约束列表 - 使用 GetAllConsObjects()
                    try:
                        all_cons = skt.GetAllConsObjects() if hasattr(skt, 'GetAllConsObjects') else []
                        if all_cons:
                            for obj in all_cons:
                                # 获取对象的所有属性（包含 name 和 type）
                                all_attrs = get_all_attributes(obj, max_depth=2)
                                status["sketch"]["constraints_list"].append(all_attrs)
                    except Exception as e:
                        print(f"获取约束信息失败：{e}")

                    # 求解状态
                    try:
                        if hasattr(skt, 'IsSolved'):
                            status["sketch"]["is_solved"] = skt.IsSolved()
                    except Exception as e:
                        print(f"获取求解状态失败：{e}")

                    # 完全约束状态
                    try:
                        if hasattr(skt, 'IsFullyConstrained'):
                            status["sketch"]["is_fully_constrained"] = skt.IsFullyConstrained()
                    except Exception as e:
                        print(f"获取完全约束状态失败：{e}")
        except Exception as e:
            print(f"获取草图状态失败：{e}")

        # 选择集状态
        try:
            sel = self.NCTI.SelectionManager(self.doc)
            if sel:
                if hasattr(sel, 'ObjectNames') and sel.ObjectNames:
                    status["selection"]["selected_objects"] = list(sel.ObjectNames)
                    status["selection"]["selected_count"] = len(sel.ObjectNames)
                if hasattr(sel, 'CellIDs') and sel.CellIDs:
                    status["selection"]["selected_cell_ids"] = list(sel.CellIDs)
        except Exception as e:
            print(f"获取选择集状态失败：{e}")

        return status
