"""
FIXED: Platform-Agnostic CPU/Environment Widget
Uses your existing normalized data pattern instead of Cisco-specific fields
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QProgressBar, QPushButton, QTextEdit, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from typing import List, Dict, Optional
import time
from dataclasses import dataclass

# Import your template editing mixin
from termtel.termtelwidgets.normalized_widgets import TemplateEditableWidget


@dataclass
class NormalizedSystemMetrics:
    """Platform-agnostic system metrics structure"""
    cpu_usage_percent: float = 0.0
    memory_used_percent: float = 0.0
    memory_total_mb: int = 0
    memory_free_mb: int = 0
    memory_used_mb: int = 0
    temperature_celsius: float = 0.0
    timestamp: float = 0.0
    platform: str = ""

    # Optional detailed CPU breakdown
    cpu_user_percent: float = 0.0
    cpu_system_percent: float = 0.0
    cpu_idle_percent: float = 0.0


class PlatformAgnosticCPUWidget(TemplateEditableWidget, QWidget):
    """Platform-agnostic CPU widget that works with ANY platform via normalization"""

    def __init__(self, controller, theme_library=None, parent=None):
        QWidget.__init__(self, parent)
        TemplateEditableWidget.__init__(self, 'cpu_widget', controller, theme_library)

        self.controller = controller
        self.theme_library = theme_library

        # Connect to NORMALIZED data signals only
        self._connect_to_normalized_signals()

        # Connect to basic device info
        self.controller.device_info_updated.connect(self.update_device_info)
        self.controller.theme_changed.connect(self.on_theme_changed)

        self._setup_widget()
        self._current_metrics = None

    def _connect_to_normalized_signals(self):
        """Connect only to normalized data signals - FIXED VERSION"""

        # Connect to system metrics if available
        signal_connections = [
            ('normalized_system_metrics_ready', self.update_system_metrics),  # ← PRIMARY
            ('normalized_system_ready', self.update_system_data),  # ← FALLBACK
            ('normalized_cpu_ready', self.update_cpu_data),  # ← CPU ONLY
            ('normalized_memory_ready', self.update_memory_data),  # ← MEMORY ONLY
        ]

        connected_count = 0
        for signal_name, handler in signal_connections:
            if hasattr(self.controller, signal_name):
                signal = getattr(self.controller, signal_name)
                signal.connect(handler)
                print(f" CPU Widget connected to {signal_name}")
                connected_count += 1
            else:
                print(f" Signal {signal_name} not available")

        if connected_count == 0:
            print(f" CPU Widget: NO SIGNALS CONNECTED!")
        else:
            print(f" CPU Widget: {connected_count} signals connected")

        # Also connect to raw outputs for debugging/template editing
        if hasattr(self.controller, 'raw_system_info_output'):
            self.controller.raw_system_info_output.connect(self.handle_raw_output_for_debugging)
            print(f" CPU Widget connected to raw_system_info_output")

    def _setup_widget(self):
        """Setup the widget UI - same as before but cleaner"""
        layout = QVBoxLayout(self)

        # Title with gear button
        title_layout = QHBoxLayout()

        self.title_label = QLabel("SYSTEM INFORMATION")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(self.title_label)

        self.data_source_label = QLabel("Waiting for data...")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #888888;")
        title_layout.addWidget(self.data_source_label)

        title_layout.addStretch()
        title_layout.addWidget(self.gear_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setMaximumWidth(80)
        self.refresh_button.clicked.connect(self._request_refresh)
        title_layout.addWidget(self.refresh_button)

        layout.addLayout(title_layout)

        # System info section
        self._create_system_info_section(layout)

        # Utilization section
        self._create_utilization_section(layout)

        # Status bar
        status_layout = QHBoxLayout()

        self.platform_label = QLabel("Platform: Unknown")
        self.platform_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.platform_label)

        status_layout.addStretch()

        self.update_time_label = QLabel("Last Update: Never")
        self.update_time_label.setStyleSheet("font-size: 10px; color: #888888;")
        status_layout.addWidget(self.update_time_label)

        layout.addLayout(status_layout)

    def _create_system_info_section(self, parent_layout):
        """Create system information display section"""
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.Shape.Box)
        info_layout = QVBoxLayout(info_frame)

        info_title = QLabel("Device Information")
        info_title.setStyleSheet("font-weight: bold; font-size: 12px; padding: 2px;")
        info_layout.addWidget(info_title)

        details_layout = QVBoxLayout()

        self.hostname_label = QLabel("Hostname: Unknown")
        self.hostname_label.setStyleSheet("font-size: 11px; padding: 1px;")
        details_layout.addWidget(self.hostname_label)

        self.hardware_label = QLabel("Hardware: Unknown")
        self.hardware_label.setStyleSheet("font-size: 11px; padding: 1px;")
        details_layout.addWidget(self.hardware_label)

        self.version_label = QLabel("Version: Unknown")
        self.version_label.setStyleSheet("font-size: 11px; padding: 1px;")
        details_layout.addWidget(self.version_label)

        self.uptime_label = QLabel("Uptime: Unknown")
        self.uptime_label.setStyleSheet("font-size: 11px; padding: 1px;")
        details_layout.addWidget(self.uptime_label)

        info_layout.addLayout(details_layout)
        parent_layout.addWidget(info_frame)

    def _create_utilization_section(self, parent_layout):
        """Create utilization meters section"""
        util_frame = QFrame()
        util_frame.setFrameStyle(QFrame.Shape.Box)
        util_layout = QVBoxLayout(util_frame)

        util_title = QLabel("Resource Utilization")
        util_title.setStyleSheet("font-weight: bold; font-size: 12px; padding: 2px;")
        util_layout.addWidget(util_title)

        # CPU Usage
        cpu_layout = QHBoxLayout()
        cpu_label = QLabel("CPU Usage:")
        cpu_label.setMinimumWidth(100)
        cpu_layout.addWidget(cpu_label)

        self.cpu_progress = QProgressBar()
        self.cpu_progress.setMinimum(0)
        self.cpu_progress.setMaximum(100)
        self.cpu_progress.setValue(0)
        cpu_layout.addWidget(self.cpu_progress)

        self.cpu_value_label = QLabel("0%")
        self.cpu_value_label.setMinimumWidth(40)
        cpu_layout.addWidget(self.cpu_value_label)

        util_layout.addLayout(cpu_layout)

        # Memory Usage
        memory_layout = QHBoxLayout()
        memory_label = QLabel("Memory Usage:")
        memory_label.setMinimumWidth(100)
        memory_layout.addWidget(memory_label)

        self.memory_progress = QProgressBar()
        self.memory_progress.setMinimum(0)
        self.memory_progress.setMaximum(100)
        self.memory_progress.setValue(0)
        memory_layout.addWidget(self.memory_progress)

        self.memory_value_label = QLabel("0%")
        self.memory_value_label.setMinimumWidth(40)
        memory_layout.addWidget(self.memory_value_label)

        util_layout.addLayout(memory_layout)

        # Memory details
        self.memory_details_label = QLabel("Total: Unknown | Free: Unknown")
        self.memory_details_label.setStyleSheet("font-size: 10px; color: #888888; padding: 2px;")
        util_layout.addWidget(self.memory_details_label)

        # Temperature (if available)
        temp_layout = QHBoxLayout()
        temp_label = QLabel("Temperature:")
        temp_label.setMinimumWidth(100)
        temp_layout.addWidget(temp_label)

        self.temperature_label = QLabel("Unknown")
        self.temperature_label.setStyleSheet("font-size: 11px; padding: 1px;")
        temp_layout.addWidget(self.temperature_label)

        # util_layout.addLayout(temp_layout)

        parent_layout.addWidget(util_frame)

    # ============ NORMALIZED DATA HANDLERS ============

    @pyqtSlot(object)  # NormalizedSystemMetrics
    def update_system_metrics(self, metrics: NormalizedSystemMetrics):
        """Update with normalized system metrics - FIXED merge logic"""
        print(f" Received normalized system metrics for platform: {metrics.platform}")
        print(f" Incoming data - CPU: {metrics.cpu_usage_percent}%, Memory: {metrics.memory_used_percent}%")

        # Store the current metrics, but merge with existing data intelligently
        if self._current_metrics is None:
            # First time - use all data
            self._current_metrics = metrics
            print(f" First update - using all data")
        else:
            # Subsequent updates - only update fields that have meaningful new data

            # CPU: Only update if new value is > 0 OR if we don't have any CPU data yet
            if metrics.cpu_usage_percent > 0 or self._current_metrics.cpu_usage_percent == 0:
                if metrics.cpu_usage_percent != self._current_metrics.cpu_usage_percent:
                    old_cpu = self._current_metrics.cpu_usage_percent
                    self._current_metrics.cpu_usage_percent = metrics.cpu_usage_percent
                    print(f" CPU updated: {old_cpu}% -> {metrics.cpu_usage_percent}%")
                else:
                    print(f" CPU unchanged: {metrics.cpu_usage_percent}%")
            else:
                print(
                    f" CPU preserved: keeping {self._current_metrics.cpu_usage_percent}% (ignoring {metrics.cpu_usage_percent}%)")

            # Memory: Only update if new value is > 0 OR if we don't have any memory data yet
            if metrics.memory_used_percent > 0 or self._current_metrics.memory_used_percent == 0:
                if metrics.memory_used_percent != self._current_metrics.memory_used_percent:
                    old_memory = self._current_metrics.memory_used_percent
                    self._current_metrics.memory_used_percent = metrics.memory_used_percent
                    self._current_metrics.memory_total_mb = metrics.memory_total_mb
                    self._current_metrics.memory_free_mb = metrics.memory_free_mb
                    self._current_metrics.memory_used_mb = metrics.memory_used_mb
                    print(f" Memory updated: {old_memory}% -> {metrics.memory_used_percent}%")
                else:
                    print(f" Memory unchanged: {metrics.memory_used_percent}%")
            else:
                print(f" Memory preserved: keeping {self._current_metrics.memory_used_percent}%")

            # Temperature: Only update if new value is > 0
            if metrics.temperature_celsius > 0:
                if metrics.temperature_celsius != self._current_metrics.temperature_celsius:
                    old_temp = self._current_metrics.temperature_celsius
                    self._current_metrics.temperature_celsius = metrics.temperature_celsius
                    print(f" Temperature updated: {old_temp}°C -> {metrics.temperature_celsius}°C")

            # Always update timestamp and platform
            self._current_metrics.timestamp = metrics.timestamp
            self._current_metrics.platform = metrics.platform

        # Now update UI with current merged data
        current = self._current_metrics

        # Update CPU display
        cpu_percent = int(current.cpu_usage_percent)
        self.cpu_progress.setValue(cpu_percent)
        self.cpu_value_label.setText(f"{cpu_percent}%")
        self._update_progress_color(self.cpu_progress, cpu_percent)

        # Update Memory display
        memory_percent = int(current.memory_used_percent)
        self.memory_progress.setValue(memory_percent)
        self.memory_value_label.setText(f"{memory_percent}%")
        self._update_progress_color(self.memory_progress, memory_percent)

        # Update memory details if we have data
        if current.memory_total_mb > 0:
            self.memory_details_label.setText(
                f"Total: {current.memory_total_mb:,} MB | Free: {current.memory_free_mb:,} MB"
            )

        # Update temperature if available
        if current.temperature_celsius > 0:
            temp_color = self._get_temperature_color(current.temperature_celsius)
            self.temperature_label.setText(f"{current.temperature_celsius:.1f}°C")
            self.temperature_label.setStyleSheet(f"font-size: 11px; color: {temp_color}; padding: 1px;")
        else:
            self.temperature_label.setText("Not Available")

        # Update status
        self.data_source_label.setText("Normalized Data")
        self.data_source_label.setStyleSheet("font-size: 10px; color: #00ff00; font-weight: bold;")
        self.platform_label.setText(f"Platform: {current.platform}")
        self._update_timestamp()

        print(f" Final UI state - CPU: {cpu_percent}%, Memory: {memory_percent}%")
    @pyqtSlot(object)  # CPU-specific normalized data
    def update_cpu_data(self, cpu_data):
        """Update CPU data from normalized CPU signal"""
        if hasattr(cpu_data, 'cpu_usage_percent'):
            cpu_percent = int(cpu_data.cpu_usage_percent)
        elif isinstance(cpu_data, (int, float)):
            cpu_percent = int(cpu_data)
        else:
            return

        self.cpu_progress.setValue(cpu_percent)
        self.cpu_value_label.setText(f"{cpu_percent}%")
        self._update_progress_color(self.cpu_progress, cpu_percent)
        self._update_timestamp()

    @pyqtSlot(object)  # Memory-specific normalized data
    def update_memory_data(self, memory_data):
        """Update memory data from normalized memory signal"""
        if hasattr(memory_data, 'memory_used_percent'):
            memory_percent = int(memory_data.memory_used_percent)
            self.memory_progress.setValue(memory_percent)
            self.memory_value_label.setText(f"{memory_percent}%")
            self._update_progress_color(self.memory_progress, memory_percent)

            if hasattr(memory_data, 'memory_total_mb'):
                self.memory_details_label.setText(
                    f"Total: {memory_data.memory_total_mb:,} MB | Free: {memory_data.memory_free_mb:,} MB"
                )

        self._update_timestamp()

    @pyqtSlot(object)  # Fallback for general system data
    def update_system_data(self, system_data):
        """Fallback handler for general system data"""
        print(f" Using fallback system data handler")
        # Handle various system data formats as fallback
        pass

    @pyqtSlot(object)  # DeviceInfo
    def update_device_info(self, device_info):
        """Update basic device information"""
        self.hostname_label.setText(f"Hostname: {device_info.hostname}")
        self.hardware_label.setText(f"Hardware: {device_info.model}")
        self.version_label.setText(f"Version: {device_info.version}")
        self.uptime_label.setText(f"Uptime: {device_info.uptime}")
        self.platform_label.setText(f"Platform: {device_info.platform}")

    @pyqtSlot(object)  # RawCommandOutput - for debugging only
    def handle_raw_output_for_debugging(self, raw_output):
        """Handle raw output for debugging - don't parse here!"""
        if 'cpu' in raw_output.command.lower() or 'memory' in raw_output.command.lower():
            self.data_source_label.setText("Raw Data (needs normalization)")
            self.data_source_label.setStyleSheet("font-size: 10px; color: #ff6600;")
            print(f" CPU widget received raw data for: {raw_output.command}")
            print(f"    This should be normalized by the controller first!")

    # ============ UTILITY METHODS ============

    def _update_progress_color(self, progress_bar, value):
        """Update progress bar color based on utilization level"""
        if value < 50:
            color = "#00ff00"  # Green
        elif value < 80:
            color = "#ffff00"  # Yellow
        else:
            color = "#ff4400"  # Red

        progress_bar.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)

    def _get_temperature_color(self, temp):
        """Get color for temperature display"""
        if temp < 40:
            return "#00ff00"  # Green
        elif temp < 60:
            return "#ffff00"  # Yellow
        elif temp < 80:
            return "#ff8800"  # Orange
        else:
            return "#ff4400"  # Red

    def _update_timestamp(self):
        """Update the last update timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        self.update_time_label.setText(f"Last Update: {timestamp}")

    def _request_refresh(self):
        """Request data refresh"""
        if hasattr(self.controller, 'collect_telemetry_data'):
            self.controller.collect_telemetry_data()

    @pyqtSlot(str)
    def on_theme_changed(self, theme_name: str):
        """Handle theme changes"""
        if self.theme_library:
            self.theme_library.apply_theme(self, theme_name)


# ============ SIMPLIFIED VERSION FOR BASIC USE ============

class SimplifiedCPUWidget(QWidget):
    """Simplified CPU widget for basic metrics display"""

    def __init__(self, controller, theme_library=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.theme_library = theme_library

        # Connect to basic signals
        if hasattr(controller, 'device_info_updated'):
            controller.device_info_updated.connect(self.update_device_info)

        self._setup_simple_widget()

    def _setup_simple_widget(self):
        """Setup simplified widget"""
        layout = QVBoxLayout(self)

        self.title_label = QLabel("SYSTEM STATUS")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.title_label)

        self.info_display = QTextEdit()
        self.info_display.setMaximumHeight(200)
        self.info_display.setReadOnly(True)
        self.info_display.setPlainText("System information will appear here...")
        layout.addWidget(self.info_display)

        self.status_label = QLabel("Status: Waiting for connection")
        self.status_label.setStyleSheet("font-size: 10px; color: #888888;")
        layout.addWidget(self.status_label)

    @pyqtSlot(object)
    def update_device_info(self, device_info):
        """Update with basic device info"""
        info_text = f"""Device Information:

Hostname: {device_info.hostname}
Platform: {device_info.platform}
Hardware: {device_info.model}
Version: {device_info.version}
Uptime: {device_info.uptime}
Status: {device_info.connection_status}
"""
        self.info_display.setPlainText(info_text)
        self.status_label.setText(f"Status: Connected to {device_info.platform}")