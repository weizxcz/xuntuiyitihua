import sys
import ctypes

import wx
import wx.aui

from ui.main_window import CAEPlatform
from ai.train_client import terminate_process_tree


class CAEPlatformApp(wx.App):
    """应用实例。重写 OnExit，在主循环结束后清理仍在进行中的训练/生成 graph
    子进程，避免它们变成孤儿进程继续占用 GPU/内存直到自然结束。"""

    def __init__(self, *args, **kwargs):
        self.frame = None
        super().__init__(*args, **kwargs)

    def OnExit(self):
        frame = self.frame
        job = getattr(frame, "train_job", None) if frame is not None else None
        if job is not None:
            terminate_process_tree(job.get("proc"))
        return super().OnExit()


if __name__ == "__main__":
    if sys.platform == 'win32':
        try:
            # 设置DPI感知级别为2（每监视器DPI感知）- Windows 8.1+支持
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except AttributeError:
            # 兼容Windows 7等旧版本
            ctypes.windll.user32.SetProcessDPIAware()

    app = CAEPlatformApp()
    frame = CAEPlatform()
    app.frame = frame
    app.MainLoop()
