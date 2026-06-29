#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import wx


def new_assembly_dialog(scale_factor:float=1.0):
    # 创建对话框，不设置固定size，让布局管理器自动计算
    dialog = wx.Dialog(None, title="创建装配文档",
                       size = (int(400*scale_factor), int(300*scale_factor)),
                       style=wx.DEFAULT_DIALOG_STYLE)

    # 创建垂直布局管理器
    main_sizer = wx.BoxSizer(wx.VERTICAL)

    # 文档名称行
    name_sizer = wx.BoxSizer(wx.HORIZONTAL)
    name_label = wx.StaticText(dialog, label="文档名称")
    name_text = wx.TextCtrl(dialog, value="装配", style=wx.TE_LEFT)
    name_sizer.Add(name_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    name_sizer.Add(name_text, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    main_sizer.Add(name_sizer, 0, wx.EXPAND | wx.ALL, 5)

    # 几何引擎行
    geometry_sizer = wx.BoxSizer(wx.HORIZONTAL)
    geometry_label = wx.StaticText(dialog, label="几何引擎")
    geometry_choices = ["OCC"]
    geometry_combo = wx.ComboBox(dialog, choices=geometry_choices, value="OCC", style=wx.CB_READONLY)
    geometry_sizer.Add(geometry_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    geometry_sizer.Add(geometry_combo, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    main_sizer.Add(geometry_sizer, 0, wx.EXPAND | wx.ALL, 5)

    # 约束引擎行
    constraint_sizer = wx.BoxSizer(wx.HORIZONTAL)
    constraint_label = wx.StaticText(dialog, label="约束引擎")
    constraint_choices = ["DCM"]
    constraint_combo = wx.ComboBox(dialog, choices=constraint_choices, value="DCM", style=wx.CB_READONLY)
    constraint_sizer.Add(constraint_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    constraint_sizer.Add(constraint_combo, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    main_sizer.Add(constraint_sizer, 0, wx.EXPAND | wx.ALL, 5)

    # 网格引擎行
    mesh_sizer = wx.BoxSizer(wx.HORIZONTAL)
    mesh_label = wx.StaticText(dialog, label="网格引擎")
    mesh_choices = ["GMSH"]
    mesh_combo = wx.ComboBox(dialog, choices=mesh_choices, value="GMSH", style=wx.CB_READONLY)
    mesh_sizer.Add(mesh_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    mesh_sizer.Add(mesh_combo, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    main_sizer.Add(mesh_sizer, 0, wx.EXPAND | wx.ALL, 5)

    # 按钮行
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    cancel_button = wx.Button(dialog, label="退出")
    ok_button = wx.Button(dialog, label="确定")

    # 设置确定按钮为蓝色底色
    ok_button.SetBackgroundColour(wx.Colour(0, 100, 255))
    ok_button.SetForegroundColour(wx.WHITE)  # 设置文字为白色，与蓝色背景对比

    # 设置按钮事件
    def on_cancel(event):
        dialog.EndModal(wx.ID_CANCEL)

    def on_ok(event):
        dialog.EndModal(wx.ID_OK)

    cancel_button.Bind(wx.EVT_BUTTON, on_cancel)
    ok_button.Bind(wx.EVT_BUTTON, on_ok)

    # 添加按钮到布局，两个按钮占满宽度
    button_sizer.Add(cancel_button, 1, wx.ALL | wx.EXPAND, 5)
    button_sizer.Add(ok_button, 1, wx.ALL | wx.EXPAND, 5)
    main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 5)

    # 设置对话框布局
    dialog.SetSizer(main_sizer)
    dialog.Layout()
    dialog.Centre()

    # 显示对话框
    result = dialog.ShowModal()

    # 处理结果
    if result == wx.ID_OK:
        doc_name = name_text.GetValue()
        geometry_engine = geometry_combo.GetValue()
        constraint_engine = constraint_combo.GetValue()
        mesh_engine = mesh_combo.GetValue()
        dialog.Destroy()
        # 返回文档名称、几何引擎、约束引擎和网格引擎
        return [doc_name, geometry_engine, constraint_engine, mesh_engine]
    else:
        dialog.Destroy()
        return []