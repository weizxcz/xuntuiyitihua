"""AI 聊天面板模块"""
import sys
import io
import threading
import wx
from typing import Optional

from services.ai_service import AIService


class AIChatPanel(wx.Panel):
    """AI 聊天面板 - 纯 Python 实现，包含 AI 聊天和脚本编辑两个 Tab"""

    def __init__(self, parent, ai_service: AIService, run_script_callback=None):
        super().__init__(parent, style=wx.SUNKEN_BORDER)
        self.ai_service = ai_service
        self.is_processing = False
        self.thread_id = None
        self.stop_flag = None
        self.run_script_callback = run_script_callback

        self.init_ui()

    def init_ui(self):
        # 创建 Tab 控件
        self.notebook = wx.Notebook(self, style=wx.NB_TOP)

        # 创建 AI 聊天 Tab
        self.ai_chat_tab = self._create_ai_chat_tab()
        self.notebook.AddPage(self.ai_chat_tab, "AI 助手")

        # 创建脚本编辑 Tab
        self.script_tab = self._create_script_tab()
        self.notebook.AddPage(self.script_tab, "脚本编辑器")

        # 主布局
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        main_sizer.Add(self.notebook, 1, wx.EXPAND)
        self.SetSizer(main_sizer)

    def _create_ai_chat_tab(self) -> wx.Panel:
        """创建 AI 聊天 Tab"""
        panel = wx.Panel(self.notebook)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # 聊天消息显示区域 - 使用 TextCtrl 支持富文本
        self.chat_log = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
        )
        self.chat_log.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.chat_log.SetBackgroundColour(wx.Colour(255, 255, 255))
        main_sizer.Add(self.chat_log, 1, wx.EXPAND | wx.ALL, 5)

        # 输入区域 - 参考 Qt 样式
        input_panel = wx.Panel(panel)
        input_panel.SetBackgroundColour(wx.Colour(255, 255, 255))

        # 输入框和按钮容器
        input_container = wx.Panel(input_panel)
        input_container.SetBackgroundColour(wx.Colour(255, 255, 255))

        input_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # 输入框 - 单行样式
        self.input_text = wx.TextCtrl(input_container, style=wx.TE_PROCESS_ENTER)
        self.input_text.SetMinSize((-1, 40))
        self.input_text.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.input_text.SetBackgroundColour(wx.Colour(255, 255, 255))
        self.input_text.Bind(wx.EVT_TEXT_ENTER, self.on_send)
        self.input_text.Bind(wx.EVT_TEXT, self.on_text_change)
        input_sizer.Add(self.input_text, 1, wx.EXPAND | wx.RIGHT, 10)

        # 发送按钮 - 圆形按钮
        self.send_btn = wx.Button(input_container, label="发送")
        self.send_btn.SetMinSize((40, 40))
        self.send_btn.SetMaxSize((40, 40))
        self.send_btn.SetBackgroundColour(wx.Colour(0, 217, 255))
        self.send_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        self.send_btn.Bind(wx.EVT_BUTTON, self.on_send)
        input_sizer.Add(self.send_btn, 0, wx.RIGHT, 0)

        # 停止按钮 - 圆形按钮
        self.stop_btn = wx.Button(input_container, label="停止")
        self.stop_btn.SetMinSize((40, 40))
        self.stop_btn.SetMaxSize((40, 40))
        self.stop_btn.SetBackgroundColour(wx.Colour(200, 200, 200))
        self.stop_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        self.stop_btn.Enable(False)
        self.stop_btn.Bind(wx.EVT_BUTTON, self.on_stop)
        input_sizer.Add(self.stop_btn, 0, wx.LEFT, 5)

        # 清空按钮 - 圆形按钮
        self.clear_btn = wx.Button(input_container, label="清空")
        self.clear_btn.SetMinSize((40, 40))
        self.clear_btn.SetMaxSize((40, 40))
        self.clear_btn.SetBackgroundColour(wx.Colour(255, 100, 100))
        self.clear_btn.SetForegroundColour(wx.Colour(255, 255, 255))
        self.clear_btn.Bind(wx.EVT_BUTTON, self.on_clear)
        input_sizer.Add(self.clear_btn, 0, wx.LEFT, 5)

        input_container.SetSizer(input_sizer)
        input_panel.SetSizer(wx.BoxSizer(wx.VERTICAL))
        input_panel.GetSizer().Add(input_container, 1, wx.EXPAND | wx.ALL, 10)

        main_sizer.Add(input_panel, 0, wx.EXPAND | wx.BOTTOM, 10)

        panel.SetSizer(main_sizer)
        return panel

    def _create_script_tab(self) -> wx.Panel:
        """创建脚本编辑 Tab"""
        from ui.script_panel import ScriptPanel
        script_panel = ScriptPanel(self.notebook, run_script_callback=self._run_script)
        return script_panel

    def _run_script(self, script: str, description: str, output_callback=None):
        """运行脚本的回调方法

        Args:
            script: 脚本代码
            description: 脚本描述
            output_callback: 输出回调函数
        """
        frame = self.GetTopLevelParent()
        if hasattr(frame, 'run_sketch_script'):
            output, error = frame.run_sketch_script(script, description, show_error=False, output_callback=output_callback)
            if error:
                self.append_message('error', f"脚本执行失败:\n{error}")
            else:
                self.append_message('tool', f"脚本执行成功:\n{output}")

    def append_message(self, role: str, content: str, append: bool = False):
        """添加消息到聊天日志

        Args:
            role: 消息角色 (user/assistant/tool/error)
            content: 消息内容
            append: 是否追加到上一条消息（用于流式输出）
        """
        def do_append():
            # 定义颜色
            colors = {
                'user': (200, 220, 255),      # 浅蓝色
                'assistant': (245, 245, 245), # 浅灰色
                'tool': (220, 255, 220),      # 浅绿色
                'error': (255, 220, 220),     # 浅红色
            }

            # 根据角色设置样式
            bg_color = colors.get(role, (255, 255, 255))

            # 设置样式
            style = wx.TextAttr()
            style.SetBackgroundColour(wx.Colour(*bg_color))
            self.chat_log.SetStyle(0, 0, style)

            # 如果是追加模式，直接追加内容；否则添加分隔符和新标签
            if append:
                self.chat_log.AppendText(content)
            else:
                # 添加消息分隔符
                self.chat_log.AppendText("\n" + "=" * 40 + "\n")

                # 添加消息内容
                if role == 'user':
                    self.chat_log.AppendText(f"你：{content}\n")
                elif role == 'assistant':
                    self.chat_log.AppendText(f"AI：{content}\n")
                elif role == 'tool':
                    self.chat_log.AppendText(f"工具：{content}\n")
                elif role == 'error':
                    self.chat_log.AppendText(f"错误：{content}\n")
                else:
                    self.chat_log.AppendText(f"{content}\n")

            # 自动滚动到底部
            self.chat_log.ShowPosition(self.chat_log.GetLastPosition())

        wx.CallAfter(do_append)

    def on_text_change(self, event):
        """输入框文本变化时启用/禁用发送按钮"""
        has_text = bool(self.input_text.GetValue().strip())
        self.send_btn.Enable(has_text and not self.is_processing)
        event.Skip()

    def on_send(self, event):
        """发送按钮点击处理"""
        content = self.input_text.GetValue().strip()
        if not content or self.is_processing:
            return

        self.input_text.Clear()
        self.append_message('user', content)

        # 启动 AI 响应线程
        self.is_processing = True
        self.stop_btn.Enable(True)
        self.stop_flag = threading.Event()

        # 确保线程存在
        if not self.ai_service._thread_id:
            try:
                thread = self.ai_service.create_thread()
                self.ai_service._thread_id = thread.get('thread_id')
            except Exception as e:
                self.append_message('error', f"创建线程失败：{e}")
                self.is_processing = False
                self.stop_btn.Enable(False)
                return

        threading.Thread(target=self.send_to_ai, args=(content,), daemon=True).start()

    def on_stop(self, event):
        """停止按钮点击处理"""
        if self.stop_flag:
            self.stop_flag.set()
        # 真正中断 HTTP 连接
        self.ai_service.stop_stream()
        self.is_processing = False
        self.stop_btn.Enable(False)

    def on_clear(self, _):
        """清空按钮点击处理 - 清空聊天记录并关闭文档"""
        # 清空聊天日志
        self.chat_log.Clear()
        # 重置 AI 线程
        self.ai_service._thread_id = None
        # 关闭文档
        frame = self.GetTopLevelParent()
        if hasattr(frame, 'on_close_doc'):
            frame.on_close_doc(None)

    def send_to_ai(self, content: str):
        """发送消息到 AI 并处理响应

        Args:
            content: 要发送的消息内容
        """
        try:
            thread_id = self.ai_service._thread_id

            # 用于跟踪已处理的 tool call，避免重复
            processed_tool_call_ids = set()
            # 用于消息去重（messages-last）：跟踪最后一条消息的 ID
            last_message_id = ""
            # 收集新的执行结果
            new_results = []

            for event in self.ai_service.stream_message(thread_id, content, stop_flag=self.stop_flag):
                if self.stop_flag and self.stop_flag.is_set():
                    break
                event_type = event.get('type')
                data = event.get('data', {})

                # messages 模式：用于展示聊天记录
                if event_type == 'messages':
                    if isinstance(data, list) and len(data) >= 1:
                        msg_chunk = data[0]
                        if msg_chunk and isinstance(msg_chunk, dict):
                            msg_type = msg_chunk.get('type')
                            msg_content = msg_chunk.get('content', '')
                            if msg_type == 'AIMessageChunk' and msg_content:
                                self.append_message('assistant', msg_content, append=True)

                # messages-last 模式：解析工具事件并执行
                if event_type == 'messages-last':
                    messages = data.get('messages', [])
                    if messages:
                        last_msg = messages[0]
                        msg_id = last_msg.get('id', '')

                        # 消息去重
                        if msg_id and msg_id == last_message_id:
                            continue
                        if msg_id:
                            last_message_id = msg_id

                        # 检查 tool_calls
                        tool_calls = last_msg.get('tool_calls', [])
                        for tool_call in tool_calls:
                            tool_id = tool_call.get('id')
                            tool_name = tool_call.get('name', '')
                            tool_args = tool_call.get('args', {})

                            if tool_id and tool_id in processed_tool_call_ids:
                                continue
                            if tool_id:
                                processed_tool_call_ids.add(tool_id)

                            if tool_name == 'exec_script':
                                script_info = tool_args
                                desc = script_info.get('description', 'AI 自动执行的脚本')
                                script_code = script_info.get('script', '')
                                print(script_code)
                                self.append_message('tool', f"正在执行：{desc}")
                                self.append_message('tool', f"正在执行：{script_code}")

                                result = self.execute_script(script_code, desc)

                                if result is not None:
                                    new_results.append(result)
                                else:
                                    new_results.append({
                                        'success': False,
                                        'error': '执行脚本返回结果为空'
                                    })

            # 流结束后，如果有执行失败的脚本，将错误信息递归调用继续处理
            failed_results = [r for r in new_results if not r.get('success')]
            if failed_results:
                # 构建错误消息内容
                result_text = "脚本执行失败："
                for i, result in enumerate(failed_results, 1):
                    result_text += f"\n[结果 {i}] 错误：{result.get('error', '未知错误')}"

                self.append_message('tool', result_text)
                self.append_message('tool', "正在发送给 AI...")

                # 递归调用继续处理
                self.send_to_ai(result_text)
                return

        except Exception as e:
            self.append_message('error', str(e))
        finally:
            self.is_processing = False
            wx.CallAfter(self.stop_btn.Enable, False)

    def execute_script(self, script: str, description: str) -> Optional[dict]:
        """执行脚本（AI 自动执行，不显示错误弹窗）

        Args:
            script: 脚本代码
            description: 脚本描述

        Returns:
            执行结果字典，失败返回 None
        """
        result = {'success': False, 'error': '未知错误'}
        event = threading.Event()

        def do_execute():
            nonlocal result
            try:
                frame = self.GetTopLevelParent()
                if hasattr(frame, 'run_sketch_script'):
                    # show_error=False 表示不弹窗，output_callback=None 表示不输出到面板
                    output, error = frame.run_sketch_script(script, description, show_error=False, output_callback=None)
                    # 如果有 error，success 设为 False，让 AI 知道需要修正
                    if error:
                        result = {
                            'success': False,
                            'error': error,
                            'result': {
                                'output': output,
                                'error': error,
                                'description': description
                            }
                        }
                    else:
                        result = {
                            'success': True,
                            'result': {
                                'output': output,
                                'error': error,
                                'description': description
                            }
                        }
            except Exception as e:
                result = {'success': False, 'error': str(e)}
            finally:
                event.set()

        wx.CallAfter(do_execute)
        # 等待执行完成（最多等待 30 秒）
        event.wait(timeout=30)
        print(f"脚本执行结果：{result}")
        return result
