import wx

from ai.model_converter import export_weight_to_onnx
from ai.train_client import resolve_python_exe


def convert_model_to_onnx(main_window):
    dialog = wx.FileDialog(None, message="选择要转换的 PTH 权重", wildcard="PTH 权重 (*.pth)|*.pth", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
    try:
        if dialog.ShowModal() != wx.ID_OK:
            return
        weight_path = dialog.GetPath()
    finally:
        dialog.Destroy()

    main_window.status_bar.SetStatusText("正在转换 PTH 权重为 ONNX，请稍候...")
    try:
        onnx_path, report_path, _ = export_weight_to_onnx(weight_path, resolve_python_exe())
    except Exception as error:
        main_window.status_bar.SetStatusText(f"模型转换失败: {error}")
        wx.MessageBox(str(error), "模型转换失败", wx.OK | wx.ICON_ERROR)
        return
    main_window.status_bar.SetStatusText(f"模型转换完成并已验证: {onnx_path}")
    wx.MessageBox(f"ONNX 已保存到：\n{onnx_path}\n\n验证报告：\n{report_path}", "模型转换完成", wx.OK | wx.ICON_INFORMATION)
