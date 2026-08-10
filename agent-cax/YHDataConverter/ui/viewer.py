import wx


class CADViewer(wx.Panel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)

        if parent is not None:
            self.parent = parent
            if hasattr(parent, 'doc'):
                self.doc = parent.doc
            if hasattr(parent, 'NCTI'):
                self.NCTI = parent.NCTI
            if hasattr(parent, 'view'):
                self.view = parent.view
                self.embed_view()

        self.Bind(wx.EVT_SIZE, self.on_size)

    def embed_view(self):
        if hasattr(self, 'view') and hasattr(self.view, 'CreateWindow'):
            try:
                hwnd = self.GetHandle()
                self.view.CreateWindow(hwnd)
            except Exception as e:
                print(f"嵌入view对象失败: {e}")

    def on_size(self, event):
        event.Skip()
        dc = wx.ClientDC(self)
        dc.Clear()
        self.update_view()

    def update_view(self):
        self.Refresh()
        self.Update()

        if not hasattr(self, 'doc') or self.doc.ID == -1 or not hasattr(self, 'view'):
            dc = wx.ClientDC(self)
            dc.Clear()
            dc.DrawRectangle(0, 0, self.GetSize().width, self.GetSize().height)
            self.Refresh()
            self.Update()
            if hasattr(self, 'parent'):
                self.parent.Refresh()
                self.parent.Update()
            return

        size = self.GetSize()

        x_pos = 0
        y_pos = 0

        if hasattr(self, 'text_label'):
            text_size = self.text_label.GetSize()
            y_pos = text_size.height + 10

        self.view.SetGeometry(
            x_pos,
            y_pos,
            size.width - x_pos,
            size.height - y_pos
        )
        self.parent.Refresh()
        self.view.SetWindowVis(True, self.doc.ID)
        self.view.RenderEnable(True)
        self.doc.Update()

    def update_doc(self, parent=None):
        if parent is not None:
            if hasattr(parent, 'doc'):
                self.doc = parent.doc
            if hasattr(parent, 'NCTI'):
                self.NCTI = parent.NCTI
            if hasattr(parent, 'view'):
                self.view = parent.view

    def update(self):
        self.Refresh()
        if hasattr(self, 'doc'):
            self.doc.Update()
