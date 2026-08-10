"""脚本编辑和执行面板模块"""
import wx
from typing import Optional


class ScriptPanel(wx.Panel):
    """脚本编辑和执行面板"""

    def __init__(self, parent, run_script_callback=None):
        super().__init__(parent, style=wx.SUNKEN_BORDER)
        self.run_script_callback = run_script_callback
        self.is_processing = False

        self.init_ui()

    def init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 工具栏按钮区域
        toolbar_panel = wx.Panel(self)
        toolbar_panel.SetBackgroundColour(wx.Colour(255, 255, 255))
        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 执行按钮
        self.run_btn = wx.Button(toolbar_panel, label="▶")
        self.run_btn.SetMinSize((20, 20))
        self.run_btn.SetMaxSize((20, 20))
        self.run_btn.SetBackgroundColour(wx.Colour(0, 217, 255))
        self.run_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        self.run_btn.Bind(wx.EVT_BUTTON, self.on_run_script)
        toolbar_sizer.Add(self.run_btn, 0, wx.RIGHT, 5)

        # 清空按钮
        self.clear_btn = wx.Button(toolbar_panel, label="✕")
        self.clear_btn.SetMinSize((20, 20))
        self.clear_btn.SetMaxSize((20, 20))
        self.clear_btn.SetBackgroundColour(wx.Colour(255, 100, 100))
        self.clear_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        self.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)
        toolbar_sizer.Add(self.clear_btn, 0)

        toolbar_panel.SetSizer(toolbar_sizer)
        main_sizer.Add(toolbar_panel, 0, wx.EXPAND | wx.ALL, 5)

        # 脚本编辑区域
        self.script_editor = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_RICH2
        )
        self.script_editor.SetFont(wx.Font(11, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.script_editor.SetBackgroundColour(wx.Colour(255, 255, 255))
        main_sizer.Add(self.script_editor, 2, wx.EXPAND | wx.ALL, 5)

        # 输出区域
        self.output_log = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
        )
        self.output_log.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.output_log.SetBackgroundColour(wx.Colour(255, 255, 255))
        main_sizer.Add(self.output_log, 1, wx.EXPAND | wx.ALL, 5)

        self.SetSizer(main_sizer)

    def on_clear(self, event):
        """清空按钮点击处理"""
        self.script_editor.Clear()
        self.output_log.Clear()
        # 清空编辑器不关闭文档，只清空脚本和输出

    def on_run_script(self, event):
        """执行脚本按钮点击处理"""
        script = self.script_editor.GetValue().strip()
        if not script:
            self.append_output("error", "请输入脚本代码！")
            return

        if self.is_processing:
            self.append_output("info", "脚本正在执行中，请稍候！")
            return

        # 清空之前的输出
        self.output_log.Clear()

        # 启动执行
        self.is_processing = True

        # 定义输出回调函数
        def on_output(text):
            """将输出追加到 wx 面板"""
            wx.CallAfter(self.append_output, "info", text)

        # 同步执行脚本
        try:
            if self.run_script_callback:
                self.run_script_callback(script, "手动执行的脚本", output_callback=on_output)
            else:
                self.append_output("error", "未设置脚本执行回调")
        except Exception as e:
            self.append_output("error", f"执行失败:\n{str(e)}")
        finally:
            self.is_processing = False

    def append_output(self, level: str, message: str):
        """添加输出信息

        Args:
            level: 输出级别 (success/error/info)
            message: 输出消息
        """
        def do_append():
            if level == "success":
                style = wx.TextAttr(wx.Colour(0, 128, 0))
            elif level == "error":
                style = wx.TextAttr(wx.Colour(255, 0, 0))
            else:
                style = wx.TextAttr(wx.Colour(0, 0, 0))

            self.output_log.SetDefaultStyle(style)
            self.output_log.AppendText(f"{message}\n")
            self.output_log.ShowPosition(self.output_log.GetLastPosition())

        wx.CallAfter(do_append)
