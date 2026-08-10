import wx

def open_ncti_file_dialog(NCTI,doc,hwnd):
    doc.ResetCaseResult()
    # 创建文件对话框
    dlg = wx.FileDialog(
        None,  # 父窗口
        message="选取NCTI文件",  # 对话框标题
        defaultDir="C:/",  # 默认目录
        defaultFile="",  # 默认文件名
        wildcard="NCTI Files (*.ncti)|*.ncti",  # 文件过滤器
        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST  # 对话框样式
    )
    
    # 显示对话框并获取结果
    if dlg.ShowModal() == wx.ID_OK:
        get_filename_path = dlg.GetPath()
        doc.Delete()
        doc.SetCreateGeGeom(1)
        doc.Open(str(get_filename_path))
        view = NCTI.View(doc.ID)
        view.CreateWindow(hwnd)
        doc.Zoom()
        dlg.Destroy()
        return view
    
    dlg.Destroy()
    return None 