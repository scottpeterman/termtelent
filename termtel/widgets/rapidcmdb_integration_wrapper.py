import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtWebChannel import QWebChannel

from termtel.termtel import logger
from termtel.widgets.terminal_app_wrapper import GenericTabContainer


class RapidCMDBWrapper:
    """Wrapper class to standardize cmdb interface"""

    def __init__(self, cmdb_widget):
        self.cmdb = cmdb_widget
        self.channel = QWebChannel()


    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.cmdb, 'cleanup'):
            self.cmdb.cleanup()
        # Make sure to stop any running cmdb loops
        if hasattr(self.cmdb, 'cmdbView'):
            if hasattr(self.cmdb.cmdbView, 'timer'):
                self.cmdb.cmdbView.timer.stop()

#
# def create_cmdb_tab(self, title: str = "Asteroids") -> str:
#     """Create a new cmdb tab"""
#     try:
#         # Generate unique ID for the tab
#         tab_id = str(uuid.uuid4())
#
#         # Create cmdb widget with appropriate theme color
#         from termtel.widgets.space_debris import AsteroidsWidget
#         theme_colors = self.parent.theme_manager.get_colors(self.parent.theme)
#         cmdb_color = theme_colors.get('text', Qt.GlobalColor.white)
#         cmdb = AsteroidsWidget(color=cmdb_color,parent=self.parent)
#
#         # Create wrapper and container
#         wrapper = RapidCMDBWrapper(cmdb)
#         container = GenericTabContainer(cmdb, wrapper, self)
#
#         # Add to tab widget
#         index = self.addTab(container, title)
#         self.setCurrentIndex(index)
#
#         # Store in sessions
#         self.sessions[tab_id] = container
#         return tab_id
#
#     except Exception as e:
#         logger.error(f"Failed to create cmdb tab: {e}")
#         raise