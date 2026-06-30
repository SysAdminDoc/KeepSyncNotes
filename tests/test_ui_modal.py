import unittest

from keepsync_ui_modal import configure_modal_dialog


class FakeWidget:
    def __init__(self):
        self.focused = False
        self.force_focused = False
        self.exists = True

    def focus_set(self):
        self.focused = True

    def focus_force(self):
        self.force_focused = True

    def winfo_exists(self):
        return self.exists


class FakeParent:
    def __init__(self, focused_widget):
        self.focused_widget = focused_widget

    def focus_get(self):
        return self.focused_widget


class FakeDialog(FakeWidget):
    def __init__(self):
        super().__init__()
        self.transient_parent = None
        self.grabbed = False
        self.protocol_handlers = {}
        self.bindings = {}
        self.destroyed = False

    def transient(self, parent):
        self.transient_parent = parent

    def grab_set(self):
        self.grabbed = True

    def protocol(self, name, handler):
        self.protocol_handlers[name] = handler

    def bind(self, event, handler):
        self.bindings[event] = handler

    def after(self, _delay_ms, callback):
        callback()

    def destroy(self):
        self.destroyed = True


class ModalHelperTests(unittest.TestCase):
    def test_configures_modal_focus_escape_close_and_focus_return(self):
        return_focus = FakeWidget()
        parent = FakeParent(return_focus)
        dialog = FakeDialog()
        initial_focus = FakeWidget()

        configure_modal_dialog(dialog, parent, initial_focus=initial_focus)

        self.assertIs(dialog.transient_parent, parent)
        self.assertTrue(dialog.grabbed)
        self.assertIn("WM_DELETE_WINDOW", dialog.protocol_handlers)
        self.assertIn("<Escape>", dialog.bindings)
        self.assertTrue(initial_focus.focused)
        self.assertTrue(initial_focus.force_focused)

        dialog.bindings["<Escape>"]()

        self.assertTrue(dialog.destroyed)
        self.assertTrue(return_focus.focused)

    def test_close_callback_can_cancel_without_destroying_dialog(self):
        parent = FakeParent(FakeWidget())
        dialog = FakeDialog()
        cancelled = []

        configure_modal_dialog(dialog, parent, on_close=lambda: cancelled.append(True))

        result = dialog.protocol_handlers["WM_DELETE_WINDOW"]()

        self.assertEqual(result, "break")
        self.assertEqual(cancelled, [True])
        self.assertFalse(dialog.destroyed)


if __name__ == "__main__":
    unittest.main()
