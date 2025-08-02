#!/usr/bin/env python3
"""
Database Maintenance Widget for RapidCMDB
PyQt6 GUI wrapper for the database maintenance utility
"""

import sys
import os
import sqlite3
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QTextEdit, QProgressBar, QComboBox,
    QCheckBox, QSpinBox, QFileDialog, QMessageBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QFrame, QScrollArea, QApplication, QSizePolicy
)
from PyQt6.QtCore import (
    QThread, pyqtSignal, QTimer, Qt, QSize
)
from PyQt6.QtGui import QFont, QIcon, QPalette, QColor

# Import the original maintenance class
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))
from rapidcmdb.db_maint import DatabaseMaintenance

logger = logging.getLogger(__name__)


class DatabaseMaintenanceThread(QThread):
    """Worker thread for database maintenance operations"""

    # Signals for communication with main thread
    progress_update = pyqtSignal(str, int)  # message, progress
    operation_complete = pyqtSignal(str, dict)  # operation, results
    operation_error = pyqtSignal(str, str)  # operation, error_message
    log_message = pyqtSignal(str, str)  # level, message

    def __init__(self, db_path: str, operation: str, **kwargs):
        super().__init__()
        self.db_path = db_path
        self.operation = operation
        self.kwargs = kwargs
        self.db_maint = None

    def run(self):
        """Execute the database maintenance operation"""
        try:
            self.progress_update.emit("Initializing database connection...", 10)
            self.db_maint = DatabaseMaintenance(self.db_path)

            if self.operation == "backup":
                self.progress_update.emit("Creating database backup...", 30)
                result = self.db_maint.backup_database()
                self.operation_complete.emit("backup", {"backup_path": result})

            elif self.operation == "normalize_vendors":
                self.progress_update.emit("Normalizing vendor names...", 40)
                dry_run = self.kwargs.get("dry_run", True)
                result = self.db_maint.normalize_vendor_names(dry_run=dry_run)
                self.operation_complete.emit("normalize_vendors", result)

            elif self.operation == "find_duplicates":
                self.progress_update.emit("Searching for duplicate devices...", 50)
                result = self.db_maint.find_duplicate_devices()
                self.operation_complete.emit("find_duplicates", {"duplicates": result})

            elif self.operation == "merge_devices":
                self.progress_update.emit("Merging duplicate devices...", 60)
                primary_id = self.kwargs.get("primary_id")
                duplicate_ids = self.kwargs.get("duplicate_ids", [])
                dry_run = self.kwargs.get("dry_run", True)
                result = self.db_maint.merge_duplicate_devices(primary_id, duplicate_ids, dry_run)
                self.operation_complete.emit("merge_devices", {"success": result})

            elif self.operation == "clean_old_data":
                self.progress_update.emit("Cleaning old data...", 70)
                dry_run = self.kwargs.get("dry_run", True)
                result = self.db_maint.clean_old_data(dry_run=dry_run)
                self.operation_complete.emit("clean_old_data", result)

            elif self.operation == "optimize":
                self.progress_update.emit("Optimizing database...", 80)
                result = self.db_maint.optimize_database()
                self.operation_complete.emit("optimize", result)

            elif self.operation == "generate_report":
                self.progress_update.emit("Generating maintenance report...", 90)
                result = self.db_maint.generate_maintenance_report()
                self.operation_complete.emit("generate_report", result)

            self.progress_update.emit("Operation completed successfully", 100)

        except Exception as e:
            error_msg = f"Error during {self.operation}: {str(e)}"
            logger.error(error_msg)
            self.operation_error.emit(self.operation, error_msg)

        finally:
            if self.db_maint:
                try:
                    self.db_maint.close()
                except:
                    pass


