import sys
import ctypes

import wx.aui

from ui.main_window import CAEPlatform


if __name__ == "__main__":
    if sys.platform == 'win32':
        try:
            # 设置DPI感知级别为2（每监视器DPI感知）- Windows 8.1+支持
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except AttributeError:
            # 兼容Windows 7等旧版本
            ctypes.windll.user32.SetProcessDPIAware()
    
    app = wx.App()
    frame = CAEPlatform()
    app.MainLoop()
