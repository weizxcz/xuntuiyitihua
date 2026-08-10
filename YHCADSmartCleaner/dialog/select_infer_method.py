import wx


def select_infer_method_dialog(parent, title: str):
    """选择识别算法对话框"""
    # 创建对话框
    dialog = wx.Dialog(parent, title=title, size=(400, 250), style=wx.DEFAULT_DIALOG_STYLE)

    # 创建垂直布局管理器
    main_sizer = wx.BoxSizer(wx.VERTICAL)

    # 圆角类型行
    fillet_type_sizer = wx.BoxSizer(wx.HORIZONTAL)
    fillet_type_label = wx.StaticText(dialog, label="算法")
    fillet_type_choices = ["AAG", "MFR", "AAG+几何"]
    fillet_type_combo = wx.ComboBox(dialog, choices=fillet_type_choices, value="AAG", style=wx.CB_READONLY)
    fillet_type_sizer.Add(fillet_type_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    fillet_type_sizer.Add(fillet_type_combo, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
    main_sizer.Add(fillet_type_sizer, 0, wx.EXPAND | wx.ALL, 5)

    # 按钮行
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    cancel_button = wx.Button(dialog, label="退出")
    ok_button = wx.Button(dialog, label="确定")

    # 设置按钮事件
    cancel_button.Bind(wx.EVT_BUTTON, lambda event: dialog.EndModal(wx.ID_CANCEL))
    ok_button.Bind(wx.EVT_BUTTON, lambda event: dialog.EndModal(wx.ID_OK))

    # 将按钮添加到布局
    button_sizer.Add(cancel_button, 1, wx.ALL | wx.ALIGN_CENTER, 5)
    button_sizer.Add(ok_button, 1, wx.ALL | wx.ALIGN_CENTER, 5)
    main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 5)

    # 设置对话框布局
    dialog.SetSizer(main_sizer)
    dialog.Layout()
    dialog.Centre()

    # 显示对话框并获取结果
    result = dialog.ShowModal()

    # 处理结果
    if result == wx.ID_OK:
        # 获取用户输入
        fillet_type = fillet_type_combo.GetValue()

        # 关闭对话框
        dialog.Destroy()

        return fillet_type
    else:
        # 关闭对话框
        dialog.Destroy()
        # 返回空列表表示取消
        return ""
