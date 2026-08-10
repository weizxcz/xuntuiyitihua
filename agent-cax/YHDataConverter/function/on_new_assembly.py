from dialog.new_assembly import new_assembly_dialog


def new_assembly_with_dialog(NCTI,doc,hwnd, scale_factor:float=1):
    doc.ResetCaseResult()
    res = new_assembly_dialog(scale_factor)
    if len(res) > 0:
        doc.NewAssemble(res[0])
        view = NCTI.View(doc.ID)
        doc.SetCreateGeGeom(1)  # 不生成平台对象（不生成会快）
        view.CreateWindow(hwnd)
        view.SetWindowVis(True,doc.ID)
        doc.Zoom()
        return view
