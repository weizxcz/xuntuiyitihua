def set_color(self):
    if False == hasattr(self, 'doc') or self.doc.ID == -1:
        return
    if False == hasattr(self, 'view'):
        return
    seg = self.doc.Scene()
    modelcolor = self.NCTI.Color(145.0/255.0,158.0/255.0,186.0/255.0)
    backcolor = self.NCTI.Color(60.0/255.0,60.0/255.0,60.0/255.0)
    highlightcolor = self.NCTI.Color(245.0/255.0,128.0/255.0,15.0/255.0)
    vertexcolor = self.NCTI.Color(248.0/255.0, 203.0/255.0, 22.0/255.0)
    seg.SetFaceColor(modelcolor)
    seg.SetBackFaceColor(backcolor)
    seg.SetHighLightColor(highlightcolor)
    seg.SetHighContColor(highlightcolor)
    seg.SetMarkerColor(vertexcolor)
    self.view.SetBackgroundColor(5, 38, 79,81, 90, 146)