class DatabaseMaintenanceWidget(QWidget):
    """Main database maintenance widget with theme support"""

    def __init__(self, parent=None, theme_manager=None):
        super().__init__(parent)
        self.parent_window = parent
        self.theme_manager = theme_manager
        self.current_theme = getattr(parent, 'theme', 'cyberpunk') if parent else 'cyberpunk'

        # Database connection
        self.db_path = None
        self.worker_thread = None

        # Initialize UI
        self.setup_ui()
        self.setup_connections()

        # Apply initial theme
        if self.theme_manager:
            self.apply_theme(self.theme_manager, self.current_theme)

        # Auto-detect database if possible
        self.auto_detect_database()

    def setup_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Database Maintenance Tool")
        self.setMinimumSize(1200, 800)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Header section
        header_layout = self.create_header_section()
        main_layout.addLayout(header_layout)

        # Main content area with tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        main_layout.addWidget(self.tab_widget)

        # Create tabs
        self.create_overview_tab()
        self.create_maintenance_tab()
        self.create_duplicates_tab()
        self.create_optimization_tab()
        self.create_logs_tab()

        # Progress section
        progress_layout = self.create_progress_section()
        main_layout.addLayout(progress_layout)


    def apply_theme(self, theme_manager=None, theme_name=None):
        """Apply the current theme - compatible with both calling patterns"""

        # Handle parameter updates
        if theme_manager is not None:
            self.theme_manager = theme_manager
        if theme_name is not None:
            self.current_theme = theme_name

        # Apply theme using the real ThemeLibrary
        if self.theme_manager:
            try:
                # Get the theme to use - prefer current_theme, fallback to parent.theme
                theme_to_use = self.current_theme
                if hasattr(self, 'parent') and hasattr(self.parent, 'theme'):
                    theme_to_use = self.parent.theme

                theme = self.theme_manager.get_theme(theme_to_use)
                if theme:
                    stylesheet = self.theme_manager.generate_stylesheet(theme)
                    self.setStyleSheet(stylesheet)
                    print(f"Successfully applied theme: {theme_to_use}")
                else:
                    print(f"Theme '{theme_to_use}' not found")
                    # self._apply_fallback_theme()

            except Exception as e:
                print(f"Error applying theme: {e}")
                self._apply_fallback_theme()
        else:
            self._apply_fallback_theme()

    def create_header_section(self) -> QHBoxLayout:
        """Create the header section with database selection"""
        header_layout = QHBoxLayout()

        # Database selection group
        db_group = QGroupBox("Database Configuration")
        db_layout = QHBoxLayout(db_group)

        self.db_path_label = QLabel("No database selected")
        self.db_path_label.setWordWrap(True)
        db_layout.addWidget(QLabel("Database:"))
        db_layout.addWidget(self.db_path_label, 1)

        self.select_db_btn = QPushButton("Select Database")
        self.select_db_btn.setMaximumWidth(150)
        db_layout.addWidget(self.select_db_btn)

        header_layout.addWidget(db_group)

        return header_layout

    def create_overview_tab(self):
        """Create the overview/dashboard tab"""
        overview_widget = QWidget()
        layout = QVBoxLayout(overview_widget)

        # Quick stats section
        stats_group = QGroupBox("Database Statistics")
        stats_layout = QGridLayout(stats_group)

        self.stats_labels = {}
        stats_items = [
            ("Database Size", "size_mb"),
            ("Total Devices", "total_devices"),
            ("Active Devices", "active_devices"),
            ("Last Updated", "last_update"),
            ("Collection Success Rate", "success_rate"),
            ("Data Freshness (7d)", "freshness_7d")
        ]

        for i, (label, key) in enumerate(stats_items):
            row, col = divmod(i, 2)
            stats_layout.addWidget(QLabel(f"{label}:"), row, col * 2)
            self.stats_labels[key] = QLabel("--")
            self.stats_labels[key].setStyleSheet("font-weight: bold;")
            stats_layout.addWidget(self.stats_labels[key], row, col * 2 + 1)

        layout.addWidget(stats_group)

        # Vendor distribution
        vendor_group = QGroupBox("Vendor Distribution")
        vendor_layout = QVBoxLayout(vendor_group)

        self.vendor_table = QTableWidget(0, 2)
        self.vendor_table.setHorizontalHeaderLabels(["Vendor", "Device Count"])
        self.vendor_table.horizontalHeader().setStretchLastSection(True)
        self.vendor_table.setMaximumHeight(200)
        vendor_layout.addWidget(self.vendor_table)

        layout.addWidget(vendor_group)

        # Quick actions
        actions_group = QGroupBox("Quick Actions")
        actions_layout = QHBoxLayout(actions_group)

        self.refresh_stats_btn = QPushButton("Refresh Statistics")
        self.backup_btn = QPushButton("Create Backup")
        self.generate_report_btn = QPushButton("Generate Report")

        actions_layout.addWidget(self.refresh_stats_btn)
        actions_layout.addWidget(self.backup_btn)
        actions_layout.addWidget(self.generate_report_btn)
        actions_layout.addStretch()

        layout.addWidget(actions_group)
        layout.addStretch()

        self.tab_widget.addTab(overview_widget, "Overview")

    def create_maintenance_tab(self):
        """Create the maintenance operations tab"""
        maintenance_widget = QWidget()
        layout = QVBoxLayout(maintenance_widget)

        # Vendor normalization section
        vendor_group = QGroupBox("Vendor Name Normalization")
        vendor_layout = QVBoxLayout(vendor_group)

        vendor_info = QLabel(
            "Standardize vendor names to fix case inconsistencies and variations.\n"
            "This helps consolidate devices from the same vendor under unified names."
        )
        vendor_info.setWordWrap(True)
        vendor_layout.addWidget(vendor_info)

        vendor_buttons = QHBoxLayout()
        self.normalize_dry_run_btn = QPushButton("Preview Changes")
        self.normalize_apply_btn = QPushButton("Apply Normalization")
        self.normalize_apply_btn.setEnabled(False)

        vendor_buttons.addWidget(self.normalize_dry_run_btn)
        vendor_buttons.addWidget(self.normalize_apply_btn)
        vendor_buttons.addStretch()

        vendor_layout.addLayout(vendor_buttons)
        layout.addWidget(vendor_group)

        # Data cleanup section
        cleanup_group = QGroupBox("Data Cleanup")
        cleanup_layout = QVBoxLayout(cleanup_group)

        cleanup_info = QLabel(
            "Remove old data based on retention policies to keep database size manageable."
        )
        cleanup_info.setWordWrap(True)
        cleanup_layout.addWidget(cleanup_info)

        cleanup_buttons = QHBoxLayout()
        self.cleanup_dry_run_btn = QPushButton("Preview Cleanup")
        self.cleanup_apply_btn = QPushButton("Apply Cleanup")
        self.cleanup_apply_btn.setEnabled(False)

        cleanup_buttons.addWidget(self.cleanup_dry_run_btn)
        cleanup_buttons.addWidget(self.cleanup_apply_btn)
        cleanup_buttons.addStretch()

        cleanup_layout.addLayout(cleanup_buttons)
        layout.addWidget(cleanup_group)

        layout.addStretch()
        self.tab_widget.addTab(maintenance_widget, "Maintenance")

    def create_duplicates_tab(self):
        """Create the duplicate management tab"""
        duplicates_widget = QWidget()
        layout = QVBoxLayout(duplicates_widget)

        # Controls section
        controls_group = QGroupBox("Duplicate Detection")
        controls_layout = QHBoxLayout(controls_group)

        self.find_duplicates_btn = QPushButton("Find Duplicates")
        self.merge_selected_btn = QPushButton("Merge Selected")
        self.merge_selected_btn.setEnabled(False)

        controls_layout.addWidget(self.find_duplicates_btn)
        controls_layout.addWidget(self.merge_selected_btn)
        controls_layout.addStretch()

        layout.addWidget(controls_group)

        # Duplicates table
        duplicates_group = QGroupBox("Duplicate Devices")
        duplicates_layout = QVBoxLayout(duplicates_group)

        self.duplicates_table = QTableWidget(0, 6)
        self.duplicates_table.setHorizontalHeaderLabels([
            "Select", "Type", "Criteria", "Count", "Device Names", "Device IDs"
        ])
        self.duplicates_table.horizontalHeader().setStretchLastSection(True)
        self.duplicates_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        duplicates_layout.addWidget(self.duplicates_table)
        layout.addWidget(duplicates_group)

        self.tab_widget.addTab(duplicates_widget, "Duplicates")

    def create_optimization_tab(self):
        """Create the database optimization tab"""
        optimization_widget = QWidget()
        layout = QVBoxLayout(optimization_widget)

        # Optimization info
        info_group = QGroupBox("Database Optimization")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel(
            "Database optimization performs VACUUM, REINDEX, and ANALYZE operations to:\n"
            "• Reclaim unused space\n"
            "• Rebuild indexes for better performance\n"
            "• Update query planner statistics\n\n"
            "This operation may take several minutes for large databases."
        )
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)

        # Optimization controls
        controls_group = QGroupBox("Optimization Controls")
        controls_layout = QVBoxLayout(controls_group)

        # Options
        options_layout = QHBoxLayout()
        self.create_backup_check = QCheckBox("Create backup before optimization")
        self.create_backup_check.setChecked(True)
        options_layout.addWidget(self.create_backup_check)
        options_layout.addStretch()

        controls_layout.addLayout(options_layout)

        # Buttons
        buttons_layout = QHBoxLayout()
        self.optimize_btn = QPushButton("Optimize Database")
        self.optimize_btn.setStyleSheet("QPushButton { font-weight: bold; }")

        buttons_layout.addWidget(self.optimize_btn)
        buttons_layout.addStretch()

        controls_layout.addLayout(buttons_layout)
        layout.addWidget(controls_group)

        # Results section
        results_group = QGroupBox("Optimization Results")
        results_layout = QGridLayout(results_group)

        self.optimization_results = {}
        result_items = [
            ("Size Before", "size_before_mb"),
            ("Size After", "size_after_mb"),
            ("Space Saved", "space_saved_mb"),
            ("Space Saved %", "space_saved_percent")
        ]

        for i, (label, key) in enumerate(result_items):
            row, col = divmod(i, 2)
            results_layout.addWidget(QLabel(f"{label}:"), row, col * 2)
            self.optimization_results[key] = QLabel("--")
            self.optimization_results[key].setStyleSheet("font-weight: bold;")
            results_layout.addWidget(self.optimization_results[key], row, col * 2 + 1)

        layout.addWidget(results_group)
        layout.addStretch()

        self.tab_widget.addTab(optimization_widget, "Optimization")

    def create_logs_tab(self):
        """Create the logs and output tab"""
        logs_widget = QWidget()
        layout = QVBoxLayout(logs_widget)

        # Controls
        controls_layout = QHBoxLayout()

        self.clear_logs_btn = QPushButton("Clear Logs")
        self.save_logs_btn = QPushButton("Save Logs")

        controls_layout.addWidget(self.clear_logs_btn)
        controls_layout.addWidget(self.save_logs_btn)
        controls_layout.addStretch()

        layout.addLayout(controls_layout)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_output)

        self.tab_widget.addTab(logs_widget, "Logs")

    def create_progress_section(self) -> QHBoxLayout:
        """Create the progress section"""
        progress_layout = QHBoxLayout()

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setMaximumWidth(80)

        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.cancel_btn)

        return progress_layout

    def setup_connections(self):
        """Setup signal connections"""
        # Header buttons
        self.select_db_btn.clicked.connect(self.select_database)

        # Overview tab
        self.refresh_stats_btn.clicked.connect(self.refresh_statistics)
        self.backup_btn.clicked.connect(self.create_backup)
        self.generate_report_btn.clicked.connect(self.generate_report)

        # Maintenance tab
        self.normalize_dry_run_btn.clicked.connect(self.preview_vendor_normalization)
        self.normalize_apply_btn.clicked.connect(self.apply_vendor_normalization)
        self.cleanup_dry_run_btn.clicked.connect(self.preview_data_cleanup)
        self.cleanup_apply_btn.clicked.connect(self.apply_data_cleanup)

        # Duplicates tab
        self.find_duplicates_btn.clicked.connect(self.find_duplicates)
        self.merge_selected_btn.clicked.connect(self.merge_selected_duplicates)

        # Optimization tab
        self.optimize_btn.clicked.connect(self.optimize_database)

        # Logs tab
        self.clear_logs_btn.clicked.connect(self.clear_logs)
        self.save_logs_btn.clicked.connect(self.save_logs)

        # Progress section
        self.cancel_btn.clicked.connect(self.cancel_operation)

    def auto_detect_database(self):
        """Try to auto-detect the database file"""
        possible_paths = [
            "rapidcmdb.db",
            "rapid_cmdb.db",
            "cmdb.db",
            os.path.expanduser("~/rapidcmdb.db"),
            os.path.expanduser("~/rapid_cmdb.db")
        ]

        for path in possible_paths:
            if os.path.exists(path):
                self.set_database_path(path)
                break

    def select_database(self):
        """Open file dialog to select database"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Database File",
            "",
            "SQLite Database (*.db *.sqlite *.sqlite3);;All Files (*.*)"
        )

        if file_path:
            self.set_database_path(file_path)

    def set_database_path(self, path: str):
        """Set the database path and update UI"""
        self.db_path = path
        self.db_path_label.setText(f"...{path[-50:]}" if len(path) > 50 else path)
        self.db_path_label.setToolTip(path)

        # Enable buttons
        self.backup_btn.setEnabled(True)
        self.generate_report_btn.setEnabled(True)
        self.refresh_stats_btn.setEnabled(True)
        self.find_duplicates_btn.setEnabled(True)
        self.normalize_dry_run_btn.setEnabled(True)
        self.cleanup_dry_run_btn.setEnabled(True)
        self.optimize_btn.setEnabled(True)

        # Auto-refresh statistics
        self.refresh_statistics()

    def start_operation(self, operation: str, **kwargs):
        """Start a database operation in a worker thread"""
        if not self.db_path:
            QMessageBox.warning(self, "No Database", "Please select a database file first.")
            return

        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "Operation Running", "Another operation is already running.")
            return

        self.worker_thread = DatabaseMaintenanceThread(self.db_path, operation, **kwargs)
        self.worker_thread.progress_update.connect(self.update_progress)
        self.worker_thread.operation_complete.connect(self.operation_completed)
        self.worker_thread.operation_error.connect(self.operation_failed)
        self.worker_thread.log_message.connect(self.add_log_message)

        # Show progress
        self.progress_bar.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.status_label.setText("Running...")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")

        self.worker_thread.start()

    def update_progress(self, message: str, progress: int):
        """Update progress bar and status"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
        self.add_log_message("INFO", message)

    def operation_completed(self, operation: str, results: dict):
        """Handle successful operation completion"""
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.status_label.setText("Operation completed successfully")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")

        self.add_log_message("SUCCESS", f"{operation} completed successfully")

        # Handle specific operation results
        if operation == "generate_report":
            self.display_report_results(results)
        elif operation == "find_duplicates":
            self.display_duplicates_results(results.get("duplicates", []))
        elif operation == "normalize_vendors":
            self.display_normalization_results(results)
        elif operation == "clean_old_data":
            self.display_cleanup_results(results)
        elif operation == "optimize":
            self.display_optimization_results(results)
        elif operation == "backup":
            QMessageBox.information(
                self, "Backup Complete",
                f"Database backup created:\n{results.get('backup_path', 'Unknown location')}"
            )

        # Refresh statistics if needed
        if operation in ["normalize_vendors", "clean_old_data", "optimize", "merge_devices"]:
            QTimer.singleShot(1000, self.refresh_statistics)

    def operation_failed(self, operation: str, error_message: str):
        """Handle operation failure"""
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.status_label.setText("Operation failed")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")

        self.add_log_message("ERROR", f"{operation} failed: {error_message}")

        QMessageBox.critical(
            self, "Operation Failed",
            f"The {operation} operation failed:\n\n{error_message}"
        )

    def cancel_operation(self):
        """Cancel the current operation"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.terminate()
            self.worker_thread.wait(3000)

        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.status_label.setText("Operation cancelled")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def add_log_message(self, level: str, message: str):
        """Add a message to the log output"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {level}: {message}"

        # Color code by level
        color = {
            "INFO": "black",
            "SUCCESS": "green",
            "WARNING": "orange",
            "ERROR": "red"
        }.get(level, "black")

        self.log_output.append(f'<span style="color: {color};">{formatted_message}</span>')

    def clear_logs(self):
        """Clear the log output"""
        self.log_output.clear()

    def save_logs(self):
        """Save logs to file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Logs",
            f"db_maintenance_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*.*)"
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    f.write(self.log_output.toPlainText())
                QMessageBox.information(self, "Logs Saved", f"Logs saved to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Failed", f"Failed to save logs:\n{str(e)}")

    # Operation methods
    def refresh_statistics(self):
        """Refresh database statistics"""
        self.start_operation("generate_report")

    def create_backup(self):
        """Create database backup"""
        self.start_operation("backup")

    def generate_report(self):
        """Generate maintenance report"""
        self.start_operation("generate_report")

    def preview_vendor_normalization(self):
        """Preview vendor normalization changes"""
        self.start_operation("normalize_vendors", dry_run=True)

    def apply_vendor_normalization(self):
        """Apply vendor normalization changes"""
        reply = QMessageBox.question(
            self, "Confirm Changes",
            "Are you sure you want to apply vendor normalization changes?\n"
            "This will modify your database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.start_operation("normalize_vendors", dry_run=False)

    def preview_data_cleanup(self):
        """Preview data cleanup"""
        self.start_operation("clean_old_data", dry_run=True)

    def apply_data_cleanup(self):
        """Apply data cleanup"""
        reply = QMessageBox.question(
            self, "Confirm Cleanup",
            "Are you sure you want to clean old data?\n"
            "This will permanently delete old records.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.start_operation("clean_old_data", dry_run=False)

    def find_duplicates(self):
        """Find duplicate devices"""
        self.start_operation("find_duplicates")

    def merge_selected_duplicates(self):
        """Merge selected duplicate devices"""
        # This would need implementation based on selection
        QMessageBox.information(self, "Not Implemented", "Duplicate merging UI is not yet implemented.")

    def optimize_database(self):
        """Optimize database"""
        if self.create_backup_check.isChecked():
            reply = QMessageBox.question(
                self, "Confirm Optimization",
                "This will create a backup and then optimize the database.\n"
                "The optimization may take several minutes.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self, "Confirm Optimization",
                "This will optimize the database without creating a backup.\n"
                "The optimization may take several minutes.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

        if reply == QMessageBox.StandardButton.Yes:
            if self.create_backup_check.isChecked():
                # Create backup first, then optimize
                self.start_operation("backup")
                QTimer.singleShot(2000, lambda: self.start_operation("optimize"))
            else:
                self.start_operation("optimize")

    # Result display methods
    def display_report_results(self, report: dict):
        """Display report results in the overview tab"""
        try:
            self.stats_labels["size_mb"].setText(f"{report.get('database_size_mb', 0):.1f} MB")
            self.stats_labels["total_devices"].setText(str(report.get('total_devices', 0)))

            # Calculate active devices from freshness data if available
            freshness = report.get('data_freshness', {})
            if freshness:
                active_pct = freshness.get('updated_7d_percent', 0)
                total = report.get('total_devices', 0)
                active = int((active_pct / 100) * total) if total > 0 else 0
                self.stats_labels["active_devices"].setText(str(active))
                self.stats_labels["freshness_7d"].setText(f"{active_pct:.1f}%")

            # Collection stats
            collection_stats = report.get('collection_stats', {})
            if collection_stats:
                success_rate = collection_stats.get('success_rate_percent', 0)
                self.stats_labels["success_rate"].setText(f"{success_rate:.1f}%")

            # Last update (use current time as proxy)
            self.stats_labels["last_update"].setText(datetime.now().strftime("%Y-%m-%d %H:%M"))

            # Update vendor distribution table
            vendor_dist = report.get('vendor_distribution', {})
            self.vendor_table.setRowCount(len(vendor_dist))

            for row, (vendor, count) in enumerate(vendor_dist.items()):
                self.vendor_table.setItem(row, 0, QTableWidgetItem(str(vendor)))
                self.vendor_table.setItem(row, 1, QTableWidgetItem(str(count)))

            self.vendor_table.resizeColumnsToContents()

        except Exception as e:
            logger.error(f"Error displaying report results: {e}")

    def display_duplicates_results(self, duplicates: List[Dict]):
        """Display duplicate detection results"""
        try:
            self.duplicates_table.setRowCount(len(duplicates))

            for row, dup in enumerate(duplicates):
                # Checkbox for selection
                checkbox = QCheckBox()
                self.duplicates_table.setCellWidget(row, 0, checkbox)

                # Duplicate info
                self.duplicates_table.setItem(row, 1, QTableWidgetItem(dup.get('type', '')))
                self.duplicates_table.setItem(row, 2, QTableWidgetItem(dup.get('criteria', '')))
                self.duplicates_table.setItem(row, 3, QTableWidgetItem(str(dup.get('count', 0))))

                device_names = ', '.join(dup.get('device_names', []))
                self.duplicates_table.setItem(row, 4, QTableWidgetItem(device_names))

                device_ids = ', '.join(map(str, dup.get('device_ids', [])))
                self.duplicates_table.setItem(row, 5, QTableWidgetItem(device_ids))

            self.duplicates_table.resizeColumnsToContents()

            # Enable merge button if duplicates found
            self.merge_selected_btn.setEnabled(len(duplicates) > 0)

            # Switch to duplicates tab to show results
            self.tab_widget.setCurrentIndex(2)

        except Exception as e:
            logger.error(f"Error displaying duplicates results: {e}")

    def display_normalization_results(self, results: Dict):
        """Display vendor normalization results"""
        try:
            if results:
                message_parts = ["Vendor normalization preview:\n"]
                for change, count in results.items():
                    message_parts.append(f"• {change}: {count} devices")

                message = "\n".join(message_parts)
                self.add_log_message("INFO", message.replace("\n", " | "))

                # Enable apply button
                self.normalize_apply_btn.setEnabled(True)

                # Show detailed results
                QMessageBox.information(self, "Normalization Preview", message)
            else:
                self.add_log_message("INFO", "No vendor normalization needed")
                QMessageBox.information(self, "No Changes", "No vendor normalization changes are needed.")

        except Exception as e:
            logger.error(f"Error displaying normalization results: {e}")

    def display_cleanup_results(self, results: Dict):
        """Display data cleanup results"""
        try:
            if any(results.values()):
                message_parts = ["Data cleanup preview:\n"]
                for table, count in results.items():
                    if count > 0:
                        message_parts.append(f"• {table}: {count} records")

                message = "\n".join(message_parts)
                self.add_log_message("INFO", message.replace("\n", " | "))

                # Enable apply button
                self.cleanup_apply_btn.setEnabled(True)

                # Show detailed results
                QMessageBox.information(self, "Cleanup Preview", message)
            else:
                self.add_log_message("INFO", "No old data to clean")
                QMessageBox.information(self, "No Cleanup Needed", "No old data needs to be cleaned.")

        except Exception as e:
            logger.error(f"Error displaying cleanup results: {e}")

    def display_optimization_results(self, results: Dict):
        """Display database optimization results"""
        try:
            # Update optimization results labels
            for key, label in self.optimization_results.items():
                value = results.get(key, 0)
                if key.endswith('_mb'):
                    label.setText(f"{value:.2f} MB")
                elif key.endswith('_percent'):
                    label.setText(f"{value:.1f}%")
                else:
                    label.setText(str(value))

            # Switch to optimization tab to show results
            self.tab_widget.setCurrentIndex(3)

            # Show summary message
            size_before = results.get('size_before_mb', 0)
            size_after = results.get('size_after_mb', 0)
            space_saved = results.get('space_saved_mb', 0)
            space_saved_pct = results.get('space_saved_percent', 0)

            message = (
                f"Database optimization completed successfully!\n\n"
                f"Size before: {size_before:.2f} MB\n"
                f"Size after: {size_after:.2f} MB\n"
                f"Space saved: {space_saved:.2f} MB ({space_saved_pct:.1f}%)"
            )

            QMessageBox.information(self, "Optimization Complete", message)

        except Exception as e:
            logger.error(f"Error displaying optimization results: {e}")


    def cleanup(self):
        """Cleanup when widget is closed"""
        try:
            # Cancel any running operations
            if self.worker_thread and self.worker_thread.isRunning():
                self.worker_thread.terminate()
                self.worker_thread.wait(3000)

            logger.info("Database maintenance widget cleaned up")

        except Exception as e:
            logger.error(f"Error during database maintenance widget cleanup: {e}")

    def closeEvent(self, event):
        """Handle close event"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self, "Operation Running",
                "A database operation is currently running.\n"
                "Do you want to cancel it and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.cleanup()
                event.accept()
            else:
                event.ignore()
        else:
            self.cleanup()
            event.accept()


class DatabaseMaintenanceWrapper:
    """Wrapper class to standardize database maintenance interface"""

    def __init__(self, maintenance_widget):
        self.maintenance = maintenance_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.maintenance, 'cleanup'):
            self.maintenance.cleanup()




# Test/Demo code
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("Database Maintenance Tool")


    # Create a simple theme manager mock for testing
    class MockThemeManager:
        def get_colors(self, theme_name):
            return {
                'background': '#2b2b2b',
                'secondary_background': '#3c3c3c',
                'text': '#ffffff',
                'border': '#555555',
                'accent': '#007acc'
            }




    # Create and show widget
    theme_manager = MockThemeManager()
    widget = DatabaseMaintenanceWidget(theme_manager=theme_manager)
    widget.show()

    sys.exit(app.exec())