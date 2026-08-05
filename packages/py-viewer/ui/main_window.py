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
            self.yh_doc = self.YH.YHDocument()
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
                output, error = self.run_sketch_script(script)
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
            tuple: (output, error) - 输出内容和错误信息
        """
        output = ""
        error = ""

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
                return output, error

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

        return output, error

    def run_sketch_script_http(self, script: str, description: str = "") -> tuple:
        """HTTP 接口调用的脚本执行方法

        Args:
            script: 脚本代码
            description: 脚本描述

        Returns:
            tuple: (output, error) - 输出内容和错误信息
        """
        return self.run_sketch_script(script, description, show_error=False)
