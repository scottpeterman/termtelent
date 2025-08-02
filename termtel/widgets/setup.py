"""
Termtel - UI Setup Module
Handles menu system with proper theme signaling for telemetry widgets
"""
import sys
import yaml
from PyQt6.QtGui import QActionGroup, QAction, QDesktopServices
from PyQt6.QtWidgets import (
    QMenuBar, QMenu, QFileDialog, QDialog,
    QVBoxLayout, QLabel, QWidget, QGroupBox, QPushButton, QMessageBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, Qt, QProcess, QProcessEnvironment, pyqtSignal
import logging
import os

from termtel.theme_launcher import launch_theme_editor
from termtel.widgets.about_dialog import AboutDialog
from termtel.widgets.credential_manager import CredentialManagerDialog
from termtel.widgets.db_maintenance_widget import DatabaseMaintenanceWidget
from termtel.widgets.fingerprint_widget import VendorFingerprintEditor
from termtel.widgets.lmtosession import LMDownloader
from termtel.widgets.nbtosession import App as NetboxExporter
from termtel.logo import get_themed_svg
from termtel.widgets.terminal_tabs import CMDBImportWrapper

logger = logging.getLogger('termtel.setup')

# Import main theme manager
try:
    from termtel.themes3 import ThemeLibrary
    MAIN_THEME_MANAGER_AVAILABLE = True
except ImportError:
    MAIN_THEME_MANAGER_AVAILABLE = False
    logger.warning("Main theme manager not available")



from termtel.widgets.network_discovery_widget import NetworkDiscoveryWidget as NetworkDiscoveryDialog


class DatabaseMaintenanceWrapper:
    """Wrapper class to standardize database maintenance interface"""

    def __init__(self, maintenance_widget):
        self.maintenance = maintenance_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.maintenance, 'cleanup'):
            self.maintenance.cleanup()



