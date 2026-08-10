import wx


class CADViewer(wx.Panel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)

        # 初始化属性
        if parent is not None:
            self.parent = parent
            if hasattr(parent, 'doc'):
                self.doc = parent.doc
            if hasattr(parent, 'NCTI'):
                self.NCTI = parent.NCTI
            if hasattr(parent, 'view'):
                self.view = parent.view
                print(f"cad view init时的view:{self.view}")
                # 确保view对象嵌入到本控件中
                self.embed_view()

        # 绑定尺寸变化事件
        self.Bind(wx.EVT_SIZE, self.on_size)
    
    def embed_view(self):
        """将view对象嵌入到本控件中"""
        if hasattr(self.view, 'CreateWindow'):
            try:
                # 获取本控件的窗口句柄
                hwnd = self.GetHandle()
                # 使用本控件的句柄作为view对象的父窗口
                self.view.CreateWindow(hwnd)
                print(f"成功将view对象嵌入到CADView控件中")
            except Exception as e:
                print(f"嵌入view对象失败: {e}")
    
    def on_size(self, event):
        """尺寸变化事件处理"""
        # 先处理事件，避免事件阻塞
        event.Skip()
        
        # 立即清除背景，防止残留旧视图
        dc = wx.ClientDC(self)
        dc.Clear()
        
        # 更新视图
        self.update_view()

    def update_view(self):
        # 立即刷新，不等待事件队列
        self.Refresh()
        self.Update()

        # 检查必要属性是否存在
        if not hasattr(self, 'doc') or self.doc.ID == -1 or not hasattr(self, 'view'):

            # 当没有doc或view时，明确清除背景
            dc = wx.ClientDC(self)
            dc.Clear()
            dc.DrawRectangle(0, 0, self.GetSize().width, self.GetSize().height)
            
            # 刷新父窗口和自身
            self.Refresh()
            self.Update()
            if hasattr(self, 'parent'):
                self.parent.Refresh()
                self.parent.Update()
            return
        # 获取当前控件的尺寸
        size = self.GetSize()
        
        # 由于view已经嵌入到本控件中，使用相对坐标
        # 对于嵌入的子窗口，位置应该相对于父窗口
        x_pos = 0  # 相对于父窗口的X偏移
        y_pos = 0  # 相对于父窗口的Y偏移
        
        # 如果需要留出空间给文本标签，调整Y偏移
        if hasattr(self, 'text_label'):
            text_size = self.text_label.GetSize()
            y_pos = text_size.height + 10  # 文本标签高度 + 间距
        
        # 调整视图几何
        # 对于嵌入的view对象，位置应该是相对于父窗口的
        # 由于view已经嵌入，不需要再使用屏幕坐标
        self.view.SetGeometry(
            x_pos,  # 相对于父窗口的X坐标
            y_pos,  # 相对于父窗口的Y坐标
            size.width - x_pos,  # 宽度：父窗口宽度 - X偏移
            size.height - y_pos  # 高度：父窗口高度 - Y偏移
        )
        self.parent.Refresh()
        self.view.SetWindowVis(True, self.doc.ID)
        self.view.RenderEnable(True)
        self.doc.Update()
    
    def update_doc(self, parent=None):
        """从父对象更新文档和视图属性"""
        if parent is not None:
            if hasattr(parent, 'doc'):
                self.doc = parent.doc
            if hasattr(parent, 'NCTI'):
                self.NCTI = parent.NCTI
            if hasattr(parent, 'view'):
                self.view = parent.view

    def update(self):
        """更新视图"""
        self.Refresh()
        if hasattr(self, 'doc'):
            self.doc.Update()