from enum import Enum


class Buttons(Enum):
    ncti_button_none = 0x0000
    ncti_button_left = 0x0001
    ncti_button_right = 0x0002
    ncti_button_middle = 0x0004
    ncti_button_x1 = 0x0008
    ncti_button_x2 = 0x0010

    @staticmethod
    def hasLeft(buttons):
        return buttons & Buttons.ncti_button_left.value != 0

    @staticmethod
    def hasRight(buttons):
        return buttons & Buttons.ncti_button_right.value != 0

    @staticmethod
    def hasMiddle(buttons):
        return buttons & Buttons.ncti_button_middle.value != 0

    @staticmethod
    def hasX1(buttons):
        return buttons & Buttons.ncti_button_x1.value != 0

    @staticmethod
    def hasX2(buttons):
        return buttons & Buttons.ncti_button_x2.value != 0


class Modifiers(Enum):
    ncti_key_none = 0x0000
    ncti_key_caps_lock = 0x0001
    ncti_key_num_lock = 0x0002
    ncti_key_scroll_lock = 0x0004
    ncti_key_right_shift = 0x0008
    ncti_key_left_shift = 0x0010
    ncti_key_right_control = 0x0020
    ncti_key_left_control = 0x0040
    ncti_key_right_alt = 0x0080
    ncti_key_left_alt = 0x0100
    ncti_key_right_meta = 0x0200
    ncti_key_left_meta = 0x0400
    ncti_key_shift = ncti_key_left_shift | ncti_key_right_shift
    ncti_key_control = ncti_key_left_control | ncti_key_right_control
    ncti_key_alt = ncti_key_left_alt | ncti_key_right_alt
    ncti_key_meta = ncti_key_left_meta | ncti_key_right_meta

    @staticmethod
    def hasCapsLock(modifiers):
        return modifiers & Modifiers.ncti_key_caps_lock.value != 0

    @staticmethod
    def hasNumLock(modifiers):
        return modifiers & Modifiers.ncti_key_num_lock.value != 0

    @staticmethod
    def hasScrollLock(modifiers):
        return modifiers & Modifiers.ncti_key_scroll_lock.value != 0

    @staticmethod
    def hasRightShift(modifiers):
        return modifiers & Modifiers.ncti_key_right_shift.value != 0

    @staticmethod
    def hasLeftShift(modifiers):
        return modifiers & Modifiers.ncti_key_left_shift.value != 0

    @staticmethod
    def hasRightControl(modifiers):
        return modifiers & Modifiers.ncti_key_right_control.value != 0

    @staticmethod
    def hasLeftControl(modifiers):
        return modifiers & Modifiers.ncti_key_left_control.value != 0

    @staticmethod
    def hasRightAlt(modifiers):
        return modifiers & Modifiers.ncti_key_right_alt.value != 0

    @staticmethod
    def hasLeftAlt(modifiers):
        return modifiers & Modifiers.ncti_key_left_alt.value != 0

    @staticmethod
    def hasRightMeta(modifiers):
        return modifiers & Modifiers.ncti_key_right_meta.value != 0

    @staticmethod
    def hasLeftMeta(modifiers):
        return modifiers & Modifiers.ncti_key_left_meta.value != 0

    @staticmethod
    def hasShift(modifiers):
        return modifiers & Modifiers.ncti_key_shift.value != 0

    @staticmethod
    def hasControl(modifiers):
        return modifiers & Modifiers.ncti_key_control.value != 0

    @staticmethod
    def hasAlt(modifiers):
        return modifiers & Modifiers.ncti_key_alt.value != 0

    @staticmethod
    def hasMeta(modifiers):
        return modifiers & Modifiers.ncti_key_meta.value != 0


class MouseEventDelegate:
    def __init__(self):
        self.NCTI = None
        self.doc = None
        self.view = None
        self.name = None
        self.renderOperator = None
        self.on_double_click_response = None
        self.on_right_mouse_down_response = None
        self.on_right_mouse_double_click_response = None
        self.on_click_response = None
        self.on_mouse_move_response = None

        self._isMiddleButtonDown = False
        self._isRightButtonDown = False
        self._callLater = None

    def install(self, NCTI, doc, view, name):
        self.uninstall()
        self.NCTI = NCTI
        self.doc = doc
        self.view = view
        self.name = name
        self.renderOperator = self.NCTI.RenderOperator(doc, view)
        if self.renderOperator:
            self.renderOperator.OnMouseDown(self.onMouseDown)
            self.renderOperator.OnMouseUp(self.onMouseUp)
            self.renderOperator.OnMouseMove(self.onMouseMove)
            self.renderOperator.OnMouseWheel(self.onMouseWheel)
        else:
            import sys
            sys.stderr.write(f"Failed to get RenderOperator for view {self.view} and name {self.name}\n")

    def uninstall(self):
        if self.renderOperator:
            self.renderOperator = None
            self.name = None
            self.doc = None
            self.view = None
            self.NCTI = None

    def onMouseDown(self, event):
        currentButtons = event['CurrentButtons']
        if Buttons.hasLeft(currentButtons):
            if event["ClickCount"] >= 2:
                self.on_double_click_response()
            else:
                self.on_click_response()
        if Buttons.hasRight(currentButtons):
            self._isRightButtonDown = True
            if self.on_right_mouse_down_response:
                self.on_right_mouse_down_response()
        if Buttons.hasMiddle(currentButtons):
            self._isMiddleButtonDown = True
            if event['ClickCount'] >= 2:
                if self.on_right_mouse_double_click_response:
                    self.on_right_mouse_double_click_response()
        return True

    def onMouseUp(self, event):
        currentButtons = event['CurrentButtons']
        if Buttons.hasRight(currentButtons):
            self._isRightButtonDown = False
        if Buttons.hasMiddle(currentButtons):
            self._isMiddleButtonDown = False
        return True

    def onMouseMove(self, event):
        self._isMoved = True
        if self._isRightButtonDown or self._isMiddleButtonDown:
            if self.on_mouse_move_response:
                self.on_mouse_move_response()
        return True

    def onMouseWheel(self, event):
        return True

