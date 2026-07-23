import wx


def select_file_base_dialog(parent, wildcard, message: str, default_dir: str, default_file: str):
    # 创建文件对话框
    dialog = wx.FileDialog(
        parent=parent,
        message=message,
        defaultDir=default_dir,
        defaultFile=default_file,
        wildcard=wildcard,
        style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
    )

    # 显示对话框并获取结果
    result = dialog.ShowModal()
    filename_path = dialog.GetPath()
    dialog.Destroy()
    if result == wx.ID_OK and filename_path:
        return filename_path
    return ""
