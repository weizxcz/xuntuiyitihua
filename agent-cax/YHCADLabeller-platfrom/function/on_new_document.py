from dialog.new_document import new_document_dialog


def new_document_with_dialog(NCTI, doc, hwnd, scale_factor:float=1):

    doc.ResetCaseResult()
    res = new_document_dialog(scale_factor)
    if len(res) > 0:
        return new_document_function(NCTI, doc, hwnd,res[0][0], "", res[1][0])
    return None

def new_document_function(NCTI, doc, hwnd, geom="OCC", cons="DCM", grid="GMSH"):
    doc.New(geom, cons, grid)
    view = NCTI.View(doc.ID)
    view.CreateWindow(hwnd)
    view.SetWindowVis(True, doc.ID)
    doc.SetCreateGeGeom(1)
    doc.Zoom()
    return view
