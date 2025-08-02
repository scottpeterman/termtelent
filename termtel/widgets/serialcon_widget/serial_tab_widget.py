from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt
import uuid
import logging
import os

# Import your existing UI_SerialWidget and SerialBackend
from termtel.widgets.serialcon_widget.Library.serialshell import SerialBackend
from termtel.widgets.serialcon_widget.serialcon_widget import Ui_SerialWidget

logger = logging.getLogger('termtel.serialcon_widget')


class SerialTerminalWidget(QWidget):
    """A serial terminal widget with theme support and tab integration"""

    # Signal when connection status changes
    connection_changed = pyqtSignal(bool, str)

    def __init__(self, parent=None, theme_library=None, current_theme="cyberpunk"):
        super().__init__(parent)
        self.parent = parent
        self.theme_library = theme_library
        self.current_theme = current_theme
        self.setup_ui()

    def setup_ui(self):
        """Set up the UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create the serial widget

        # Create the serial widget with theme support
        self.serial_widget = Ui_SerialWidget(
            theme_library=self.theme_library,
            current_theme=self.current_theme,
            parent=self
        )

        # Connect signals
        if hasattr(self.serial_widget, 'backend') and hasattr(self.serial_widget.backend, 'connection_changed'):
            self.serial_widget.backend.connection_changed.connect(self.on_connection_changed)

        # Add widget to layout
        layout.addWidget(self.serial_widget)

    def on_connection_changed(self, connected, info):
        """Handle connection status changes"""
        # Forward the signal
        self.connection_changed.emit(connected, info)

        # Update tab title if possible
        self.update_tab_title(connected, info)

    def update_tab_title(self, connected, info):
        """Update the tab title to reflect connection status"""
        try:
            # Find the tab widget and the index of this widget
            from PyQt6.QtWidgets import QTabWidget
            parent = self.parent
            while parent is not None:
                if isinstance(parent, QTabWidget):
                    for i in range(parent.count()):
                        if parent.widget(i) == self or parent.widget(i).findChild(SerialTerminalWidget) == self:
                            current_title = parent.tabText(i)

                            # Update title based on connection status
                            if connected:
                                if ':' in current_title:
                                    base_title = current_title.split(':')[0].strip()
                                else:
                                    base_title = current_title

                                # Show port in title if it's in the info
                                if hasattr(self.serial_widget.backend, 'port') and self.serial_widget.backend.port:
                                    parent.setTabText(i, f"{base_title}: {self.serial_widget.backend.port}")
                                else:
                                    parent.setTabText(i, f"{base_title}: Connected")
                            else:
                                if ':' in current_title:
                                    base_title = current_title.split(':')[0].strip()
                                    parent.setTabText(i, base_title)
                            break
                    break
                parent = parent.parent()
        except Exception as e:
            logger.warning(f"Failed to update tab title: {e}")

    def apply_theme(self, theme_manager, theme_name):
        """Apply theme to the widget"""
        if hasattr(self, 'serial_widget') and hasattr(self.serial_widget, 'set_theme'):
            self.serial_widget.set_theme(theme_name)
        elif hasattr(self, 'serial_widget') and hasattr(self.serial_widget, 'view'):
            # Apply theme directly to the view
            try:
                theme = theme_manager.get_theme(theme_name)
                if theme:
                    js_code = theme_manager.generate_terminal_js(theme)
                    self.serial_widget.view.page().runJavaScript(js_code)
            except Exception as e:
                logger.error(f"Error applying theme to serial terminal: {e}")

    def cleanup(self):
        """Clean up resources when the widget is closed"""
        try:
            if hasattr(self, 'serial_widget') and hasattr(self.serial_widget, 'cleanup'):
                self.serial_widget.cleanup()
            elif hasattr(self, 'serial_widget') and hasattr(self.serial_widget, 'backend'):
                if hasattr(self.serial_widget.backend, 'disconnect'):
                    self.serial_widget.backend.disconnect()
        except Exception as e:
            logger.error(f"Error during serial widget cleanup: {e}")