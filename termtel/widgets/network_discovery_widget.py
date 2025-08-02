"""
Network Discovery Widget - Updated with proper theme responsiveness
"""
import os
import sys
import yaml
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QCheckBox, QSpinBox, QGroupBox, QFileDialog,
    QMessageBox, QProgressBar, QSplitter, QTabWidget,
    QFormLayout, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import (
    QThread, QProcess, QTimer, pyqtSignal,
    QProcessEnvironment, Qt, QObject
)
from PyQt6.QtGui import QFont, QTextCursor, QColor, QPalette
import logging

logger = logging.getLogger('termtel.network_discovery')


class NetworkDiscoveryProcess(QObject):
    """Handles the network discovery process execution"""

    output_received = pyqtSignal(str)
    error_received = pyqtSignal(str)
    process_finished = pyqtSignal(int, str)
    progress_updated = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.process = None
        self.is_running = False

    def start_discovery(self, command_args, working_dir=None):
        """Start the network discovery process"""
        if self.is_running:
            return False

        self.process = QProcess()
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        # Set up signal connections
        self.process.readyReadStandardOutput.connect(self._handle_output)
        self.process.finished.connect(self._handle_finished)
        self.process.errorOccurred.connect(self._handle_error)

        if working_dir:
            self.process.setWorkingDirectory(working_dir)

        # Set environment
        env = QProcessEnvironment.systemEnvironment()
        self.process.setProcessEnvironment(env)

        try:
            # Start the process
            program = sys.executable  # Use current Python interpreter
            full_args = ["-u"] + command_args  # -u for unbuffered output

            self.process.start(program, full_args)
            self.is_running = True

            if not self.process.waitForStarted(5000):
                self.error_received.emit("Failed to start discovery process")
                return False

            return True

        except Exception as e:
            self.error_received.emit(f"Error starting process: {str(e)}")
            return False

    def stop_discovery(self):
        """Stop the running discovery process"""
        if self.process and self.is_running:
            self.process.kill()
            self.process.waitForFinished(3000)
            self.is_running = False

    def _handle_output(self):
        """Handle stdout/stderr output from the process"""
        if self.process:
            data = self.process.readAllStandardOutput()
            text = bytes(data).decode('utf-8', errors='replace')
            if text.strip():
                self.output_received.emit(text)

    def _handle_finished(self, exit_code, exit_status):
        """Handle process completion"""
        self.is_running = False
        status_text = "completed successfully" if exit_code == 0 else f"failed with code {exit_code}"
        self.process_finished.emit(exit_code, status_text)

    def _handle_error(self, error):
        """Handle process errors"""
        self.is_running = False
        error_messages = {
            QProcess.ProcessError.FailedToStart: "Failed to start process",
            QProcess.ProcessError.Crashed: "Process crashed",
            QProcess.ProcessError.Timedout: "Process timed out",
            QProcess.ProcessError.WriteError: "Write error",
            QProcess.ProcessError.ReadError: "Read error",
            QProcess.ProcessError.UnknownError: "Unknown error"
        }
        self.error_received.emit(error_messages.get(error, "Unknown process error"))


