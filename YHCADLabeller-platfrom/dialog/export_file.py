import wx

def export_file_dialog(NCTI,doc):
    doc.ResetCaseResult()
    
    # 创建保存文件对话框
    dlg = wx.FileDialog(
        None,  # 父窗口
        message="输入导出的文件",  # 对话框标题
        defaultDir="C:/",  # 默认目录
        defaultFile="",  # 默认文件名
        wildcard="模型文件 (*.igs;*.stp;*.step;*.brep;*.sat;*.prt)|*.igs;*.stp;*.step;*.brep;*.sat;*.prt",  # 文件过滤器
        style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT  # 对话框样式：保存模式 + 覆盖提示
    )
    
    # 显示对话框并获取结果
    filename_path = ""
    if dlg.ShowModal() == wx.ID_OK:
        filename_path = dlg.GetPath()
        sel = NCTI.SelectionManager(doc)
        names = sel.ObjectNames
        if len(names) == 0:
            names = doc.AllNames()
        doc.RunCommand("cmd_ncti_export_file", str(filename_path), names)
    
    # 销毁对话框，释放资源
    dlg.Destroy()
    return filename_path
