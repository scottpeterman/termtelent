# widgets/terminal_tabs.py
import profile
import socket
import traceback
from importlib.resources import files
from pathlib import Path

from PyQt6.QtGui import QColor
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWidgets import (QTabWidget, QWidget, QVBoxLayout,
                             QMenu, QMessageBox, QSplitter, QSizePolicy)
from PyQt6.QtCore import QUrl, pyqtSignal, Qt, QTimer
import uuid
import logging
from typing import Dict, Optional, Tuple

from termtel.helpers.theme_bridge import ThemeBridge
from termtel.themes2 import terminal_themes
from termtel.themes3 import ThemeMapper, generate_terminal_themes
from termtel.widgets import download_handler
from termtel.widgets.diff_tool_widget import DiffToolWidget, DiffToolWrapper
from termtel.widgets.notepad_widget import NotepadWidget
from termtel.widgets.qtssh_widget import Ui_Terminal
from termtel.widgets.terminal_app_wrapper import TextEditorWrapper, GenericTabContainer
from termtel.widgets.serialcon_widget.serialcon_widget import SerialWidgetWrapper as SerialTerminalWidget

logger = logging.getLogger(__name__)


class SerialTerminalWrapper:
    """Wrapper class to standardize serial terminal interface"""

    def __init__(self, terminal_widget):
        self.terminal = terminal_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.terminal, 'cleanup'):
            self.terminal.cleanup()
        elif hasattr(self.terminal, 'backend') and hasattr(self.terminal.backend, 'disconnect'):
            # Try to disconnect the serial backend
            try:
                self.terminal.backend.disconnect()
            except Exception as e:
                print(f"Error disconnecting serial: {e}")


class NapalmWrapper:
    """Wrapper class to standardize NAPALM widget interface"""

    def __init__(self, napalm_widget):
        self.napalm = napalm_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.napalm, 'cleanup'):
            self.napalm.cleanup()

        # Cancel any running NAPALM operations
        if hasattr(self.napalm, 'current_operation') and self.napalm.current_operation:
            try:
                self.napalm.cancel_operation()
            except Exception as e:
                logger.warning(f"Error cancelling NAPALM operation: {e}")

    def apply_theme(self, theme_manager, theme_name):
        """Apply theme to the NAPALM widget"""
        try:
            if hasattr(self.napalm, 'set_theme_from_parent'):
                self.napalm.set_theme_from_parent(theme_name)
            elif hasattr(self.napalm, 'apply_theme'):
                self.napalm.apply_theme(theme_name)
            else:
                # Fallback to theme manager direct application
                theme_manager.apply_theme(self.napalm, theme_name)
        except Exception as e:
            logger.warning(f"Could not apply theme to NAPALM widget: {e}")



class GameWrapper:
    """Wrapper class to standardize game interface"""

    def __init__(self, game_widget):
        self.game = game_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.game, 'cleanup'):
            self.game.cleanup()
        # Make sure to stop any running game loops
        if hasattr(self.game, 'gameView'):
            if hasattr(self.game.gameView, 'timer'):
                self.game.gameView.timer.stop()
