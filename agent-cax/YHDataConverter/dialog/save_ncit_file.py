import wx

def save_ncit_file_dialog(NCTI,doc):
    doc.ResetCaseResult()
    
    # 创建保存文件对话框
    dlg = wx.FileDialog(
        None,  # 父窗口
        message="输入保存文件",  # 对话框标题
        defaultDir="C:/",  # 默认目录
        defaultFile="",  # 默认文件名
        wildcard="NCTI Files (*.ncti)|*.ncti",  # 文件过滤器
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT  # 对话框样式：保存模式 + 覆盖提示
    )
    
    # 显示对话框并获取结果
    if dlg.ShowModal() == wx.ID_OK:
        get_filename_path = dlg.GetPath()
        doc.Save(str(get_filename_path))
    
    # 销毁对话框，释放资源
    dlg.Destroy()