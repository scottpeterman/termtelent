"""
Theme bridge for communicating between Qt application and RapidCMDB web views
"""

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


class ThemeBridge(QObject):
    """Bridge object to communicate theme changes to web views"""

    # Signal to notify web views of theme changes
    theme_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.current_theme = "cyberpunk"  # Default theme

    @pyqtSlot(str)
    def set_theme(self, theme_name):
        """Set the current theme and notify all web views"""
        self.current_theme = theme_name
        print(f"ThemeBridge: Setting theme to {theme_name}")
        self.theme_changed.emit(theme_name)

    @pyqtSlot(result=str)
    def get_current_theme(self):
        """Get the current theme name"""
        return self.current_theme

    @pyqtSlot(str)
    def notify_theme_change(self, theme_name):
        """Public method to notify theme changes from Qt side"""
        self.set_theme(theme_name)