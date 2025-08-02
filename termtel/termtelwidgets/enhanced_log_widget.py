"""
Simplified Log Viewer Widget - Raw Lines Only (Compatible Compact Layout)
No parsing, just displays log lines as received from the device
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QTextEdit, QPushButton, QSpinBox, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QFont
import time

# Import your template editing mixin
from termtel.termtelwidgets.normalized_widgets import TemplateEditableWidget


class SimplifiedLogWidget(TemplateEditableWidget, QWidget):
    """Simplified log widget that just displays raw log lines"""

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'log_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library
        self.max_lines = 1000
        self.auto_scroll = True

        # Connect to controller signals
        self._connect_controller_signals()
        self._setup_widget()

    def _connect_controller_signals(self):
        """Connect to controller signals"""
        print(" Connecting Simplified Log widget signals...")

        # Primary log signal
        if hasattr(self.controller, 'raw_log_output'):
            self.controller.raw_log_output.connect(self.process_raw_log_output)
            print(" Connected to raw_log_output")
        else:
            print(" raw_log_output signal not found")

        # Other useful signals
        other_signals = [
            ('theme_changed', self.on_theme_changed),
            ('connection_status_changed', self._on_connection_status_changed),
            ('device_info_updated', self._on_device_info_updated)
        ]

        for signal_name, handler in other_signals:
            if hasattr(self.controller, signal_name):
                signal = getattr(self.controller, signal_name)
                signal.connect(handler)
                print(f" Connected to {signal_name}")

    def _setup_widget(self):
        """Setup the widget UI - Compact horizontal layout"""
        layout = QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(6, 4, 6, 4)

        # === LEFT SIDE: Compact Controls Panel ===
        controls_panel = self._create_compact_controls_panel()
        controls_panel.setFixedWidth(200)
        layout.addWidget(controls_panel)

        # === RIGHT SIDE: Log Display ===
        log_section = self._create_log_display()
        layout.addWidget(log_section, 1)

    def _create_compact_controls_panel(self):
        """Create compact controls panel - all essential elements"""
        controls_frame = QWidget()
        controls_frame.setObjectName("controls_frame")

        layout = QVBoxLayout(controls_frame)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 4, 6, 4)

        # === TITLE ROW ===
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel(" SYSTEM LOGS")
        self.title_label.setObjectName("section_title")
        title_row.addWidget(self.title_label)

        layout.addLayout(title_row)

        # === STATUS BADGE ===
        self.data_source_label = QLabel("Raw")
        self.data_source_label.setObjectName("status_badge")
        self.data_source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.data_source_label.setMaximumHeight(20)
        # layout.addWidget(self.data_source_label)

        # === PLATFORM INFO (Required by original code) ===
        platform_row = QHBoxLayout()
        platform_row.setContentsMargins(0, 0, 0, 0)

        platform_icon = QLabel("")
        platform_icon.setObjectName("status_icon")
        platform_row.addWidget(platform_icon)

        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setObjectName("status_label")
        self.platform_label.setWordWrap(True)
        platform_row.addWidget(self.platform_label, 1)

        # layout.addLayout(platform_row)

        # === CONTROLS ROW ===
        controls_row = QHBoxLayout()
        controls_row.setContentsMargins(0, 2, 0, 2)
        controls_row.setSpacing(4)

        # Auto-scroll checkbox
        self.auto_scroll_check = QCheckBox("Auto")
        self.auto_scroll_check.setObjectName("checkbox_control")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.toggled.connect(self._toggle_auto_scroll)
        controls_row.addWidget(self.auto_scroll_check)

        # Refresh button
        self.refresh_button = QPushButton("")
        self.refresh_button.setObjectName("primary_button")
        self.refresh_button.setFixedSize(22, 22)
        self.refresh_button.setToolTip("Refresh logs")
        self.refresh_button.clicked.connect(self._request_refresh)
        # controls_row.addWidget(self.refresh_button)

        layout.addLayout(controls_row)

        # === ACTION BUTTONS ROW ===
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)

        # Option 1: Clickable text links (more compact and elegant)
        self.clear_button = QLabel('<a href="#" style="color: #ff6b6b; text-decoration: none;">Clear</a>')
        self.clear_button.setObjectName("link_button")
        self.clear_button.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clear_button.linkActivated.connect(self._clear_logs)
        self.clear_button.setToolTip("Clear logs")
        actions_row.addWidget(self.clear_button)

        self.export_button = QLabel('<a href="#" style="color: #4dabf7; text-decoration: none;">Export</a>')
        self.export_button.setObjectName("link_button")
        self.export_button.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.export_button.linkActivated.connect(self._export_logs)
        self.export_button.setToolTip("Export logs")
        actions_row.addWidget(self.export_button)

        # Alternative Option 2: Small icon buttons (uncomment if you prefer buttons)
        # self.clear_button = QPushButton(" Clear")
        # self.clear_button.setObjectName("danger_button")
        # self.clear_button.setFixedHeight(20)
        # self.clear_button.setToolTip("Clear logs")
        # self.clear_button.clicked.connect(self._clear_logs)
        # actions_row.addWidget(self.clear_button)

        # self.export_button = QPushButton(" Export")
        # self.export_button.setObjectName("secondary_button")
        # self.export_button.setFixedHeight(20)
        # self.export_button.setToolTip("Export logs")
        # self.export_button.clicked.connect(self._export_logs)
        # actions_row.addWidget(self.export_button)

        layout.addLayout(actions_row)

        # === STATS (Required by original code) ===
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(2)

        # Line count
        lines_row = QHBoxLayout()
        lines_row.setContentsMargins(0, 0, 0, 0)

        lines_icon = QLabel("")
        lines_icon.setObjectName("status_icon")
        lines_row.addWidget(lines_icon)

        self.lines_count_label = QLabel("Lines: 0")
        self.lines_count_label.setObjectName("metric_label")
        lines_row.addWidget(self.lines_count_label, 1)

        # stats_layout.addLayout(lines_row)

        # Update time (Required by original code)
        time_row = QHBoxLayout()
        time_row.setContentsMargins(0, 0, 0, 0)

        time_icon = QLabel("")
        time_icon.setObjectName("status_icon")
        time_row.addWidget(time_icon)

        self.update_time_label = QLabel("Last Update: Never")
        self.update_time_label.setObjectName("timestamp_label")
        self.update_time_label.setWordWrap(True)
        time_row.addWidget(self.update_time_label, 1)

        stats_layout.addLayout(time_row)
        layout.addLayout(stats_layout)

        # Add some stretch to keep everything compact at top
        layout.addStretch()

        return controls_frame

    def _create_log_display(self):
        """Create enhanced log display with better styling - THEME AWARE"""
        log_frame = QWidget()
        log_frame.setObjectName("log_display_frame")

        layout = QVBoxLayout(log_frame)
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(2)

        # Minimal header
        header_row = QHBoxLayout()
        header_row.setContentsMargins(2, 0, 2, 0)

        log_title = QLabel("Log Output")
        log_title.setObjectName("control_label")
        header_row.addWidget(log_title)
        header_row.addStretch()

        layout.addLayout(header_row)

        # Main log display
        self.log_display = QTextEdit()
        self.log_display.setObjectName("log_text_display")
        self.log_display.setReadOnly(True)
        self.log_display.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        # Use monospace font for better log readability
        font = QFont("Consolas", 9)
        if not font.exactMatch():
            font = QFont("Courier New", 9)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 105)
        self.log_display.setFont(font)

        layout.addWidget(self.log_display)
        return log_frame

    # === REQUIRED METHODS FROM ORIGINAL (Keep compatibility) ===

    def update_data_source_status(self, status_type):
        """Update data source badge with theme-aware colors"""
        if status_type == "raw":
            self.data_source_label.setText("Raw")
            self.data_source_label.setObjectName("status_badge_warning")
            self.data_source_label.setProperty("status", "warning")
        elif status_type == "normalized":
            self.data_source_label.setText("Normalized")
            self.data_source_label.setObjectName("status_badge_success")
            self.data_source_label.setProperty("status", "success")
        elif status_type == "error":
            self.data_source_label.setText("Error")
            self.data_source_label.setObjectName("status_badge_error")
            self.data_source_label.setProperty("status", "error")
        else:
            self.data_source_label.setText("Waiting...")
            self.data_source_label.setObjectName("status_badge")
            self.data_source_label.setProperty("status", "neutral")

        # Force style refresh
        self.data_source_label.style().unpolish(self.data_source_label)
        self.data_source_label.style().polish(self.data_source_label)

    def _export_logs(self, *args):
        """Export logs to file - Updated for link compatibility"""
        try:
            from PyQt6.QtWidgets import QFileDialog
            import os

            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export Logs",
                f"system_logs_{time.strftime('%Y%m%d_%H%M%S')}.txt",
                "Text Files (*.txt);;All Files (*)"
            )

            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_display.toPlainText())

                # Show success message
                original_text = self.export_button.text()

                self.export_button.setText('<a href="#" style="color: #51cf66; text-decoration: none;"> Saved!</a>')

                # Reset after 2 seconds
                QTimer.singleShot(2000, lambda: self.export_button.setText(original_text))

        except Exception as e:
            print(f" Export failed: {e}")
            # Show error state
            original_text = self.export_button.text()
            self.export_button.setText('<a href="#" style="color: #ff6b6b; text-decoration: none;"> Failed!</a>')
            QTimer.singleShot(2000, lambda: self.export_button.setText(original_text))

    def _reset_export_button(self, original_text, original_class):
        """Reset export button to original state - Removed since using links now"""
        pass

    @pyqtSlot(object)
    def process_raw_log_output(self, raw_output):
        """Process raw log output - SIMPLE: Replace content, don't append"""
        print(f" Processing raw log output: {raw_output.command}")
        print(f" Raw output length: {len(raw_output.output)} characters")

        # Update status with theme-aware colors (Required by original)
        command_short = raw_output.command.split()[-1] if raw_output.command else "logs"
        self.platform_label.setText(f"Platform: {raw_output.platform} | Command: {command_short}")

        # Use theme-aware status update
        self.update_data_source_status("raw")

        # SIMPLE: Just replace the content entirely - no processing, no appending
        if raw_output.output and raw_output.output.strip():
            # Clear and replace with new content
            timestamp = time.strftime("%H:%M:%S")
            header = f"=== Log Output Retrieved at {timestamp} ===\n\n"

            # Set the raw output directly - REPLACE, don't append
            self.log_display.setPlainText(header + raw_output.output)

            # Count lines for display
            line_count = len(raw_output.output.split('\n'))
            self.lines_count_label.setText(f"Lines: {line_count}")

            print(f" Replaced display with {line_count} raw lines")
        else:
            # No output received
            timestamp = time.strftime("%H:%M:%S")
            self.log_display.setPlainText(f"[{timestamp}] No log output received from device")
            self.lines_count_label.setText("Lines: 0")
            print(f" No log output received")

        if self.auto_scroll:
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            print(f" Auto-scrolled to bottom")

        self._update_timestamp()

    def _should_skip_line(self, line: str) -> bool:
        """Determine if a line should be skipped"""
        # Skip empty lines, command echoes, and common noise
        skip_patterns = [
            "",  # Empty lines
            "show logging",  # Command echo
            "Building configuration",  # Cisco noise
            "Current configuration",  # Cisco noise
            "!",  # Comment lines
            "#",  # Prompt characters
            "---",  # Separators
            "===",  # Separators
        ]

        line_lower = line.lower().strip()

        for pattern in skip_patterns:
            if pattern and (line_lower == pattern.lower() or line_lower.startswith(pattern.lower())):
                return True

        # Skip very short lines (likely noise)
        if len(line.strip()) < 3:
            return True

        return False

    def _trim_to_max_lines(self):
        """Remove this method - not needed when replacing content"""
        pass  # Do nothing - we replace content entirely

    def _toggle_auto_scroll(self, enabled: bool):
        """Toggle auto-scroll functionality"""
        self.auto_scroll = enabled

    def _update_max_lines(self, max_lines: int):
        """Update maximum log lines - informational only since we replace content"""
        self.max_lines = max_lines
        # No trimming needed since we replace content entirely

    def _clear_logs(self, *args):
        """Clear all log entries - Updated for link compatibility"""
        self.log_display.clear()
        self.lines_count_label.setText("Lines: 0")

    def _request_refresh(self):
        """Request log data refresh"""
        if hasattr(self.controller, 'collect_telemetry_data'):
            self.controller.collect_telemetry_data()

    def _update_timestamp(self):
        """Update the last update timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_time_label.setText(f"Last Update: {timestamp}")

    @pyqtSlot(str, str)
    def _on_connection_status_changed(self, device_ip, status):
        """Handle connection status changes"""
        if status == "disconnected":
            self.platform_label.setText("Platform: Disconnected")

    @pyqtSlot(object)
    def _on_device_info_updated(self, device_info):
        """Handle device info updates"""
        if hasattr(device_info, 'platform'):
            self.platform_label.setText(f"Platform: {device_info.platform}")

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes - ENHANCED VERSION"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)

            # Force refresh of all dynamic elements
            for widget in [self.data_source_label, self.export_button]:
                widget.style().unpolish(widget)
                widget.style().polish(widget)


# Even simpler version if you want the absolute minimum
class MinimalLogWidget(TemplateEditableWidget, QWidget):
    """Minimal log widget - just a text area with gear button"""

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'log_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library

        # Connect to log signal
        if hasattr(self.controller, 'raw_log_output'):
            self.controller.raw_log_output.connect(self.process_raw_log_output)
        if hasattr(self.controller, 'theme_changed'):
            self.controller.theme_changed.connect(self.on_theme_changed)

        self._setup_widget()

    def _setup_widget(self):
        """Setup minimal widget"""
        layout = QVBoxLayout(self)

        # Title with gear button
        title_layout = QHBoxLayout()

        title = QLabel("SYSTEM LOGS")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title)

        title_layout.addStretch()
        title_layout.addWidget(self.gear_button)

        layout.addLayout(title_layout)

        # Simple text display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        font = QFont("Consolas", 9)
        self.log_display.setFont(font)
        layout.addWidget(self.log_display)

    @pyqtSlot(object)
    def process_raw_log_output(self, raw_output):
        """Process raw log output"""
        if raw_output.output and raw_output.output.strip():
            timestamp = time.strftime("%H:%M:%S")
            header = f"=== Log Output Retrieved at {timestamp} ===\n\n"
            self.log_display.setPlainText(header + raw_output.output)

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)