class TerminalTabWidget(QTabWidget):
    """Widget managing multiple terminal tabs."""
    terminal_closed = pyqtSignal(str)  # Signal when a terminal is closed
    all_terminals_closed = pyqtSignal()  # Signal when all terminals are closed

    def __init__(self, server_port: int, parent=None):
        super().__init__(parent)
        self.server_port = server_port
        self.sessions: Dict[str, QWidget] = {}
        self.parent = parent
        self.current_term_theme = "Cyberpunk"  # Default
        if hasattr(self.parent, 'theme'):
            self.current_term_theme = self.parent.theme
        self.terminal_themes = generate_terminal_themes(self.parent.theme_manager)

        self.setup_ui()

    def create_cmdb_tab(self, title: str = "RapidCMDB") -> str:
        try:
            tab_id = str(uuid.uuid4())

            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEngineDownloadRequest
            from PyQt6.QtCore import QUrl, QStandardPaths
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            import os
            from datetime import datetime

            # Get or create profile (don't use setProfile)
            profile = QWebEngineProfile.defaultProfile()

            # Enable settings on the profile
            settings = profile.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)

            # Create WebView normally
            web_view = QWebEngineView()
            web_view.setZoomFactor(.8)

            # Download handler function
            def handle_download(download_request: QWebEngineDownloadRequest):
                print(f"Download requested: {download_request.url().toString()}")
                print(f"Suggested filename: {download_request.suggestedFileName()}")
                print(f"MIME type: {download_request.mimeType()}")

                # Get suggested filename or create one
                suggested_filename = download_request.suggestedFileName()
                if not suggested_filename:
                    # Extract from URL and create appropriate filename
                    url_str = download_request.url().toString()
                    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

                    if 'drawio' in url_str:
                        suggested_filename = f"topology-{timestamp}.drawio"
                    elif 'json' in url_str:
                        suggested_filename = f"topology-{timestamp}.json"
                    elif 'svg' in url_str:
                        suggested_filename = f"topology-{timestamp}.svg"
                    else:
                        suggested_filename = f"download-{timestamp}.txt"

                # Get Downloads folder
                downloads_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
                if not downloads_path:
                    downloads_path = os.path.expanduser("~/Downloads")

                # Show save dialog
                full_path = os.path.join(downloads_path, suggested_filename)
                file_path, _ = QFileDialog.getSaveFileName(
                    web_view,
                    "Save Downloaded File",
                    full_path,
                    "All Files (*.*)"
                )

                if file_path:
                    print(f"Saving to: {file_path}")

                    # Set download path
                    download_request.setDownloadDirectory(os.path.dirname(file_path))
                    download_request.setDownloadFileName(os.path.basename(file_path))

                    # Accept the download
                    download_request.accept()

                else:
                    # User cancelled the save dialog
                    print("Download cancelled by user")
                    download_request.cancel()

            # Connect download handler to the default profile
            profile.downloadRequested.connect(handle_download)

            # Get current theme from parent and set URL with theme parameter
            current_theme = getattr(self.parent, 'theme', 'cyberpunk')
            url = QUrl(f"http://127.0.0.1:5000/?theme={current_theme}")
            web_view.setUrl(url)

            # Create wrapper with parent window reference
            wrapper = CMDBWrapper(web_view, self.parent)
            container = GenericTabContainer(web_view, wrapper, self)

            index = self.addTab(container, title)
            self.setCurrentIndex(index)

            self.sessions[tab_id] = container

            # Store wrapper for theme updates
            if not hasattr(self, 'cmdb_wrappers'):
                self.cmdb_wrappers = []
            self.cmdb_wrappers.append(wrapper)

            return tab_id

        except Exception as e:
            logger.error(f"Failed to create CMDB tab: {e}")
            raise

    def create_fingerprint_editor_tab(self, title: str = "Vendor Fingerprint Editor") -> str:
        """Create a new vendor fingerprint editor tab with full theme support"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Import and create fingerprint editor widget
            from termtel.widgets.fingerprint_widget import VendorFingerprintEditor

            # Create editor widget with current theme and proper sizing
            editor_widget = VendorFingerprintEditor(
                parent=self.parent,
                theme_manager=getattr(self.parent, 'theme_manager', None)
            )
            editor_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Apply current theme if available
            if hasattr(self.parent, 'theme_manager') and hasattr(self.parent, 'theme'):
                current_theme = self.parent.theme
                try:
                    editor_widget.apply_theme(self.parent.theme_manager, current_theme)
                    logger.debug(f"Applied initial theme {current_theme} to vendor fingerprint editor")
                except Exception as e:
                    logger.warning(f"Could not apply initial theme to vendor fingerprint editor: {e}")

            # Create wrapper and container
            from termtel.widgets.fingerprint_widget import VendorFingerprintWrapper
            wrapper = VendorFingerprintWrapper(editor_widget)
            container = GenericTabContainer(editor_widget, wrapper, self)
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Store wrapper reference on container for theme updates
            container.wrapper = wrapper

            # Ensure the container layout uses full space
            if hasattr(container, 'layout') and container.layout():
                container.layout().setContentsMargins(0, 0, 0, 0)

            # Add to tab widget with icon if available
            from PyQt6.QtGui import QIcon
            icon_path = Path(__file__).parent.parent / 'icons' / 'fingerprint-editor.svg'

            if icon_path.exists():
                tab_icon = QIcon(str(icon_path))
                index = self.addTab(container, tab_icon, title)
            else:
                index = self.addTab(container, title)

            self.setTabToolTip(index, "Edit vendor fingerprint YAML configurations")
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container

            # Store a reference to update the theme later if needed
            if not hasattr(self, 'theme_aware_widgets'):
                self.theme_aware_widgets = []
            self.theme_aware_widgets.append(editor_widget)

            logger.info(f"Created vendor fingerprint editor tab with theme support")
            return tab_id

        except Exception as e:
            logger.error(f"Failed to create vendor fingerprint editor tab: {e}")
            import traceback
            traceback.print_exc()

            # Show error dialog
            QMessageBox.critical(
                self.parent,
                "Fingerprint Editor Error",
                f"Failed to create vendor fingerprint editor tab:\n{str(e)}"
            )
            return None

    def create_cmdb_import_tab(self, title: str = "CMDB Scanner Import") -> str:
        """Create a new CMDB scanner import tab with full theme support"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Import and create CMDB import widget
            from termtel.import_scan_ui import CMDBImportWidget

            # Create import widget with current theme and proper sizing
            import_widget = CMDBImportWidget(
                parent=self.parent,
                theme_manager=self.parent.theme_manager
            )
            import_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Apply current theme if available
            if hasattr(self.parent, 'theme_manager') and hasattr(self.parent, 'theme'):
                current_theme = self.parent.theme
                try:
                    import_widget.current_theme = current_theme
                    import_widget.apply_theme()
                    logger.debug(f"Applied initial theme {current_theme} to CMDB import widget")
                except Exception as e:
                    logger.warning(f"Could not apply initial theme to CMDB import widget: {e}")

            # Create wrapper and container
            wrapper = CMDBImportWrapper(import_widget)
            container = GenericTabContainer(import_widget, wrapper, self)
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Store wrapper reference on container for theme updates
            container.wrapper = wrapper

            # Ensure the container layout uses full space
            if hasattr(container, 'layout') and container.layout():
                container.layout().setContentsMargins(0, 0, 0, 0)

            # Add to tab widget with icon if available
            from PyQt6.QtGui import QIcon
            icon_path = Path(__file__).parent.parent / 'icons' / 'database-import.svg'

            if icon_path.exists():
                tab_icon = QIcon(str(icon_path))
                index = self.addTab(container, tab_icon, title)
            else:
                index = self.addTab(container, title)

            self.setTabToolTip(index, "CMDB Scanner Data Import Tool")
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container

            # Store a reference to update the theme later if needed
            if not hasattr(self, 'theme_aware_widgets'):
                self.theme_aware_widgets = []
            self.theme_aware_widgets.append(import_widget)

            logger.info(f"Created CMDB scanner import tab with theme support")
            return tab_id

        except Exception as e:
            logger.error(f"Failed to create CMDB import tab: {e}")
            import traceback
            traceback.print_exc()

            # Show error dialog
            QMessageBox.critical(
                self.parent,
                "CMDB Import Error",
                f"Failed to create CMDB scanner import tab:\n{str(e)}"
            )
            return None
    def create_napalm_tab(self, title: str = "NAPALM Tester") -> str:
        """Create a new NAPALM testing tab with full theme support"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Import and create NAPALM widget
            from termtel.widgets.napalm_util import NapalmWidget

            # Create NAPALM widget with current theme
            napalm_widget = NapalmWidget(
                parent=self.parent,
                theme_manager=getattr(self.parent, 'theme_manager', None),
                theme_name=getattr(self.parent, 'theme', 'cyberpunk')
            )

            # Set appropriate size policy
            napalm_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Apply current theme if available
            if hasattr(self.parent, 'theme_manager') and hasattr(self.parent, 'theme'):
                current_theme = self.parent.theme
                try:
                    napalm_widget.set_theme_from_parent(current_theme)
                    logger.debug(f"Applied initial theme {current_theme} to NAPALM widget")
                except Exception as e:
                    logger.warning(f"Could not apply initial theme to NAPALM widget: {e}")

            # Create wrapper and container
            wrapper = NapalmWrapper(napalm_widget)
            container = GenericTabContainer(napalm_widget, wrapper, self)
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Store wrapper reference on container for theme updates
            container.wrapper = wrapper

            # Ensure the container layout uses full space
            if hasattr(container, 'layout') and container.layout():
                container.layout().setContentsMargins(0, 0, 0, 0)

            # Add to tab widget with icon if available
            from PyQt6.QtGui import QIcon
            icon_path = Path(__file__).parent.parent / 'icons' / 'napalm.svg'

            if icon_path.exists():
                tab_icon = QIcon(str(icon_path))
                index = self.addTab(container, tab_icon, title)
            else:
                index = self.addTab(container, title)

            self.setTabToolTip(index, "NAPALM Device Testing and Validation")
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container

            # Store a reference to update the theme later if needed
            if not hasattr(self, 'theme_aware_widgets'):
                self.theme_aware_widgets = []
            self.theme_aware_widgets.append(napalm_widget)

            # Store reference for parent window theme updates
            if not hasattr(self.parent, 'napalm_widgets'):
                self.parent.napalm_widgets = []
            self.parent.napalm_widgets.append(napalm_widget)

            logger.info(f"Created NAPALM testing tab with theme support")
            return tab_id

        except Exception as e:
            logger.error(f"Failed to create NAPALM tab: {e}")
            import traceback
            traceback.print_exc()

            # Show error dialog
            QMessageBox.critical(
                self.parent,
                "NAPALM Error",
                f"Failed to create NAPALM testing tab:\n{str(e)}"
            )
            return None

    # Alternative: Manual download handler using navigation interception
    def create_cmdb_tab_manual_downloads(self, title: str = "RapidCMDB") -> str:
        """Alternative with manual download handling if the above doesn't work"""
        try:
            tab_id = str(uuid.uuid4())

            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
            from PyQt6.QtCore import QUrl, QStandardPaths, QThread, pyqtSignal, QNetworkRequest
            from PyQt6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
            from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply
            import os
            from datetime import datetime

            # Enable local file access
            profile = QWebEngineProfile.defaultProfile()
            settings = profile.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)

            web_view = QWebEngineView()
            web_view.setZoomFactor(.8)

            # Create network manager for manual downloads
            network_manager = QNetworkAccessManager()

            # Navigation interceptor
            def handle_navigation_request(navigation_request):
                url = navigation_request.navigatedUrl()
                url_str = url.toString()

                print(f"Navigation requested to: {url_str}")

                # Check if this is a download URL
                if '/api/topology/export/' in url_str:
                    print(f"Intercepting download URL: {url_str}")

                    # Determine file type and extension
                    if 'drawio' in url_str:
                        ext = '.drawio'
                        file_filter = 'Draw.io Files (*.drawio);;All Files (*.*)'
                    elif 'json' in url_str:
                        ext = '.json'
                        file_filter = 'JSON Files (*.json);;All Files (*.*)'
                    elif 'svg' in url_str:
                        ext = '.svg'
                        file_filter = 'SVG Files (*.svg);;All Files (*.*)'
                    else:
                        ext = '.txt'
                        file_filter = 'All Files (*.*)'

                    # Generate default filename
                    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                    default_filename = f"topology-{timestamp}{ext}"

                    # Get Downloads folder
                    downloads_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
                    if not downloads_path:
                        downloads_path = os.path.expanduser("~/Downloads")

                    # Show save dialog
                    full_path = os.path.join(downloads_path, default_filename)
                    file_path, _ = QFileDialog.getSaveFileName(
                        web_view,
                        "Save Export File",
                        full_path,
                        file_filter
                    )

                    if file_path:
                        print(f"Downloading to: {file_path}")

                        # Create progress dialog
                        progress_dialog = QProgressDialog("Downloading file...", "Cancel", 0, 100, web_view)
                        progress_dialog.setWindowTitle("Download Progress")
                        progress_dialog.setModal(True)
                        progress_dialog.show()

                        # Start download
                        request = QNetworkRequest(url)
                        reply = network_manager.get(request)

                        def on_download_progress(bytes_received, bytes_total):
                            if bytes_total > 0:
                                progress = int((bytes_received / bytes_total) * 100)
                                progress_dialog.setValue(progress)
                                print(f"Download progress: {progress}%")

                        def on_cancel():
                            reply.abort()
                            progress_dialog.close()

                        progress_dialog.canceled.connect(on_cancel)

                    # Reject the navigation to prevent normal page load
                    navigation_request.reject()
                    return

                # Allow normal navigation for other URLs
                navigation_request.accept()

            # Connect navigation interceptor
            web_view.page().navigationRequested.connect(handle_navigation_request)

            # Get current theme from parent and set URL with theme parameter
            current_theme = getattr(self.parent, 'theme', 'cyberpunk')
            url = QUrl(f"http://127.0.0.1:{self.parent.port}/network/enhanced?theme={current_theme}")
            web_view.setUrl(url)

            # Create wrapper with parent window reference
            wrapper = CMDBWrapper(web_view, self.parent)
            container = GenericTabContainer(web_view, wrapper, self)

            index = self.addTab(container, title)
            self.setCurrentIndex(index)

            self.sessions[tab_id] = container

            # Store wrapper for theme updates
            if not hasattr(self, 'cmdb_wrappers'):
                self.cmdb_wrappers = []
            self.cmdb_wrappers.append(wrapper)

            return tab_id

        except Exception as e:
            logger.error(f"Failed to create CMDB tab: {e}")
            raise
    # def create_cmdb_tab(self, title: str = "RapidCMDB") -> str:
    #     try:
    #         tab_id = str(uuid.uuid4())
    #
    #         from PyQt6.QtWebEngineWidgets import QWebEngineView
    #         from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile
    #         from PyQt6.QtCore import QUrl
    #
    #         # Enable local file access
    #         profile = QWebEngineProfile.defaultProfile()
    #         settings = profile.settings()
    #         settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    #         settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
    #         settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
    #         settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
    #
    #         web_view = QWebEngineView()
    #         web_view.setZoomFactor(.8)
    #
    #         # Get current theme from parent and set URL with theme parameter
    #         current_theme = getattr(self.parent, 'theme', 'cyberpunk')
    #         url = QUrl(f"http://127.0.0.1:5000?theme={current_theme}")
    #         web_view.setUrl(url)
    #
    #         # Create wrapper with parent window reference
    #         wrapper = CMDBWrapper(web_view, self.parent)
    #         container = GenericTabContainer(web_view, wrapper, self)
    #
    #         index = self.addTab(container, title)
    #         self.setCurrentIndex(index)
    #
    #         self.sessions[tab_id] = container
    #
    #         # Store wrapper for theme updates
    #         if not hasattr(self, 'cmdb_wrappers'):
    #             self.cmdb_wrappers = []
    #         self.cmdb_wrappers.append(wrapper)
    #
    #         return tab_id
    #
    #     except Exception as e:
    #         logger.error(f"Failed to create CMDB tab: {e}")
    #         raise

    # Add this method to your TerminalTabWidget class
    def create_telemetry_tab(self, tab_name="Telemetry"):
        """Create a new telemetry tab"""
        try:
            # Create the path to frontend files
            frontend_path = Path(__file__).parent.parent / 'termtelng' / 'frontend'

            # Create the telemetry widget
            from termtel.termtelwidgets.telemetry_widget import TelemetryWidget
            telemetry_widget = TelemetryWidget(parent=self.parent)

            # Connect cleanup signal
            # telemetry_widget.cleanup_requested.connect(self.parent.handle_telemetry_cleanup)

            # Add tab with an icon if available
            from PyQt6.QtGui import QIcon
            icon_path = Path(__file__).parent.parent / 'termtelng' / 'frontend' / 'radar.svg'

            if icon_path.exists():
                tab_icon = QIcon(str(icon_path))
                index = self.addTab(telemetry_widget, tab_icon, tab_name)
            else:
                index = self.addTab(telemetry_widget, tab_name)

            self.setTabToolTip(index, "Terminal Telemetry Dashboard")
            self.setCurrentIndex(index)  # Switch to the new tab

            # Apply current theme
            if hasattr(telemetry_widget, 'set_theme_from_parent') and hasattr(self.parent, 'theme'):
                telemetry_widget.set_theme_from_parent(self.parent.theme)

            # Store reference for cleanup
            if not hasattr(self.parent, 'telemetry_widgets'):
                self.parent.telemetry_widgets = []
            self.parent.telemetry_widgets.append(telemetry_widget)

            return telemetry_widget

        except Exception as e:
            logger.error(f"Failed to create telemetry tab: {e}")
            traceback.print_exc()
            return None
    def get_mapped_terminal_theme(self, pyqt_theme: str) -> str:
        """Map PyQt theme names to terminal theme names."""
        theme_mapping = {
            "cyberpunk": "Cyberpunk",
            "dark_mode": "Dark",
            "light_mode": "Light",
            "retro_green": "Green",
            "retro_amber": "Amber",
            "neon_blue": "Neon"
        }
        return theme_mapping.get(pyqt_theme.lower(), "Cyberpunk")

    def setup_ui(self):
        """Initialize the tab widget UI."""
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setUsesScrollButtons(True)

        # Connect signals
        self.tabCloseRequested.connect(self.close_tab)

        # Set up context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def update_theme(self, theme_name: str):
        """Update terminal themes."""
        terminal_theme = self.get_mapped_terminal_theme(theme_name)
        self.current_term_theme = terminal_theme

        # Update all terminal instances
        for i in range(self.count()):
            tab = self.widget(i)
            if tab:
                terminal = tab.findChild(Ui_Terminal)
                if terminal:
                    self.apply_theme_to_terminal(terminal, theme_name)


    def test_socket_connection(self, host: str, port: str, timeout: int = 5) -> Tuple[bool, Optional[str]]:
        """Test if a socket connection can be established to the given host and port."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, int(port)))
            return True, None
        except socket.timeout:
            return False, "Connection timed out after 5 seconds"
        except ConnectionRefusedError:
            return False, "Connection refused - service may not be running on the specified port"
        except socket.gaierror:
            return False, "Could not resolve hostname"
        except ValueError:
            return False, "Invalid port number"
        except Exception as e:
            return False, str(e)
        finally:
            sock.close()



    def create_serial_terminal_tab(self, title: str = "Serial Terminal") -> str:
        """Create a new serial terminal tab"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Import the Ui_SerialWidget class from your existing implementation
            from termtel.widgets.serialcon_widget.serialcon_widget import Ui_SerialWidget

            # Create serial terminal widget with current theme
            serial_terminal = Ui_SerialWidget(
                theme_library=self.parent.theme_manager,
                current_theme=self.parent.theme,
                parent=self
            )

            # Create wrapper and container
            from termtel.widgets.serialcon_widget.serial_terminal_wrapper import SerialTerminalWrapper
            wrapper = SerialTerminalWrapper(serial_terminal)
            container = GenericTabContainer(serial_terminal, wrapper, self)

            # Add to tab widget
            index = self.addTab(container, title)
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container

            # Store a reference to update the theme later if needed
            if not hasattr(self, 'theme_aware_widgets'):
                self.theme_aware_widgets = []
            self.theme_aware_widgets.append(serial_terminal)

            return tab_id

        except Exception as e:
            logger.error(f"Failed to create serial terminal: {e}")
            import traceback
            traceback.print_exc()
            raise

    def create_terminal(self, connection_data: Dict) -> str:
        """Create a new terminal tab."""
        session_id = connection_data.get('uuid', str(uuid.uuid4()))

        try:
            # Test socket connection first
            host = connection_data['host']
            port = connection_data.get('port', '22')

            success, error_message = self.test_socket_connection(host, port)
            if not success:
                QMessageBox.critical(
                    self,
                    "Connection Failed",
                    f"Failed to connect to {host}:{port}\nError: {error_message}"
                )
                return None

            # Create tab container
            tab_container = QWidget()
            layout = QVBoxLayout(tab_container)
            layout.setContentsMargins(0, 0, 0, 0)

            # Create Ui_Terminal instance
            hostinfo = {
                "host": connection_data['host'],
                "port": connection_data.get('port', '22'),
                "username": connection_data.get('username'),
                "password": connection_data.get('password'),
                "log_filename": f"./logs/session_{connection_data['host']}.log",
                "theme": self.get_mapped_terminal_theme(self.current_term_theme)
            }

            terminal = Ui_Terminal(hostinfo, parent=tab_container)
            layout.addWidget(terminal)

            # Theme will be applied when terminal is ready
            if hasattr(terminal, 'view'):
                self.apply_theme_to_terminal(terminal, self.current_term_theme)

            # Add to tab widget
            display_name = connection_data.get('display_name') or connection_data['host']
            index = self.addTab(tab_container, display_name)
            self.setCurrentIndex(index)

            # Store session
            self.sessions[session_id] = tab_container
            return session_id

        except Exception as e:
            logger.error(f"Failed to create terminal: {e}")
            raise

    def apply_theme_to_terminal(self, terminal, theme_name):
        """Apply theme to a specific terminal instance."""
        if hasattr(terminal, 'view') and theme_name in self.terminal_themes:
            js_code = self.terminal_themes[theme_name]["js"]
            try:
                terminal.view.page().runJavaScript(
                    "typeof term !== 'undefined' && term !== null",
                    lambda result: self.handle_theme_check(result, terminal, js_code)
                )
            except Exception as e:
                traceback.print_exc()
    def handle_theme_check(self, is_ready: bool, terminal, theme_js: str):
        """Handle the terminal readiness check for theme application."""
        if is_ready:
            terminal.view.page().runJavaScript(
                theme_js,
                lambda result: print(f"Theme applied successfully")
            )
        else:
            # Retry after a short delay
            QTimer.singleShot(1000, lambda: self.apply_theme_to_terminal(terminal, self.current_term_theme))

    def apply_theme_to_terminal(self, terminal, theme_name):
        """Apply theme to a specific terminal instance - restored original working version."""
        if hasattr(terminal, 'view') and theme_name in self.terminal_themes:
            js_code = self.terminal_themes[theme_name]["js"]
            try:
                terminal.view.page().runJavaScript(
                    "typeof term !== 'undefined' && term !== null",
                    lambda result: self.handle_theme_check(result, terminal, js_code)
                )
            except Exception as e:
                print(f"Error applying theme to terminal: {e}")
                traceback.print_exc()

    def handle_theme_check(self, is_ready: bool, terminal, theme_js: str):
        """Handle the terminal readiness check for theme application - restored original."""
        if is_ready:
            terminal.view.page().runJavaScript(
                theme_js,
                lambda result: print(f"Theme applied successfully")
            )
        else:
            # Retry after a short delay
            QTimer.singleShot(1000, lambda: self.apply_theme_to_terminal(terminal, self.current_term_theme))

    def change_single_terminal_theme(self, theme_name: str, tab_index: int):
        """Change theme for a specific terminal tab using dynamic theme system."""
        print(f"Changing theme for tab {tab_index} to {theme_name}")

        # Get the specific tab that was right-clicked
        tab = self.widget(tab_index)
        if tab:
            terminal = tab.findChild(Ui_Terminal)
            if terminal and hasattr(terminal, 'view'):
                # Use the dynamic theme system - get the generated JavaScript for this theme
                if theme_name in self.terminal_themes:
                    js_code = self.terminal_themes[theme_name]["js"]
                    try:
                        # Use a longer delay for individual tab theme changes
                        QTimer.singleShot(3000, lambda: terminal.view.page().runJavaScript(
                            "typeof term !== 'undefined' && term !== null",
                            lambda result: self.handle_single_theme_check(result, terminal, js_code, theme_name)
                        ))
                    except Exception as e:
                        print(f"Error applying theme to single terminal: {e}")
                else:
                    print(f"Theme '{theme_name}' not found in generated terminal_themes")
                    print(f"Available themes: {list(self.terminal_themes.keys())}")
            else:
                print(f"No terminal found in tab {tab_index}")

    def handle_single_theme_check(self, is_ready: bool, terminal, theme_js: str, theme_name: str):
        """Handle theme check for individual terminal theme changes."""
        if is_ready:
            try:
                terminal.view.page().runJavaScript(
                    theme_js,
                    lambda result: print(f"Single terminal theme '{theme_name}' applied successfully")
                )
            except Exception as e:
                print(f"Error executing single terminal theme JS: {e}")
        else:
            print(f"Single terminal not ready, retrying theme '{theme_name}' in 3 seconds...")
            QTimer.singleShot(3000, lambda: self.handle_single_theme_check(True, terminal, theme_js, theme_name))

    def cleanup(self):
        """
        Cleanup method to properly close the terminal and free resources.
        """
        try:
            # Disconnect the backend if it exists
            if hasattr(self, 'backend'):
                self.backend.disconnect()

            # Clear the web channel
            if hasattr(self, 'channel'):
                self.channel.deregisterObject(self.backend)

            # Clean up the web view
            if hasattr(self, 'view'):
                self.view.setPage(None)
                self.view.deleteLater()

            # Clean up the URL scheme handler
            if hasattr(self, 'handler'):
                QWebEngineProfile.defaultProfile().removeUrlSchemeHandler(self.handler)
                profile.downloadRequested.connect(download_handler.handle_download)

                self.handler.deleteLater()

        except Exception as e:
            print(f"Error during terminal cleanup: {e}")

    def remove_session(self, session_id: str):
        """Remove session from tracking."""
        if session_id in self.sessions:
            self.sessions.pop(session_id)
            self.terminal_closed.emit(session_id)
            if not self.sessions:
                self.all_terminals_closed.emit()

    def show_context_menu(self, position):
        index = self.tabBar().tabAt(position)
        if index >= 0:
            menu = QMenu(self)

            # Add theme submenu
            theme_menu = menu.addMenu("Terminal Theme")

            # Get available themes from the dynamic ThemeLibrary instead of hardcoded themes
            available_themes = self.parent.theme_manager.get_theme_names()

            # Create theme actions using the dynamic theme system
            for theme_name in available_themes:
                # Convert theme name to display name (e.g., "dark_mode" -> "Dark Mode")
                display_name = theme_name.replace('_', ' ').title()

                action = theme_menu.addAction(display_name)
                action.setCheckable(True)
                action.setChecked(theme_name == self.current_term_theme)
                # Pass the specific tab index to the theme change function
                action.triggered.connect(
                    lambda checked, tn=theme_name, tab_index=index: self.change_single_terminal_theme(tn, tab_index))

            menu.addSeparator()

            # ADD ONLY THIS: Rename tab action
            rename_action = menu.addAction("Rename Tab")
            rename_action.triggered.connect(lambda: self.rename_tab(index))

            menu.addSeparator()

            # Close action
            close_action = menu.addAction("Close")
            close_action.triggered.connect(lambda: self.close_tab(index))

            # Close others action
            close_others_action = menu.addAction("Close Others")
            close_others_action.triggered.connect(
                lambda: self.close_other_tabs(index)
            )

            # Close all action
            close_all_action = menu.addAction("Close All")
            close_all_action.triggered.connect(self.close_all_tabs)

            menu.exec(self.tabBar().mapToGlobal(position))

    def rename_tab(self, index: int):
        """Show dialog to rename the tab"""
        from PyQt6.QtWidgets import QInputDialog

        current_text = self.tabText(index)

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Tab",
            "Enter new tab name:",
            text=current_text
        )

        if ok and new_name.strip():
            self.setTabText(index, new_name.strip())

    def change_terminal_theme(self, theme_name: str):
        """Change theme for all terminals using dynamic theme system."""
        self.current_term_theme = theme_name

        # Apply theme to all terminals via the update_theme method
        # This is the key line that applies themes to all existing terminals
        self.update_theme(theme_name)

    def close_other_tabs(self, keep_index: int):
        """Close all tabs except the specified one."""
        for i in range(self.count() - 1, -1, -1):
            if i != keep_index:
                self.close_tab(i)

    def close_all_tabs(self):
        """Close all tabs."""
        for i in range(self.count() - 1, -1, -1):
            self.close_tab(i)

    def cleanup_all(self):
        """Clean up all terminals on application exit."""
        try:
            self.close_all_tabs()
            self.sessions.clear()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def create_text_editor_tab(self, title: str = "Notepad") -> str:
        """Create a new text editor tab"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Create notepad widget
            from termtel.widgets.notepad_widget import NotepadWidget
            editor = NotepadWidget()

            # Create wrapper and container
            wrapper = TextEditorWrapper(editor)
            container = GenericTabContainer(editor, wrapper, self)

            # Add to tab widget
            index = self.addTab(container, title)
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container
            return tab_id

        except Exception as e:
            logger.error(f"Failed to create text editor: {e}")
            raise


    def create_diff_tool_tab(self, title: str = "Diff Tool") -> str:
        """Create a new diff tool tab"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Import the diff tool widget

            # Create diff tool widget with current theme
            diff_tool = DiffToolWidget(parent=self.parent)

            # Apply current theme if available
            if hasattr(self.parent, 'theme_manager') and hasattr(self.parent, 'theme'):
                current_theme = self.parent.theme
                diff_tool.apply_theme(self.parent.theme_manager, current_theme)

            # Create wrapper and container
            wrapper = DiffToolWrapper(diff_tool)
            container = GenericTabContainer(diff_tool, wrapper, self)

            # Add to tab widget
            index = self.addTab(container, title)
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container

            # Store a reference to update the theme later if needed
            if not hasattr(self, 'theme_aware_widgets'):
                self.theme_aware_widgets = []
            self.theme_aware_widgets.append(diff_tool)

            return tab_id

        except Exception as e:
            logger.error(f"Failed to create diff tool: {e}")
            import traceback
            traceback.print_exc()
            raise

    def update_all_theme_aware_widgets(self, theme_name):
        """Update theme for all widgets that support theming"""
        if not hasattr(self, 'theme_aware_widgets'):
            return

        # Update the current terminal theme
        self.current_term_theme = self.get_mapped_terminal_theme(theme_name)

        # First update terminals
        self.update_theme(theme_name)

        # Then update any theme-aware widgets (diff tools, network discovery, etc.)
        for widget in self.theme_aware_widgets:
            try:
                if hasattr(widget, 'apply_theme') and callable(widget.apply_theme):
                    # Widget has its own apply_theme method
                    widget.apply_theme(self.parent.theme_manager, theme_name)
                    logger.debug(f"Applied theme to widget using apply_theme method")
                elif hasattr(self.parent, 'theme_manager'):
                    # Fallback: try to apply theme directly via theme manager
                    self.parent.theme_manager.apply_theme(widget, theme_name)
                    logger.debug(f"Applied theme to widget using theme_manager")
            except Exception as e:
                logger.error(f"Failed to update theme for widget: {e}")

        # Also update any wrappers that have apply_theme methods
        for tab_id, container in self.sessions.items():
            try:
                if hasattr(container, 'wrapper') and hasattr(container.wrapper, 'apply_theme'):
                    container.wrapper.apply_theme(self.parent.theme_manager, theme_name)
                    logger.debug(f"Applied theme to wrapper for tab {tab_id}")
            except Exception as e:
                logger.error(f"Failed to update theme for wrapper: {e}")

    def create_game_tab(self, title: str = "Asteroids") -> str:
        """Create a new game tab"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Create game widget with appropriate theme color
            from termtel.widgets.space_debris import AsteroidsWidget

            # Get theme colors using ThemeLibrary
            theme_colors = self.parent.theme_manager.get_colors(self.parent.theme)
            text_color = theme_colors.get('text', '#FFFFFF')

            # Create QColor from hex string
            game_color = QColor(text_color)

            # Create game widget with the color
            game = AsteroidsWidget(color=game_color, parent=self.parent)

            # Create wrapper and container
            wrapper = GameWrapper(game)
            container = GenericTabContainer(game, wrapper, self)

            # Add to tab widget
            index = self.addTab(container, title)
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container
            return tab_id

        except Exception as e:
            logger.error(f"Failed to create game tab: {e}")
            raise

    def close_tab(self, index: int):
        """Handle tab close request."""
        try:
            widget = self.widget(index)
            if widget:
                # Find session ID for this widget
                session_id = None
                for sid, w in self.sessions.items():
                    if w == widget:
                        session_id = sid
                        break

                # Check for unsaved changes if it's a notepad
                notepad = widget.findChild(NotepadWidget)
                if notepad and notepad.has_unsaved_changes:
                    reply = QMessageBox.question(
                        self,
                        "Unsaved Changes",
                        "This note has unsaved changes. Do you want to save before closing?",
                        QMessageBox.StandardButton.Save |
                        QMessageBox.StandardButton.Discard |
                        QMessageBox.StandardButton.Cancel
                    )

                    if reply == QMessageBox.StandardButton.Save:
                        notepad.save_content()
                    elif reply == QMessageBox.StandardButton.Cancel:
                        return

                # Handle telemetry widget cleanup specifically
                from termtel.widgets.TelemetryWidget import TelemetryWidget
                telemetry_widget = None

                # First check if the widget itself is a TelemetryWidget
                if isinstance(widget, TelemetryWidget):
                    telemetry_widget = widget
                else:
                    # Otherwise search for a TelemetryWidget inside this widget
                    telemetry_widget = widget.findChild(TelemetryWidget)

                if telemetry_widget:
                    logger.info("Found telemetry widget to clean up")
                    try:
                        # Call cleanup method on the telemetry widget
                        telemetry_widget.cleanup()

                        # If the widget is in parent's telemetry_widgets list, remove it
                        if hasattr(self.parent,
                                   'telemetry_widgets') and telemetry_widget in self.parent.telemetry_widgets:
                            self.parent.telemetry_widgets.remove(telemetry_widget)

                        # Wait a moment to allow cleanup to complete
                        import time
                        time.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Error cleaning up telemetry widget: {e}")
                        import traceback
                        traceback.print_exc()

                # Clean up and remove the tab
                terminal = widget.findChild(Ui_Terminal)
                if terminal:
                    try:
                        terminal.cleanup()
                    except Exception as e:
                        logger.warning(f"Terminal cleanup failed: {e}")

                # Handle generic cleanup
                if hasattr(widget, 'cleanup'):
                    try:
                        widget.cleanup()
                    except Exception as e:
                        logger.warning(f"Widget cleanup failed: {e}")

                # Remove the tab before widget deletion to prevent UI issues
                self.removeTab(index)

                # Add a small delay before widget deletion to allow cleanup to complete
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(200, lambda: widget.deleteLater())

                # Clean up session
                if session_id:
                    self.remove_session(session_id)

        except Exception as e:
            logger.error(f"Error closing tab: {e}")
            import traceback
            traceback.print_exc()

    def create_network_discovery_tab(self, title: str = "Network Discovery") -> str:
        """Create a new network discovery tab with full space utilization and theme support"""
        try:
            # Generate unique ID for the tab
            tab_id = str(uuid.uuid4())

            # Create network discovery widget with current theme and proper sizing
            discovery_widget = NetworkDiscoveryWidget(parent=self.parent)
            discovery_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Apply current theme if available
            if hasattr(self.parent, 'theme_manager') and hasattr(self.parent, 'theme'):
                current_theme = self.parent.theme
                try:
                    discovery_widget.apply_theme(self.parent.theme_manager, current_theme)
                    logger.debug(f"Applied initial theme {current_theme} to network discovery widget")
                except Exception as e:
                    logger.warning(f"Could not apply initial theme to network discovery widget: {e}")

            # Create wrapper and container
            wrapper = NetworkDiscoveryWrapper(discovery_widget)
            container = GenericTabContainer(discovery_widget, wrapper, self)
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Store wrapper reference on container for theme updates
            container.wrapper = wrapper

            # Ensure the container layout uses full space
            if hasattr(container, 'layout') and container.layout():
                container.layout().setContentsMargins(0, 0, 0, 0)

            # Add to tab widget
            index = self.addTab(container, title)
            self.setCurrentIndex(index)

            # Store in sessions
            self.sessions[tab_id] = container

            # Store a reference to update the theme later if needed
            if not hasattr(self, 'theme_aware_widgets'):
                self.theme_aware_widgets = []
            self.theme_aware_widgets.append(discovery_widget)

            logger.info(f"Created network discovery tab with theme support")
            return tab_id

        except Exception as e:
            logger.error(f"Failed to create network discovery tab: {e}")
            import traceback
            traceback.print_exc()
            raise


class CMDBWrapper:
    def __init__(self, cmdb_widget, parent_window=None):
        from PyQt6.QtWebChannel import QWebChannel

        self.cmdb = cmdb_widget
        self.parent_window = parent_window
        self.channel = QWebChannel()

        # Create theme bridge and set current theme
        self.theme_bridge = ThemeBridge()
        if parent_window and hasattr(parent_window, 'theme'):
            self.theme_bridge.current_theme = parent_window.theme
            print(f"Initialized theme bridge with current theme: {parent_window.theme}")

        # Register the theme bridge with the web channel
        self.channel.registerObject("themeBridge", self.theme_bridge)

        # Set the web channel on the page
        cmdb_widget.page().setWebChannel(self.channel)

        # If we have a parent window, connect to its theme changes
        if parent_window and hasattr(parent_window, 'theme_changed'):
            parent_window.theme_changed.connect(self.theme_bridge.notify_theme_change)

    def update_theme(self, theme_name):
        """Update theme for this CMDB instance"""
        print(f"CMDBWrapper: Updating theme to {theme_name}")
        self.theme_bridge.notify_theme_change(theme_name)

    def cleanup(self):
        if hasattr(self.cmdb, 'cleanup'):
            self.cmdb.cleanup()



# Add this import at the top of your terminal_tabs.py file with the other imports:
from termtel.widgets.network_discovery_widget import NetworkDiscoveryWidget


def create_network_discovery_tab(self, title: str = "Network Discovery") -> str:
    """Create a new network discovery tab with full space utilization and theme support"""
    try:
        # Generate unique ID for the tab
        tab_id = str(uuid.uuid4())

        # Create network discovery widget with current theme and proper sizing
        discovery_widget = NetworkDiscoveryWidget(parent=self.parent)
        discovery_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Apply current theme if available
        if hasattr(self.parent, 'theme_manager') and hasattr(self.parent, 'theme'):
            current_theme = self.parent.theme
            try:
                discovery_widget.apply_theme(self.parent.theme_manager, current_theme)
                logger.debug(f"Applied initial theme {current_theme} to network discovery widget")
            except Exception as e:
                logger.warning(f"Could not apply initial theme to network discovery widget: {e}")

        # Create wrapper and container
        wrapper = NetworkDiscoveryWrapper(discovery_widget)
        container = GenericTabContainer(discovery_widget, wrapper, self)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Store wrapper reference on container for theme updates
        container.wrapper = wrapper

        # Ensure the container layout uses full space
        if hasattr(container, 'layout') and container.layout():
            container.layout().setContentsMargins(0, 0, 0, 0)

        # Add to tab widget
        index = self.addTab(container, title)
        self.setCurrentIndex(index)

        # Store in sessions
        self.sessions[tab_id] = container

        # Store a reference to update the theme later if needed
        if not hasattr(self, 'theme_aware_widgets'):
            self.theme_aware_widgets = []
        self.theme_aware_widgets.append(discovery_widget)

        logger.info(f"Created network discovery tab with theme support")
        return tab_id

    except Exception as e:
        logger.error(f"Failed to create network discovery tab: {e}")
        import traceback
        traceback.print_exc()
        raise


class NetworkDiscoveryWrapper:
    """Wrapper class to standardize network discovery interface"""

    def __init__(self, discovery_widget):
        self.discovery = discovery_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.discovery, 'cleanup'):
            self.discovery.cleanup()

        # Stop any running discovery process
        if hasattr(self.discovery, 'discovery_process'):
            try:
                self.discovery.discovery_process.stop_discovery()
            except Exception as e:
                logger.warning(f"Error stopping discovery process: {e}")

    def apply_theme(self, theme_manager, theme_name):
        """Apply theme to the discovery widget"""
        if hasattr(self.discovery, 'parent_window') and hasattr(self.discovery.parent_window, 'theme_manager'):
            try:
                self.discovery.parent_window.theme_manager.apply_theme(self.discovery, theme_name)
            except Exception as e:
                logger.warning(f"Could not apply theme to network discovery: {e}")


class CMDBImportWrapper:
    """Wrapper class to standardize CMDB import interface with theme support"""

    def __init__(self, import_widget):
        self.import_widget = import_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.import_widget, 'cleanup'):
            self.import_widget.cleanup()

        # Stop any running import process
        if hasattr(self.import_widget, 'import_thread') and self.import_widget.import_thread:
            try:
                if self.import_widget.import_thread.isRunning():
                    self.import_widget.import_thread.terminate()
                    self.import_widget.import_thread.wait(3000)
                logger.info("Stopped running import process")
            except Exception as e:
                logger.warning(f"Error stopping import process: {e}")

        # Save settings
        if hasattr(self.import_widget, 'save_settings'):
            try:
                self.import_widget.save_settings()
            except Exception as e:
                logger.warning(f"Error saving import settings: {e}")

    def apply_theme(self, theme_manager, theme_name):
        """Apply theme to the import widget"""
        try:
            # Call with the correct parameters
            self.import_widget.apply_theme(theme_manager, theme_name)
            logger.debug(f"Applied theme {theme_name} to CMDB import widget")
        except Exception as e:
            logger.warning(f"Could not apply theme to CMDB import widget: {e}")