def show_network_discovery(window):
    """Show the network discovery tool as a standalone window"""
    try:
        # Check if we already have a network discovery window open
        if hasattr(window, 'network_discovery') and window.network_discovery:
            window.network_discovery.raise_()
            window.network_discovery.activateWindow()
            return

        # Create new network discovery window
        discovery_window = NetworkDiscoveryDialog(window)
        discovery_window.setWindowTitle("Network Discovery Tool")

        # Store reference
        window.network_discovery = discovery_window

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                window.theme_manager.apply_theme(discovery_window, window.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to network discovery: {e}")

        discovery_window.show()
        logger.info("Opened network discovery tool")

    except ImportError as e:
        logger.error(f"Failed to import network discovery tool: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Network Discovery Tool module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing network discovery tool: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Network Discovery Tool:\n{str(e)}"
        )


def show_network_discovery_as_tab(window):
    """Show the network discovery tool as a tab"""
    try:
        # Check if terminal_tabs exists and has the method
        if not hasattr(window, 'terminal_tabs'):
            logger.error("No terminal_tabs found on window")
            QMessageBox.warning(
                window,
                "Error",
                "Terminal tabs system not available."
            )
            return

        if not hasattr(window.terminal_tabs, 'create_network_discovery_tab'):
            logger.error("create_network_discovery_tab method not found")
            QMessageBox.warning(
                window,
                "Error",
                "Network Discovery tab creation not available.\nPlease check your terminal_tabs.py file."
            )
            return

        # Create network discovery tab using the terminal tabs system
        tab_id = window.terminal_tabs.create_network_discovery_tab("Network Discovery")
        logger.info("Created network discovery tab")
        return tab_id

    except ImportError as e:
        logger.error(f"Failed to import network discovery tool: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Network Discovery Tool module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing network discovery tool: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Network Discovery Tool:\n{str(e)}"
        )



def setup_menus(window):
    """Setup menu system for the main window"""
    menubar = window.menuBar()

    # File Menu
    file_menu = menubar.addMenu("&File")
    open_action = file_menu.addAction("&Open Sessions...")
    open_action.triggered.connect(lambda: handle_open_sessions(window))
    file_menu.addSeparator()
    exit_action = file_menu.addAction("E&xit")
    exit_action.triggered.connect(window.close)

    # View Menu
    view_menu = menubar.addMenu("&View")

    # Create Themes submenu with dynamic theme loading
    themes_menu = view_menu.addMenu("Theme")
    theme_group = QActionGroup(window)
    theme_group.setExclusive(True)

    # Get available themes from ThemeLibrary
    available_themes = window.theme_manager.get_theme_names()

    # Create theme actions with safe theme switching
    for theme_name in available_themes:
        # Convert theme name to display name (e.g., "dark_mode" -> "Dark Mode")
        display_name = theme_name.replace('_', ' ').title()

        theme_action = QAction(display_name, window)
        theme_action.setCheckable(True)
        theme_action.setChecked(theme_name == window.theme)
        theme_action.triggered.connect(
            lambda checked, t=theme_name: safe_switch_theme(window, t)
        )

        theme_group.addAction(theme_action)
        themes_menu.addAction(theme_action)

    # Add theme reload action
    themes_menu.addSeparator()
    theme_editor_action = themes_menu.addAction("Theme Editor")
    theme_editor_action.triggered.connect(lambda: launch_theme_editor(window))

    reload_themes = themes_menu.addAction("Reload Themes")
    reload_themes.triggered.connect(lambda: reload_theme_menu(window, themes_menu, theme_group))
    download_themes = themes_menu.addAction("Download Themes")
    download_themes.triggered.connect(
        lambda: QDesktopServices.openUrl(
            QUrl("https://raw.githubusercontent.com/scottpeterman/terminaltelemetry/main/themes.zip")
        )
    )
    credentials_action = view_menu.addAction("&Credentials")
    credentials_action.triggered.connect(lambda: show_unified_credentials_dialog(window))

    # Tools Menu
    tools_menu = menubar.addMenu("&Tools")
    serial_terminal_action = tools_menu.addAction("Serial &Terminal")
    serial_terminal_action.triggered.connect(
        lambda: window.terminal_tabs.create_serial_terminal_tab("Serial Terminal")
    )
    netbox_action = tools_menu.addAction("&Netbox Import")
    netbox_action.triggered.connect(lambda: show_netbox_importer(window))

    lm_action = tools_menu.addAction("&LogicMonitor Import")
    lm_action.triggered.connect(lambda: show_logicmonitor_importer(window))

    # Use safe telemetry tab creation
    telemetry_action = tools_menu.addAction('Telemetry Dashboard')
    telemetry_action.triggered.connect(lambda: safe_create_telemetry_tab(window))

    tools_menu.addSeparator()

    # RapidCMDB Submenu
    rapidcmdb_menu = tools_menu.addMenu("RapidCMDB")
    rapidcmdb_menu.setObjectName("menu_rapidcmdb")

    # RapidCMDB Application
    rapidcmdb_app_action = rapidcmdb_menu.addAction("RapidCMDB Application")
    rapidcmdb_app_action.triggered.connect(
        lambda: window.terminal_tabs.create_cmdb_tab("RapidCMDB")
    )

    # Vendor Fingerprint Editor
    fingerprint_editor_action = rapidcmdb_menu.addAction("Vendor Fingerprint Editor")
    fingerprint_editor_action.triggered.connect(lambda: show_fingerprint_editor_as_tab(window))

    # Database Maintenance Tool (stub for future implementation)
    db_maintenance_action = rapidcmdb_menu.addAction("Database Maintenance")
    db_maintenance_action.triggered.connect(lambda: show_db_maintenance(window))
    db_maintenance_action.setEnabled(True)
    # db_maintenance_action.setToolTip("Coming Soon - Database maintenance and optimization tools")

    # Optional: Add separator and advanced tools
    rapidcmdb_menu.addSeparator()

    # Configuration Tools submenu within RapidCMDB
    config_tools_menu = rapidcmdb_menu.addMenu("Configuration Tools")
    config_tools_menu.setObjectName("menu_rapidcmdb_config")

    # Move fingerprint editor to config tools if you prefer more organization
    fingerprint_config_action = config_tools_menu.addAction("Edit Vendor Fingerprints")
    fingerprint_config_action.triggered.connect(lambda: show_fingerprint_editor_as_tab(window))

    # Future config tools
    db_config_action = config_tools_menu.addAction("Database Configuration")
    db_config_action.triggered.connect(lambda: show_db_config_tool(window))
    db_config_action.setEnabled(False)
    db_config_action.setToolTip("Coming Soon - Database configuration editor")

    scan_config_action = config_tools_menu.addAction("Scan Configuration")
    scan_config_action.triggered.connect(lambda: show_scan_config_tool(window))
    scan_config_action.setEnabled(False)
    scan_config_action.setToolTip("Coming Soon - SNMP scan configuration editor")

    tools_menu.addSeparator()

    # Add CMDB Import submenu
    cmdb_import_menu = tools_menu.addMenu("CMDB Import")
    cmdb_import_menu.setObjectName("menu_cmdb_import")
    # CMDB Scan Import Tool
    scan_import_action = cmdb_import_menu.addAction("Scanner Import Tool")
    scan_import_action.triggered.connect(lambda: show_cmdb_scan_import_as_tab(window))

    # Alternative: as a standalone window
    scan_import_window_action = cmdb_import_menu.addAction("Scanner Import Tool (Window)")
    scan_import_window_action.triggered.connect(lambda: show_cmdb_scan_import_window(window))
    tools_menu.addSeparator()


    manage_sessions_action = tools_menu.addAction('Manage Sessions')
    manage_sessions_action.triggered.connect(lambda: show_session_manager(window))
    napalm_action = tools_menu.addAction("NAPALM &Tester")
    napalm_action.triggered.connect(lambda: safe_create_napalm_tab(window))
    # Add separator before map tools
    tools_menu.addSeparator()

    # Add Map Tools submenu
    map_tools_menu = tools_menu.addMenu("Map Tools")
    map_tools_menu.setObjectName("menu_map_tools")

    network_discovery_action = map_tools_menu.addAction("Network Discovery")
    network_discovery_action.triggered.connect(lambda: show_network_discovery_as_tab(window))

    # Network Topology Viewer
    topology_viewer_action = map_tools_menu.addAction("Network Topology Viewer")
    topology_viewer_action.triggered.connect(lambda: show_topology_viewer(window))

    # Network Map Enhancer
    map_enhancer_action = map_tools_menu.addAction("Network Map Enhancer")
    map_enhancer_action.triggered.connect(lambda: show_map_enhancer(window))

    # Icon Mapping Editor
    icon_editor_action = map_tools_menu.addAction("Icon Mapping Editor")
    icon_editor_action.triggered.connect(lambda: show_icon_editor(window))

    # Map Editor
    map_editor_action = map_tools_menu.addAction("Map Editor")
    map_editor_action.triggered.connect(lambda: show_map_editor(window))

    # Map Merge Tool
    map_merge_action = map_tools_menu.addAction("Map Merge Tool")
    map_merge_action.triggered.connect(lambda: show_map_merge_dialog(window))

    # Add separator before distractions menu
    tools_menu.addSeparator()

    # Add Distractions submenu
    distractions_menu = tools_menu.addMenu("Distractions")
    distractions_menu.setObjectName("menu_distractions")

    # Add Notepad action
    notepad_action = distractions_menu.addAction("Notepad")
    notepad_action.triggered.connect(
        lambda: window.terminal_tabs.create_text_editor_tab("Notepad")
    )

    diff_tool_action = distractions_menu.addAction("Diff Tool")
    diff_tool_action.triggered.connect(
        lambda: window.terminal_tabs.create_diff_tool_tab("Diff Tool")
    )

    space_debris = distractions_menu.addAction("Space Debris")
    space_debris.triggered.connect(
        lambda: window.terminal_tabs.create_game_tab("Space Debris")
    )

    # Help Menu
    help_menu = menubar.addMenu("&Help")
    about_action = help_menu.addAction("&About")
    about_action.triggered.connect(lambda: show_about_dialog(window))

def show_fingerprint_editor_as_tab(window):
    """Show the vendor fingerprint editor as a tab"""
    try:
        # Check if terminal_tabs exists and has the method
        if not hasattr(window, 'terminal_tabs'):
            logger.error("No terminal_tabs found on window")
            QMessageBox.warning(
                window,
                "Error",
                "Terminal tabs system not available."
            )
            return

        if not hasattr(window.terminal_tabs, 'create_fingerprint_editor_tab'):
            logger.error("create_fingerprint_editor_tab method not found")
            QMessageBox.warning(
                window,
                "Error",
                "Vendor Fingerprint Editor tab creation not available.\nPlease check your terminal_tabs.py file."
            )
            return

        # Create fingerprint editor tab using the terminal tabs system
        tab_id = window.terminal_tabs.create_fingerprint_editor_tab("Vendor Fingerprint Editor")
        logger.info("Created vendor fingerprint editor tab")
        return tab_id

    except ImportError as e:
        logger.error(f"Failed to import vendor fingerprint editor: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Vendor Fingerprint Editor module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing vendor fingerprint editor: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Vendor Fingerprint Editor:\n{str(e)}"
        )

def show_fingerprint_editor_window(window):
    """Show the vendor fingerprint editor as a standalone window"""
    try:
        # Check if we already have an editor window open
        if hasattr(window, 'fingerprint_editor_window') and window.fingerprint_editor_window:
            window.fingerprint_editor_window.raise_()
            window.fingerprint_editor_window.activateWindow()
            return

        # Import the editor widget
        from termtel.widgets.vendor_fingerprint_editor import VendorFingerprintEditor

        # Create standalone window
        editor_window = QWidget()
        editor_window.setWindowTitle("Vendor Fingerprint Editor")
        editor_window.resize(1400, 900)
        editor_window.setMinimumSize(1000, 600)

        # Set proper window attributes
        editor_window.setWindowFlags(Qt.WindowType.Window)
        editor_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout(editor_window)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create the editor widget with theme manager
        editor_widget = VendorFingerprintEditor(
            parent=editor_window,
            theme_manager=getattr(window, 'theme_manager', None)
        )
        layout.addWidget(editor_widget)

        # Create a custom closeEvent for cleanup
        def closeEvent(event):
            # Clear the reference when window is closed
            if hasattr(window, 'fingerprint_editor_window'):
                window.fingerprint_editor_window = None
            event.accept()
            editor_window.deleteLater()

        # Override the closeEvent
        editor_window.closeEvent = closeEvent

        # Store reference
        window.fingerprint_editor_window = editor_window

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                editor_widget.apply_theme(window.theme_manager, window.theme)
                logger.debug(f"Applied theme {window.theme} to vendor fingerprint editor")
            except Exception as e:
                logger.warning(f"Could not apply theme to vendor fingerprint editor: {e}")

        editor_window.show()
        logger.info("Opened vendor fingerprint editor as standalone window")

    except ImportError as e:
        logger.error(f"Failed to import vendor fingerprint editor: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Vendor Fingerprint Editor module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing vendor fingerprint editor: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Vendor Fingerprint Editor:\n{str(e)}"
        )


def show_db_maintenance(window):
    """Show the database maintenance tool as a tab (fallback method)"""
    try:
        # Generate unique ID for the tab
        import uuid
        tab_id = str(uuid.uuid4())

        # Create database maintenance widget with current theme and proper sizing
        from PyQt6.QtWidgets import QSizePolicy
        maintenance_widget = DatabaseMaintenanceWidget(
            parent=window,
            theme_manager=getattr(window, 'theme_manager', None)
        )
        maintenance_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Apply current theme if available
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            current_theme = window.theme
            try:
                maintenance_widget.apply_theme(window.theme_manager, current_theme)
                logger.debug(f"Applied initial theme {current_theme} to database maintenance widget")
            except Exception as e:
                logger.warning(f"Could not apply initial theme to database maintenance widget: {e}")

        # Create wrapper and container
        wrapper = DatabaseMaintenanceWrapper(maintenance_widget)

        # Use the existing GenericTabContainer if available
        if hasattr(window.terminal_tabs, 'sessions'):
            from termtel.widgets.terminal_app_wrapper import GenericTabContainer
            container = GenericTabContainer(maintenance_widget, wrapper, window.terminal_tabs)
            container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            # Store wrapper reference on container for theme updates
            container.wrapper = wrapper

            # Ensure the container layout uses full space
            if hasattr(container, 'layout') and container.layout():
                container.layout().setContentsMargins(0, 0, 0, 0)

            # Add to tab widget with icon if available
            from PyQt6.QtGui import QIcon
            from pathlib import Path
            icon_path = Path(__file__).parent / 'icons' / 'database-maintenance.svg'

            if icon_path.exists():
                tab_icon = QIcon(str(icon_path))
                index = window.terminal_tabs.addTab(container, tab_icon, "Database Maintenance")
            else:
                index = window.terminal_tabs.addTab(container, "Database Maintenance")

            window.terminal_tabs.setTabToolTip(index, "Database maintenance and optimization tools")
            window.terminal_tabs.setCurrentIndex(index)

            # Store in sessions
            window.terminal_tabs.sessions[tab_id] = container

            # Store a reference to update the theme later if needed
            if not hasattr(window.terminal_tabs, 'theme_aware_widgets'):
                window.terminal_tabs.theme_aware_widgets = []
            window.terminal_tabs.theme_aware_widgets.append(maintenance_widget)

            logger.info(f"Created database maintenance tab with theme support")
            return tab_id
        else:
            # Fallback to standalone window
            print("Failed to load db maint tool as tab")
            return

    except Exception as e:
        logger.error(f"Failed to create database maintenance tab: {e}")
        import traceback
        traceback.print_exc()

        # Show error dialog
        QMessageBox.critical(
            window,
            "Database Maintenance Error",
            f"Failed to create database maintenance tab:\n{str(e)}"
        )
        return None


def show_db_config_tool(window):
    """Show the database configuration tool (stub for future implementation)"""
    QMessageBox.information(
        window,
        "Coming Soon",
        "Database Configuration Tool\n\n"
        "This tool will provide:\n"
        "• Connection string management\n"
        "• Schema configuration\n"
        "• Data retention policies\n"
        "• Performance tuning settings\n\n"
        "Currently under development..."
    )

def show_scan_config_tool(window):
    """Show the scan configuration tool (stub for future implementation)"""
    QMessageBox.information(
        window,
        "Coming Soon",
        "Scan Configuration Tool\n\n"
        "This tool will provide:\n"
        "• SNMP community and credential management\n"
        "• Scan timing and performance settings\n"
        "• Network range and exclusion configuration\n"
        "• Custom OID and MIB management\n\n"
        "Currently under development..."
    )


# Map Tools Functions
def show_topology_viewer(window):
    """Show the network topology viewer"""
    try:
        from termtel.mviewer import TopologyViewer

        # Check if we already have a topology viewer tab open
        if hasattr(window, 'topology_viewer') and window.topology_viewer:
            # Bring existing viewer to front
            window.topology_viewer.raise_()
            window.topology_viewer.activateWindow()
            return

        # Create new topology viewer
        viewer = TopologyViewer(dark_mode=True, parent=window)
        viewer.setWindowTitle("Network Topology Viewer")

        # Store reference to prevent garbage collection
        window.topology_viewer = viewer

        # Apply current theme if theme manager is available
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                window.theme_manager.apply_theme(viewer, window.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to topology viewer: {e}")

        viewer.show()
        logger.info("Opened network topology viewer")

    except ImportError as e:
        logger.error(f"Failed to import topology viewer: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Network Topology Viewer module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing topology viewer: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Network Topology Viewer:\n{str(e)}"
        )


def show_map_enhancer(window):
    """Show the network map enhancer widget"""
    try:
        from termtel.map_enhance_widget import TopologyEnhanceWidget

        # Check if we already have a map enhancer open and close it
        if hasattr(window, 'map_enhancer') and window.map_enhancer is not None:
            try:
                # Properly close the existing window
                window.map_enhancer.close()
                window.map_enhancer.deleteLater()
            except:
                pass  # In case the window was already destroyed
            finally:
                window.map_enhancer = None

        # Create new map enhancer window
        enhancer_window = QWidget()
        enhancer_window.setWindowTitle("Network Map Enhancer")
        enhancer_window.resize(700, 600)

        # Set proper window attributes for cleanup
        enhancer_window.setWindowFlags(Qt.WindowType.Window)
        enhancer_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout(enhancer_window)
        enhancer_widget = TopologyEnhanceWidget()
        layout.addWidget(enhancer_widget)

        # Create a custom closeEvent for the wrapper window
        def closeEvent(event):
            # Clear the reference when window is closed
            if hasattr(window, 'map_enhancer'):
                window.map_enhancer = None
            event.accept()
            enhancer_window.deleteLater()

        # Override the closeEvent
        enhancer_window.closeEvent = closeEvent

        # Store reference
        window.map_enhancer = enhancer_window

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                window.theme_manager.apply_theme(enhancer_window, window.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to map enhancer: {e}")

        enhancer_window.show()
        logger.info("Opened network map enhancer")

    except ImportError as e:
        logger.error(f"Failed to import map enhancer: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Network Map Enhancer module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing map enhancer: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Network Map Enhancer:\n{str(e)}"
        )

def show_icon_editor(window):
    """Show the icon mapping editor"""
    try:
        from termtel.icon_map_editor import IconConfigEditor

        # Check if we already have an icon editor open
        if hasattr(window, 'icon_editor') and window.icon_editor:
            window.icon_editor.raise_()
            window.icon_editor.activateWindow()
            return

        # Create new icon editor window
        editor_window = QWidget()
        editor_window.setWindowTitle("Icon Mapping Editor")
        editor_window.resize(900, 500)

        layout = QVBoxLayout(editor_window)
        editor_widget = IconConfigEditor()
        layout.addWidget(editor_widget)

        # Store reference
        window.icon_editor = editor_window

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                window.theme_manager.apply_theme(editor_window, window.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to icon editor: {e}")

        editor_window.show()
        logger.info("Opened icon mapping editor")

    except ImportError as e:
        logger.error(f"Failed to import icon editor: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Icon Mapping Editor module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing icon editor: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Icon Mapping Editor:\n{str(e)}"
        )


def show_map_editor(window):
    """Show the map editor widget"""
    try:
        from termtel.map_editor import TopologyWidget

        # Check if we already have a map editor open
        if hasattr(window, 'map_editor') and window.map_editor:
            window.map_editor.raise_()
            window.map_editor.activateWindow()
            return

        # Create new map editor
        editor = TopologyWidget()
        editor.setWindowTitle("Map Editor")
        editor.resize(1000, 600)

        # Store reference
        window.map_editor = editor

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                window.theme_manager.apply_theme(editor, window.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to map editor: {e}")

        editor.show()
        logger.info("Opened map editor")

    except ImportError as e:
        logger.error(f"Failed to import map editor: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Map Editor module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing map editor: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Map Editor:\n{str(e)}"
        )


def show_map_merge_dialog(window):
    """Show the map merge dialog"""
    try:
        from termtel.merge_dialog import TopologyMergeDialog

        dialog = TopologyMergeDialog(window)

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                window.theme_manager.apply_theme(dialog, window.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to merge dialog: {e}")

        # Connect merge complete signal if needed
        def on_merge_complete(output_file):
            logger.info(f"Map merge completed: {output_file}")
            QMessageBox.information(
                window,
                "Merge Complete",
                f"Maps successfully merged to:\n{output_file}"
            )

        dialog.merge_complete.connect(on_merge_complete)
        dialog.exec()
        logger.info("Opened map merge dialog")

    except ImportError as e:
        logger.error(f"Failed to import merge dialog: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "Map Merge Tool module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing map merge dialog: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Map Merge Tool:\n{str(e)}"
        )


def safe_switch_theme(window, theme_name):
    """
    Safe theme switching that handles both old and new telemetry properly
    """
    print(f"Safe theme switch to: {theme_name}")

    try:
        # Apply theme to main window using existing method
        if hasattr(window, 'switch_theme'):
            try:
                window.switch_theme(theme_name)
            except Exception as e:
                print(f"Error in main switch_theme: {e}")
                # Fallback: apply directly if switch_theme fails
                if hasattr(window, 'theme_manager'):
                    window.theme_manager.apply_theme(window, theme_name)
                    window.theme = theme_name

        db_maintenance_windows = ['db_maintenance']
        for window_attr in db_maintenance_windows:
            if hasattr(window, window_attr):
                maintenance_window = getattr(window, window_attr)
                if maintenance_window and hasattr(window, 'theme_manager'):
                    try:
                        # Find the maintenance widget inside the window
                        from termtel.widgets.db_maintenance_widget import DatabaseMaintenanceWidget
                        maintenance_widget = maintenance_window.findChild(DatabaseMaintenanceWidget)
                        if maintenance_widget:
                            maintenance_widget.apply_theme(window.theme_manager, theme_name)
                            print(f"Applied theme to {window_attr}")
                    except Exception as e:
                        print(f"Could not apply theme to {window_attr}: {e}")

        # Handle new telemetry widgets
        if hasattr(window, 'telemetry_widgets'):
            for widget in window.telemetry_widgets:
                try:
                    if hasattr(widget, 'set_theme_from_parent'):
                        widget.set_theme_from_parent(theme_name)
                    elif hasattr(widget, '_apply_theme'):
                        widget._apply_theme(theme_name)
                except Exception as e:
                    print(f"Could not apply theme to telemetry widget: {e}")

        if hasattr(window, 'napalm_widgets'):
            for widget in window.napalm_widgets:
                try:
                    if hasattr(widget, 'set_theme_from_parent'):
                        widget.set_theme_from_parent(theme_name)
                    elif hasattr(widget, 'apply_theme'):
                        widget.apply_theme(theme_name)
                except Exception as e:
                    print(f"Could not apply theme to NAPALM widget: {e}")

        if hasattr(window, 'terminal_tabs') and hasattr(window.terminal_tabs, 'sessions'):
            for tab_id, container in window.terminal_tabs.sessions.items():
                try:
                    if hasattr(container, 'wrapper') and isinstance(container.wrapper, CMDBImportWrapper):
                        container.wrapper.apply_theme(window.theme_manager, theme_name)
                        logger.debug(f"Applied theme to CMDB import tab {tab_id}")
                except Exception as e:
                    logger.error(f"Failed to update theme for CMDB import tab: {e}")

        if hasattr(window, 'terminal_tabs') and hasattr(window.terminal_tabs, 'cmdb_wrappers'):
            print(f"Updating {len(window.terminal_tabs.cmdb_wrappers)} CMDB tabs...")
            for wrapper in window.terminal_tabs.cmdb_wrappers:
                try:
                    wrapper.update_theme(theme_name)
                except Exception as e:
                    print(f"Could not update CMDB theme: {e}")

        fingerprint_windows = ['fingerprint_editor_window']
        for window_attr in fingerprint_windows:
            if hasattr(window, window_attr):
                fingerprint_window = getattr(window, window_attr)
                if fingerprint_window and hasattr(window, 'theme_manager'):
                    try:
                        # Find the editor widget inside the window
                        editor_widget = fingerprint_window.findChild(VendorFingerprintEditor)
                        if editor_widget:
                            editor_widget.apply_theme(window.theme_manager, theme_name)
                            print(f"Applied theme to {window_attr}")
                    except Exception as e:
                        print(f"Could not apply theme to {window_attr}: {e}")

        # Update map tool windows with new theme
        map_windows = ['topology_viewer', 'map_enhancer', 'icon_editor', 'map_editor']
        for window_attr in map_windows:
            if hasattr(window, window_attr):
                map_window = getattr(window, window_attr)
                if map_window and hasattr(window, 'theme_manager'):
                    try:
                        window.theme_manager.apply_theme(map_window, theme_name)
                        print(f"Applied theme to {window_attr}")
                    except Exception as e:
                        print(f"Could not apply theme to {window_attr}: {e}")

        # Emit theme change signal for other components
        if hasattr(window, 'theme_changed'):
            window.theme_changed.emit(theme_name)

        print(f"Theme switch to {theme_name} completed")

    except Exception as e:
        print(f"Error in safe_switch_theme: {e}")
        QMessageBox.warning(
            window,
            "Theme Switch Warning",
            f"Theme change partially failed: {str(e)}"
        )


def safe_create_telemetry_tab(window):
    """
    Safe telemetry tab creation with theme manager registration
    """
    try:
        # Initialize telemetry theme manager if this is the first telemetry tab
        if not hasattr(window, 'telemetry_theme_manager'):
            # window.telemetry_theme_manager = TelemetryWidgetThemeManager(window)
            print("Initialized telemetry theme manager")

        # Create telemetry tab using existing method
        if hasattr(window.terminal_tabs, 'create_telemetry_tab'):
            tab = window.terminal_tabs.create_telemetry_tab("Telemetry")

            # Register with theme manager if it's a new-style widget
            if hasattr(window, 'telemetry_theme_manager'):

                telemetry_widget = None

                # Find the telemetry widget in the tab
                if hasattr(tab, 'telemetry_widget'):
                    telemetry_widget = tab.telemetry_widget
                elif hasattr(tab, 'set_theme_from_parent'):
                    telemetry_widget = tab

                if telemetry_widget:
                    try:
                        window.telemetry_theme_manager.register_telemetry_widget(telemetry_widget)
                        print("Registered telemetry widget with theme manager")

                        # Apply current theme to new widget
                        if hasattr(window, 'theme'):
                            telemetry_widget.set_theme_from_parent(window.theme)

                    except Exception as e:
                        print(f"Could not register telemetry widget: {e}")
        else:
            # Fallback to old method
            window.terminal_tabs.create_telemetry_tab("Telemetry")

    except Exception as e:
        print(f"Error creating telemetry tab: {e}")
        QMessageBox.warning(window, "Telemetry Error", f"Could not create telemetry tab: {str(e)}")


def reload_theme_menu(window, themes_menu, theme_group):
    """Reload the themes menu with current themes from ThemeLibrary"""
    # Clear existing theme actions
    for action in theme_group.actions():
        themes_menu.removeAction(action)
        theme_group.removeAction(action)

    # Reload themes from library
    window.theme_manager._load_custom_themes()

    # Add new theme actions with safe switching
    available_themes = window.theme_manager.get_theme_names()
    for theme_name in available_themes:
        display_name = theme_name.replace('_', ' ').title()
        theme_action = QAction(display_name, window)
        theme_action.setCheckable(True)
        theme_action.setChecked(theme_name == window.theme)
        theme_action.triggered.connect(
            lambda checked, t=theme_name: safe_switch_theme(window, t)
        )
        theme_group.addAction(theme_action)
        themes_menu.insertAction(themes_menu.actions()[-2], theme_action)  # Insert before separator


def show_session_manager(window):
    """Launch the session manager dialog"""
    from termtel.widgets.session_editor import SessionEditorDialog

    dialog = SessionEditorDialog(window, session_file=window.session_file_with_path)
    if dialog.exec() == dialog.DialogCode.Accepted:
        try:
            with open(window.session_file_with_path) as f:
                sessions_data = yaml.safe_load(f)
                window.session_navigator.load_sessions(file_content_to_load=sessions_data)
        except Exception as e:
            logger.error(f"Failed to load sessions: {str(e)}")


def show_netbox_importer(window):
    """Show the Netbox to Session importer"""
    try:
        dialog = NetboxExporter(window)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.show()
    except Exception as e:
        logger.error(f"Error showing Netbox importer: {e}")


def handle_open_sessions(window):
    """Handle opening a new sessions file"""
    try:
        file_name, _ = QFileDialog.getOpenFileName(
            window,
            "Open Sessions File",
            "",
            "YAML Files (*.yaml);;All Files (*)"
        )
        if file_name:
            logger.info(f"Opening sessions file: {file_name}")
            window.session_file = file_name
            window.load_sessions()
    except Exception as e:
        logger.error(f"Error opening sessions file: {e}")


def show_credentials_dialog(window):
    """Show the credentials management dialog"""
    try:
        dialog = CredentialManagerDialog(window)
        dialog.credentials_updated.connect(window.session_navigator.load_sessions)
        dialog.exec()
    except Exception as e:
        logger.error(f"Error showing credentials dialog: {e}")


def show_about_dialog(window):
    """Show the about dialog"""
    try:
        dialog = AboutDialog(window)
        dialog.exec()
    except Exception as e:
        logger.error(f"Error showing about dialog: {e}")


def show_logicmonitor_importer(window):
    """Show the LogicMonitor to Session importer"""
    try:
        window.lmdialog = LMDownloader(window)
        window.lmdialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        window.lmdialog.show()
    except Exception as e:
        logger.error(f"Error showing LogicMonitor importer: {e}")


def safe_close_telemetry_tab(window, tab_widget):
    """
    Safe cleanup when closing telemetry tabs
    Call this when a telemetry tab is closed
    """
    try:
        if hasattr(window, 'telemetry_widgets'):
            # Remove from telemetry widgets list
            if hasattr(tab_widget, 'telemetry_widget') and tab_widget.telemetry_widget in window.telemetry_widgets:
                window.telemetry_widgets.remove(tab_widget.telemetry_widget)
            elif hasattr(tab_widget, 'set_theme_from_parent') and tab_widget in window.telemetry_widgets:
                window.telemetry_widgets.remove(tab_widget)

        # Call cleanup on telemetry widget if it has one
        if hasattr(tab_widget, 'telemetry_widget') and hasattr(tab_widget.telemetry_widget, 'cleanup'):
            tab_widget.telemetry_widget.cleanup()
        elif hasattr(tab_widget, 'cleanup'):
            tab_widget.cleanup()

    except Exception as e:
        print(f"Error during telemetry tab cleanup: {e}")


def show_unified_credentials_dialog(window):
    """Show the unified credential management dialog"""
    try:
        from termtel.widgets.unified_credential_manager import UnifiedCredentialManager

        dialog = UnifiedCredentialManager(window)

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                window.theme_manager.apply_theme(dialog, window.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme to credential manager: {e}")

        # Connect credential update signal
        dialog.credentials_updated.connect(window.session_navigator.load_sessions)

        # Connect to any RapidCMDB credential refresh if needed
        if hasattr(window, 'refresh_rapidcmdb_credentials'):
            dialog.credentials_updated.connect(window.refresh_rapidcmdb_credentials)

        dialog.exec()

    except ImportError as e:
        logger.error(f"Failed to import unified credential manager: {e}")
        # Fallback to old credential manager
        show_credentials_dialog_legacy(window)
    except Exception as e:
        logger.error(f"Error showing unified credential manager: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open Credential Manager:\n{str(e)}"
        )


def show_credentials_dialog_legacy(window):
    """Show the legacy credentials management dialog (fallback)"""
    try:
        from termtel.widgets.credential_manager import CredentialManagerDialog

        dialog = CredentialManagerDialog(window)
        dialog.credentials_updated.connect(window.session_navigator.load_sessions)
        dialog.exec()
    except Exception as e:
        logger.error(f"Error showing legacy credentials dialog: {e}")


def safe_create_napalm_tab(window):
    """
    Safe NAPALM tab creation with theme manager registration
    """
    try:
        # Create NAPALM tab using terminal tabs system
        if hasattr(window.terminal_tabs, 'create_napalm_tab'):
            napalm_widget = window.terminal_tabs.create_napalm_tab("NAPALM Tester")

            if napalm_widget:
                # Register for theme updates (already done in create_napalm_tab)
                logger.info("NAPALM testing tab created and registered")

                # Apply current theme
                if hasattr(window, 'theme'):
                    try:
                        napalm_widget.set_theme_from_parent(window.theme)
                    except Exception as e:
                        logger.warning(f"Could not apply initial theme to NAPALM widget: {e}")
        else:
            QMessageBox.warning(window, "Error", "NAPALM tab creation not available.")

    except Exception as e:
        logger.error(f"Error creating NAPALM tab: {e}")
        QMessageBox.warning(window, "NAPALM Error", f"Could not create NAPALM tab: {str(e)}")


def safe_close_napalm_tab(window, tab_widget):
    """
    Safe cleanup when closing NAPALM tabs
    Call this when a NAPALM tab is closed
    """
    try:
        if hasattr(window, 'napalm_widgets'):
            # Remove from NAPALM widgets list
            if hasattr(tab_widget, 'napalm_widget') and tab_widget.napalm_widget in window.napalm_widgets:
                window.napalm_widgets.remove(tab_widget.napalm_widget)
            elif hasattr(tab_widget, 'set_theme_from_parent') and tab_widget in window.napalm_widgets:
                window.napalm_widgets.remove(tab_widget)

        # Call cleanup on NAPALM widget if it has one
        if hasattr(tab_widget, 'napalm_widget') and hasattr(tab_widget.napalm_widget, 'cleanup'):
            tab_widget.napalm_widget.cleanup()
        elif hasattr(tab_widget, 'cleanup'):
            tab_widget.cleanup()

    except Exception as e:
        print(f"Error during NAPALM tab cleanup: {e}")

def show_cmdb_scan_import_as_tab(window):
    """Show the CMDB scan import tool as a tab"""
    try:
        # Check if terminal_tabs exists and has the method
        if not hasattr(window, 'terminal_tabs'):
            logger.error("No terminal_tabs found on window")
            QMessageBox.warning(
                window,
                "Error",
                "Terminal tabs system not available."
            )
            return

        if not hasattr(window.terminal_tabs, 'create_cmdb_import_tab'):
            logger.error("create_cmdb_import_tab method not found")
            QMessageBox.warning(
                window,
                "Error",
                "CMDB Import tab creation not available.\nPlease check your terminal_tabs.py file."
            )
            return

        # Create CMDB import tab using the terminal tabs system
        tab_id = window.terminal_tabs.create_cmdb_import_tab("CMDB Scanner Import")
        logger.info("Created CMDB scanner import tab")
        return tab_id

    except ImportError as e:
        logger.error(f"Failed to import CMDB scanner tool: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "CMDB Scanner Import Tool module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing CMDB scanner import tool: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open CMDB Scanner Import Tool:\n{str(e)}"
        )


def show_cmdb_scan_import_window(window):
    """Show the CMDB scan import tool as a standalone window"""
    try:
        # Check if we already have an import window open
        if hasattr(window, 'cmdb_import_window') and window.cmdb_import_window:
            window.cmdb_import_window.raise_()
            window.cmdb_import_window.activateWindow()
            return

        # Import the widget
        from termtel.import_scan_ui import CMDBImportWidget

        # Create standalone window
        import_window = QWidget()
        import_window.setWindowTitle("CMDB Scanner Import Tool")
        import_window.resize(1400, 800)
        import_window.setMinimumSize(1000, 600)

        # Set proper window attributes
        import_window.setWindowFlags(Qt.WindowType.Window)
        import_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout(import_window)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create the import widget with theme manager
        import_widget = CMDBImportWidget(
            parent=import_window,
            theme_manager=getattr(window, 'theme_manager', None)
        )
        layout.addWidget(import_widget)

        # Create a custom closeEvent for cleanup
        def closeEvent(event):
            # Clear the reference when window is closed
            if hasattr(window, 'cmdb_import_window'):
                window.cmdb_import_window = None
            event.accept()
            import_window.deleteLater()

        # Override the closeEvent
        import_window.closeEvent = closeEvent

        # Store reference
        window.cmdb_import_window = import_window

        # Apply current theme
        if hasattr(window, 'theme_manager') and hasattr(window, 'theme'):
            try:
                import_widget.current_theme = window.theme
                import_widget.apply_theme()
                logger.debug(f"Applied theme {window.theme} to CMDB import tool")
            except Exception as e:
                logger.warning(f"Could not apply theme to CMDB import tool: {e}")

        import_window.show()
        logger.info("Opened CMDB scanner import tool as standalone window")

    except ImportError as e:
        logger.error(f"Failed to import CMDB scanner tool: {e}")
        QMessageBox.warning(
            window,
            "Import Error",
            "CMDB Scanner Import Tool module not available.\nPlease check your installation."
        )
    except Exception as e:
        logger.error(f"Error showing CMDB scanner import tool: {e}")
        QMessageBox.critical(
            window,
            "Error",
            f"Failed to open CMDB Scanner Import Tool:\n{str(e)}"
        )