class NetworkDiscoveryWidget(QWidget):
    """Main widget for network discovery tool - with proper theme responsiveness"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.discovery_process = NetworkDiscoveryProcess()
        self.config_file_path = None

        # Set size policy to expand in both directions
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Set up the UI
        self.setup_ui()
        self.setup_connections()
        self.load_default_config()

        # Store reference to theme manager and current theme
        self.theme_manager = None
        self.current_theme = None

        # Apply theme if parent has theme manager
        if hasattr(parent, 'theme_manager') and hasattr(parent, 'theme'):
            self.theme_manager = parent.theme_manager
            self.current_theme = parent.theme
            try:
                self.apply_theme(parent.theme_manager, parent.theme)
            except Exception as e:
                logger.warning(f"Could not apply initial theme: {e}")

        # Connect to parent's theme changes if available
        if hasattr(parent, 'theme_changed'):
            parent.theme_changed.connect(self.on_theme_changed)

    def on_theme_changed(self, theme_name):
        """Handle theme change signal from parent"""
        try:
            if self.theme_manager:
                self.apply_theme(self.theme_manager, theme_name)
            logger.debug(f"Applied theme {theme_name} to Network Discovery widget")
        except Exception as e:
            logger.error(f"Failed to apply theme {theme_name}: {e}")

    def apply_theme(self, theme_manager, theme_name):
        """Apply theme to this widget and all its components"""
        try:
            # Store current theme info
            self.theme_manager = theme_manager
            self.current_theme = theme_name

            # Get theme colors for custom styling (don't call apply_theme to avoid recursion)
            colors = theme_manager.get_colors(theme_name)

            # Apply base theme using stylesheet directly
            theme = theme_manager.get_theme(theme_name)
            if theme:
                stylesheet = theme_manager.generate_stylesheet(theme)
                self.setStyleSheet(stylesheet)

            # Apply custom styling to output text area for better visibility
            if hasattr(self, 'output_text') and colors:
                output_style = f"""
                QTextEdit {{
                    background-color: {colors.get('background', '#1e1e1e')};
                    color: {colors.get('text', '#ffffff')};
                    border: 1px solid {colors.get('border', '#444444')};
                    font-family: 'Courier New', monospace;
                    font-size: 9pt;
                }}
                """
                self.output_text.setStyleSheet(output_style)

            # Apply custom styling to config preview
            if hasattr(self, 'config_preview') and colors:
                preview_style = f"""
                QTextEdit {{
                    background-color: {colors.get('background', '#1e1e1e')};
                    color: {colors.get('text', '#ffffff')};
                    border: 1px solid {colors.get('border', '#444444')};
                    font-family: 'Courier New', monospace;
                    font-size: 9pt;
                }}
                """
                self.config_preview.setStyleSheet(preview_style)

            # Apply enhanced styling to buttons for better theme consistency
            if colors:
                # Create enhanced button styling that will override the base theme
                button_style = f"""
                QPushButton {{
                    background-color: {colors.get('button_bg', colors.get('darker_bg', '#333333'))};
                    color: {colors.get('button_text', colors.get('text', '#ffffff'))};
                    border: 1px solid {colors.get('border_light', colors.get('border', '#444444'))};
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {colors.get('button_hover', colors.get('primary', '#444444'))} !important;
                    border: 1px solid {colors.get('text', '#ffffff')} !important;
                }}
                QPushButton:pressed {{
                    background-color: {colors.get('button_pressed', colors.get('secondary', '#222222'))} !important;
                }}
                QPushButton:disabled {{
                    background-color: {colors.get('disabled', colors.get('grid', '#555555'))} !important;
                    color: {colors.get('disabled_text', colors.get('border', '#888888'))} !important;
                    border: 1px solid {colors.get('border', '#666666')} !important;
                }}
                """

                # Apply enhanced styling to all buttons with !important to override base theme
                for button in self.findChildren(QPushButton):
                    button.setStyleSheet(button_style)

                # Also apply to input fields for consistency
                input_style = f"""
                QLineEdit, QTextEdit {{
                    background-color: {colors.get('darker_bg', '#1a1a1a')};
                    border: 1px solid {colors.get('border_light', '#444444')};
                    color: {colors.get('text', '#ffffff')};
                    padding: 5px;
                    border-radius: 2px;
                }}
                QLineEdit:focus, QTextEdit:focus {{
                    border: 2px solid {colors.get('primary', '#0a8993')};
                }}
                """

                # Apply to input fields
                for widget in self.findChildren(QLineEdit):
                    widget.setStyleSheet(input_style)
                for widget in self.findChildren(QTextEdit):
                    if widget != self.output_text and widget != self.config_preview:
                        widget.setStyleSheet(input_style)

            logger.debug(f"Successfully applied theme {theme_name} to Network Discovery widget")

        except Exception as e:
            logger.error(f"Error applying theme {theme_name}: {e}")

    def setup_ui(self):
        """Set up the user interface with full space utilization"""
        # Main layout with no margins to use full space
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)  # Minimal margins
        layout.setSpacing(5)

        # Create splitter for main content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(splitter)

        # Left panel - Configuration (fixed width, expandable height)
        config_widget = self.create_config_panel()
        splitter.addWidget(config_widget)

        # Right panel - Output and control (expandable in both directions)
        output_widget = self.create_output_panel()
        splitter.addWidget(output_widget)

        # Set splitter proportions - give more space to output
        splitter.setSizes([350, 850])  # Adjusted for better proportion
        splitter.setStretchFactor(0, 0)  # Config panel doesn't stretch
        splitter.setStretchFactor(1, 1)  # Output panel stretches

        # Status bar
        self.create_status_bar(layout)

    def create_config_panel(self):
        """Create the configuration panel with proper sizing"""
        # Main container with size policy
        main_widget = QWidget()
        main_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        main_widget.setMinimumWidth(340)
        main_widget.setMaximumWidth(380)

        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Configuration tabs
        tab_widget = QTabWidget()
        tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Basic Configuration Tab
        basic_tab = self.create_basic_config_tab()
        tab_widget.addTab(basic_tab, "Basic Config")

        # Advanced Configuration Tab
        advanced_tab = self.create_advanced_config_tab()
        tab_widget.addTab(advanced_tab, "Advanced")

        # File Configuration Tab
        file_tab = self.create_file_config_tab()
        tab_widget.addTab(file_tab, "File Config")

        main_layout.addWidget(tab_widget)

        return main_widget

    def create_basic_config_tab(self):
        """Create basic configuration tab with scroll area"""
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Scroll widget content
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Network Configuration Group
        network_group = QGroupBox("Network Configuration")
        network_layout = QFormLayout(network_group)
        network_layout.setContentsMargins(10, 10, 10, 10)

        self.seed_ip_edit = QLineEdit()
        self.seed_ip_edit.setPlaceholderText("192.168.1.1")
        network_layout.addRow("Seed IP:", self.seed_ip_edit)

        self.domain_edit = QLineEdit()
        self.domain_edit.setPlaceholderText("example.com")
        network_layout.addRow("Domain Name:", self.domain_edit)

        layout.addWidget(network_group)

        # Authentication Group
        auth_group = QGroupBox("Authentication")
        auth_layout = QFormLayout(auth_group)
        auth_layout.setContentsMargins(10, 10, 10, 10)

        self.username_edit = QLineEdit()
        auth_layout.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        auth_layout.addRow("Password:", self.password_edit)

        self.alt_username_edit = QLineEdit()
        auth_layout.addRow("Alt Username:", self.alt_username_edit)

        self.alt_password_edit = QLineEdit()
        self.alt_password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        auth_layout.addRow("Alt Password:", self.alt_password_edit)

        layout.addWidget(auth_group)

        # Discovery Parameters Group
        params_group = QGroupBox("Discovery Parameters")
        params_layout = QFormLayout(params_group)
        params_layout.setContentsMargins(10, 10, 10, 10)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setValue(30)
        self.timeout_spin.setSuffix(" seconds")
        params_layout.addRow("Timeout:", self.timeout_spin)

        self.max_devices_spin = QSpinBox()
        self.max_devices_spin.setRange(1, 10000)
        self.max_devices_spin.setValue(100)
        params_layout.addRow("Max Devices:", self.max_devices_spin)

        self.layout_combo = QComboBox()
        self.layout_combo.addItems(["kk", "spring", "circular", "random"])
        params_layout.addRow("Layout Algorithm:", self.layout_combo)

        layout.addWidget(params_group)

        layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        return scroll_area

    def create_advanced_config_tab(self):
        """Create advanced configuration tab with scroll area"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Output Configuration Group
        output_group = QGroupBox("Output Configuration")
        output_layout = QFormLayout(output_group)
        output_layout.setContentsMargins(10, 10, 10, 10)

        # Output directory selection
        output_dir_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setPlaceholderText("Select output directory...")
        self.output_dir_btn = QPushButton("Browse")
        self.output_dir_btn.clicked.connect(self.select_output_directory)
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(self.output_dir_btn)
        output_layout.addRow("Output Directory:", output_dir_layout)

        self.map_name_edit = QLineEdit()
        self.map_name_edit.setPlaceholderText("network_map")
        output_layout.addRow("Map Name:", self.map_name_edit)

        layout.addWidget(output_group)

        # Exclusion Configuration Group
        exclusion_group = QGroupBox("Exclusion Configuration")
        exclusion_layout = QVBoxLayout(exclusion_group)
        exclusion_layout.setContentsMargins(10, 10, 10, 10)

        exclusion_layout.addWidget(QLabel("Exclude Strings (comma-separated):"))
        self.exclude_edit = QTextEdit()
        self.exclude_edit.setMaximumHeight(80)
        self.exclude_edit.setPlaceholderText("router1,switch2,device3")
        exclusion_layout.addWidget(self.exclude_edit)

        layout.addWidget(exclusion_group)

        # Debug Options Group
        debug_group = QGroupBox("Debug Options")
        debug_layout = QVBoxLayout(debug_group)
        debug_layout.setContentsMargins(10, 10, 10, 10)

        self.debug_checkbox = QCheckBox("Save Debug Information")
        debug_layout.addWidget(self.debug_checkbox)

        layout.addWidget(debug_group)

        layout.addStretch()

        scroll_area.setWidget(scroll_widget)
        return scroll_area

    def create_file_config_tab(self):
        """Create file configuration tab with scroll area"""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Config file group
        config_group = QGroupBox("Configuration File")
        config_layout = QVBoxLayout(config_group)
        config_layout.setContentsMargins(10, 10, 10, 10)

        # Config file selection
        file_layout = QHBoxLayout()
        self.config_file_edit = QLineEdit()
        self.config_file_edit.setPlaceholderText("Select YAML configuration file...")
        self.config_file_btn = QPushButton("Browse")
        self.config_file_btn.clicked.connect(self.select_config_file)
        file_layout.addWidget(self.config_file_edit)
        file_layout.addWidget(self.config_file_btn)
        config_layout.addLayout(file_layout)

        # Config file actions
        actions_layout = QHBoxLayout()
        self.load_config_btn = QPushButton("Load Config")
        self.load_config_btn.clicked.connect(self.load_config_file)
        self.save_config_btn = QPushButton("Save Config")
        self.save_config_btn.clicked.connect(self.save_config_file)
        actions_layout.addWidget(self.load_config_btn)
        actions_layout.addWidget(self.save_config_btn)
        config_layout.addLayout(actions_layout)

        layout.addWidget(config_group)

        # Config preview - this should expand
        preview_group = QGroupBox("Configuration Preview")
        preview_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(10, 10, 10, 10)

        self.config_preview = QTextEdit()
        self.config_preview.setFont(QFont("Courier", 9))
        self.config_preview.setReadOnly(True)
        self.config_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_layout.addWidget(self.config_preview)

        layout.addWidget(preview_group)

        scroll_area.setWidget(scroll_widget)
        return scroll_area

    def create_output_panel(self):
        """Create the output and control panel with full expansion"""
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Control buttons
        control_layout = QHBoxLayout()
        control_layout.setSpacing(10)

        self.start_btn = QPushButton("Start Discovery")
        self.start_btn.clicked.connect(self.start_discovery)

        self.stop_btn = QPushButton("Stop Discovery")
        self.stop_btn.clicked.connect(self.stop_discovery)
        self.stop_btn.setEnabled(False)

        self.clear_btn = QPushButton("Clear Output")
        self.clear_btn.clicked.connect(self.clear_output)

        self.save_output_btn = QPushButton("Save Output")
        self.save_output_btn.clicked.connect(self.save_output)

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addStretch()
        control_layout.addWidget(self.clear_btn)
        control_layout.addWidget(self.save_output_btn)

        layout.addLayout(control_layout)

        # Output text area - this should expand to fill remaining space
        output_group = QGroupBox("Discovery Output")
        output_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        output_layout = QVBoxLayout(output_group)
        output_layout.setContentsMargins(10, 10, 10, 10)

        self.output_text = QTextEdit()
        self.output_text.setFont(QFont("Courier", 9))
        self.output_text.setReadOnly(True)
        self.output_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Set minimum size to ensure it's visible
        self.output_text.setMinimumHeight(300)
        output_layout.addWidget(self.output_text)

        layout.addWidget(output_group)

        return widget

    def create_status_bar(self, parent_layout):
        """Create status bar"""
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(5, 2, 5, 2)

        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(20)

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.progress_bar)

        parent_layout.addLayout(status_layout)

    def setup_connections(self):
        """Set up signal connections"""
        self.discovery_process.output_received.connect(self.append_output)
        self.discovery_process.error_received.connect(self.append_error)
        self.discovery_process.process_finished.connect(self.on_discovery_finished)
        self.discovery_process.progress_updated.connect(self.progress_bar.setValue)

    # Rest of the methods remain the same...
    def load_default_config(self):
        """Load default configuration values"""
        default_config = {
            'seed_ip': '',
            'username': '',
            'password': '',
            'alternate_username': '',
            'alternate_password': '',
            'domain_name': '',
            'exclude_string': '',
            'output_dir': str(Path.home() / 'network_discovery'),
            'timeout': 30,
            'max_devices': 100,
            'save_debug_info': False,
            'map_name': 'network_map',
            'layout_algo': 'kk'
        }
        self.update_ui_from_config(default_config)
        self.update_config_preview()

    def get_current_config(self):
        """Get current configuration from UI"""
        config = {
            'seed_ip': self.seed_ip_edit.text().strip(),
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text(),
            'alternate_username': self.alt_username_edit.text().strip(),
            'alternate_password': self.alt_password_edit.text(),
            'domain_name': self.domain_edit.text().strip(),
            'exclude_string': self.exclude_edit.toPlainText().strip(),
            'output_dir': self.output_dir_edit.text().strip(),
            'timeout': self.timeout_spin.value(),
            'max_devices': self.max_devices_spin.value(),
            'save_debug_info': self.debug_checkbox.isChecked(),
            'map_name': self.map_name_edit.text().strip() or 'network_map',
            'layout_algo': self.layout_combo.currentText()
        }
        return config

    def update_ui_from_config(self, config):
        """Update UI elements from configuration"""
        self.seed_ip_edit.setText(config.get('seed_ip', ''))
        self.username_edit.setText(config.get('username', ''))
        self.password_edit.setText(config.get('password', ''))
        self.alt_username_edit.setText(config.get('alternate_username', ''))
        self.alt_password_edit.setText(config.get('alternate_password', ''))
        self.domain_edit.setText(config.get('domain_name', ''))
        self.exclude_edit.setPlainText(config.get('exclude_string', ''))
        self.output_dir_edit.setText(config.get('output_dir', ''))
        self.timeout_spin.setValue(config.get('timeout', 30))
        self.max_devices_spin.setValue(config.get('max_devices', 100))
        self.debug_checkbox.setChecked(config.get('save_debug_info', False))
        self.map_name_edit.setText(config.get('map_name', 'network_map'))

        layout_algo = config.get('layout_algo', 'kk')
        index = self.layout_combo.findText(layout_algo)
        if index >= 0:
            self.layout_combo.setCurrentIndex(index)

    def update_config_preview(self):
        """Update configuration preview"""
        config = self.get_current_config()
        # Remove password fields for preview
        preview_config = config.copy()
        if preview_config.get('password'):
            preview_config['password'] = '***'
        if preview_config.get('alternate_password'):
            preview_config['alternate_password'] = '***'

        yaml_text = yaml.dump(preview_config, default_flow_style=False, sort_keys=True)
        self.config_preview.setPlainText(yaml_text)

    def select_output_directory(self):
        """Select output directory"""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.output_dir_edit.text()
        )
        if directory:
            self.output_dir_edit.setText(directory)
            self.update_config_preview()

    def select_config_file(self):
        """Select configuration file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Configuration File", "", "YAML Files (*.yaml *.yml);;All Files (*)"
        )
        if file_path:
            self.config_file_edit.setText(file_path)
            self.config_file_path = file_path

    def load_config_file(self):
        """Load configuration from file"""
        if not self.config_file_path:
            if not self.config_file_edit.text():
                QMessageBox.warning(self, "Warning", "Please select a configuration file first.")
                return
            self.config_file_path = self.config_file_edit.text()

        try:
            with open(self.config_file_path, 'r') as f:
                config = yaml.safe_load(f)

            self.update_ui_from_config(config)
            self.update_config_preview()
            self.status_label.setText(f"Loaded config from {os.path.basename(self.config_file_path)}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load configuration file:\n{str(e)}")

    def save_config_file(self):
        """Save current configuration to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Configuration File", "network_discovery_config.yaml",
            "YAML Files (*.yaml *.yml);;All Files (*)"
        )

        if file_path:
            try:
                config = self.get_current_config()
                with open(file_path, 'w') as f:
                    yaml.dump(config, f, default_flow_style=False, sort_keys=True)

                self.status_label.setText(f"Saved config to {os.path.basename(file_path)}")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save configuration file:\n{str(e)}")

    def build_command_args(self):
        """Build command line arguments from current configuration"""
        config = self.get_current_config()
        args = []

        # Use sc.py as the script name - adjust path as needed
        script_path = "sc.py"  # You may need to adjust this path
        args.append(script_path)

        # Add configuration arguments
        if config['seed_ip']:
            args.extend(['--seed-ip', config['seed_ip']])

        if config['username']:
            args.extend(['--username', config['username']])

        if config['password']:
            args.extend(['--password', config['password']])

        if config['alternate_username']:
            args.extend(['--alternate-username', config['alternate_username']])

        if config['alternate_password']:
            args.extend(['--alternate-password', config['alternate_password']])

        if config['domain_name']:
            args.extend(['--domain-name', config['domain_name']])

        if config['exclude_string']:
            args.extend(['--exclude-string', config['exclude_string']])

        if config['output_dir']:
            args.extend(['--output-dir', config['output_dir']])

        args.extend(['--timeout', str(config['timeout'])])
        args.extend(['--max-devices', str(config['max_devices'])])

        if config['save_debug_info']:
            args.append('--save-debug-info')

        if config['map_name']:
            args.extend(['--map-name', config['map_name']])

        args.extend(['--layout-algo', config['layout_algo']])

        return args

    def start_discovery(self):
        """Start the network discovery process"""
        # Validate required fields
        config = self.get_current_config()
        if not config['seed_ip']:
            QMessageBox.warning(self, "Warning", "Please enter a seed IP address.")
            return

        if not config['username']:
            QMessageBox.warning(self, "Warning", "Please enter a username.")
            return

        # Create output directory if it doesn't exist
        if config['output_dir']:
            try:
                Path(config['output_dir']).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create output directory:\n{str(e)}")
                return

        # Build command arguments
        try:
            args = self.build_command_args()
            # self.append_output(f"Starting discovery with command: {' '.join(args)}\n")
            self.append_output(f"Starting discovery ...\n")
            # Start the process
            if self.discovery_process.start_discovery(args):
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.progress_bar.setVisible(True)
                self.progress_bar.setRange(0, 0)  # Indeterminate progress
                self.status_label.setText("Discovery running...")
            else:
                QMessageBox.critical(self, "Error", "Failed to start discovery process.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start discovery:\n{str(e)}")

    def stop_discovery(self):
        """Stop the running discovery process"""
        self.discovery_process.stop_discovery()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Discovery stopped")
        self.append_output("\n--- Discovery stopped by user ---\n")

    def append_output(self, text):
        """Append text to output area"""
        self.output_text.moveCursor(QTextCursor.MoveOperation.End)
        self.output_text.insertPlainText(text)
        self.output_text.moveCursor(QTextCursor.MoveOperation.End)
        self.update_config_preview()

    def append_error(self, text):
        """Append error text to output area"""
        self.output_text.moveCursor(QTextCursor.MoveOperation.End)
        self.output_text.setTextColor(QColor("red"))
        self.output_text.insertPlainText(f"ERROR: {text}\n")
        self.output_text.setTextColor(QColor("white"))  # Reset color
        self.output_text.moveCursor(QTextCursor.MoveOperation.End)

    def on_discovery_finished(self, exit_code, status_text):
        """Handle discovery process completion"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Discovery {status_text}")

        self.append_output(f"\n--- Discovery {status_text} ---\n")

        if exit_code == 0:
            # Optionally open output directory
            config = self.get_current_config()
            if config['output_dir'] and os.path.exists(config['output_dir']):
                reply = QMessageBox.question(
                    self, "Discovery Complete",
                    f"Discovery completed successfully!\n\nOpen output directory?\n{config['output_dir']}",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    os.startfile(config['output_dir']) if os.name == 'nt' else os.system(f'open "{config["output_dir"]}"')

    def clear_output(self):
        """Clear the output text area"""
        self.output_text.clear()
        self.status_label.setText("Output cleared")

    def save_output(self):
        """Save output to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Output", "discovery_output.txt", "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(self.output_text.toPlainText())
                self.status_label.setText(f"Output saved to {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save output:\n{str(e)}")

    def cleanup(self):
        """Cleanup method for proper resource management"""
        try:
            # Disconnect from theme changes if connected
            if hasattr(self.parent_window, 'theme_changed'):
                try:
                    self.parent_window.theme_changed.disconnect(self.on_theme_changed)
                except:
                    pass  # May not be connected

            # Stop any running discovery process
            if hasattr(self, 'discovery_process'):
                self.discovery_process.stop_discovery()

            # Wait a moment for process cleanup
            import time
            time.sleep(0.1)

            logger.info("Network discovery widget cleaned up")

        except Exception as e:
            logger.error(f"Error during network discovery cleanup: {e}")


class NetworkDiscoveryDialog(QWidget):
    """Standalone dialog wrapper for the network discovery widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Network Discovery Tool")
        self.resize(1200, 800)

        layout = QVBoxLayout(self)
        self.discovery_widget = NetworkDiscoveryWidget(parent)
        layout.addWidget(self.discovery_widget)

        # Apply theme if parent has theme manager
        if hasattr(parent, 'theme_manager') and hasattr(parent, 'theme'):
            try:
                parent.theme_manager.apply_theme(self, parent.theme)
            except Exception as e:
                logger.warning(f"Could not apply theme: {e}")