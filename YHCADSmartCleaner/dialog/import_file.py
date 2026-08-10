#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import wx


def import_file_dialog(NCTI, doc):
    doc.ResetCaseResult()
    doc.SetCreateGeGeom(1)
    doc.SetImportAssemelFile(1)
    
    wildcard = "Stp Files|*.stp;*.step| IGS Files|*.igs"
    
    # 创建文件对话框
    dialog = wx.FileDialog(
        None,
        "选取导入模型",
        "C:/",
        "",
        wildcard,
        wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
    )

    # 显示对话框并获取结果
    result = dialog.ShowModal()
    get_filename_path = dialog.GetPath()
    dialog.Destroy()
    
    if result == wx.ID_OK and get_filename_path:
        doc.RunCommand("cmd_ncti_import_file", str(get_filename_path))
        doc.Zoom()
    else:
        get_filename_path = ""
    
    return get_filename_path