import sys
import ctypes

import wx.aui

from ui.convert_main_window import ConvertPlatform


if __name__ == "__main__":
    if sys.platform == 'win32':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except AttributeError:
            ctypes.windll.user32.SetProcessDPIAware()

    app = wx.App()
    frame = ConvertPlatform()
    app.MainLoop()
