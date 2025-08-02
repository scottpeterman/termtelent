from PyQt6.QtWidgets import QWidget, QVBoxLayout


class TextEditorWrapper:
    """Wrapper class to standardize text editor interface"""

    def __init__(self, editor):
        self.editor = editor

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.editor, 'cleanup'):
            self.editor.cleanup()


class GenericTabContainer(QWidget):
    """Container for tabs that maintains consistent interface"""

    def __init__(self, widget, wrapper, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.wrapper = wrapper
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)

    def cleanup(self):
        """Cleanup method called when tab is closed"""
        if self.wrapper:
            self.wrapper.cleanup()