def set_color(self):
    if not hasattr(self, 'doc') or self.doc.ID == -1:
        return
    if not hasattr(self, 'view'):
        return
    seg = self.doc.Scene()
    modelcolor = self.NCTI.Color(145.0/255.0,158.0/255.0,186.0/255.0)
    backcolor = self.NCTI.Color(60.0/255.0,60.0/255.0,60.0/255.0)
    highlightcolor = self.NCTI.Color(245.0/255.0,128.0/255.0,15.0/255.0)
    vertexcolor = self.NCTI.Color(248.0/255.0, 203.0/255.0, 22.0/255.0)
    if hasattr(seg, 'SetFaceColor'):
        seg.SetFaceColor(modelcolor)
    if hasattr(seg, 'SetBackFaceColor'):
        seg.SetBackFaceColor(backcolor)
    if hasattr(seg, 'SetHighLightColor'):
        seg.SetHighLightColor(highlightcolor)
    if hasattr(seg, 'SetHighContColor'):
        seg.SetHighContColor(highlightcolor)
    if hasattr(seg, 'SetMarkerColor'):
        seg.SetMarkerColor(vertexcolor)
