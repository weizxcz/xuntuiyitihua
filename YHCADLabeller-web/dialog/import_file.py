#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import wx
import os

from utils.file_finder import json_labels_path_to_step_path


def import_file_dialog(NCTI, doc, include_json=False):
    doc.ResetCaseResult()
    doc.SetCreateGeGeom(1)
    doc.SetImportAssemelFile(1)

    if include_json:
        wildcard = "Json Files|*.json| Stp Files|*.stp;*.step| IGS Files|*.igs"
    else:
        wildcard = "Stp Files|*.stp;*.step| IGS Files|*.igs"

    dialog = wx.FileDialog(
        None,
        "选取导入模型",
        "",
        "",
        wildcard,
        wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
    )

    result = dialog.ShowModal()
    get_filename_path = dialog.GetPath()
    dialog.Destroy()

    if result == wx.ID_OK and get_filename_path:
        file_ext = os.path.splitext(get_filename_path)[1].lower()

        if file_ext == ".json":
            step_path = json_labels_path_to_step_path(get_filename_path)
            if step_path:
                doc.RunCommand("cmd_ncti_import_file", str(step_path))
            else:
                get_filename_path = ""
        else:
            doc.RunCommand("cmd_ncti_import_file", str(get_filename_path))

        doc.Zoom()
    else:
        get_filename_path = ""

    return get_filename_path