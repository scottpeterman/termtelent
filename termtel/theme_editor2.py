#!/usr/bin/env python3
"""
Theme Editor - Standalone theme creation and editing tool
Integrates with the existing ThemeLibrary system
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QColorDialog, QComboBox,
    QTextEdit, QSplitter, QGroupBox, QScrollArea, QMessageBox,
    QFileDialog, QCheckBox, QSpinBox, QTabWidget, QFormLayout,
    QFrame, QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPalette, QFont

# Import your existing theme system
try:
    from termtel.themes3 import ThemeLibrary, ThemeColors, LayeredHUDFrame

    THEME_SYSTEM_AVAILABLE = True
except ImportError:
    THEME_SYSTEM_AVAILABLE = False
    print("Warning: Could not import theme system, running in standalone mode")


class ColorPickerWidget(QWidget):
    """Custom color picker widget with hex input and visual preview"""
    colorChanged = pyqtSignal(str)

    def __init__(self, label: str, initial_color: str = "#000000", parent=None):
        super().__init__(parent)
        self.current_color = initial_color
        self.setup_ui(label)

    def setup_ui(self, label: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Label
        self.label = QLabel(label)
        self.label.setMinimumWidth(120)
        layout.addWidget(self.label)

        # Color preview button
        self.color_button = QPushButton()
        self.color_button.setFixedSize(40, 25)
        self.color_button.clicked.connect(self.open_color_dialog)
        self.update_color_button()
        layout.addWidget(self.color_button)

        # Hex input
        self.hex_input = QLineEdit(self.current_color)
        self.hex_input.setMaximumWidth(80)
        self.hex_input.textChanged.connect(self.on_hex_changed)
        layout.addWidget(self.hex_input)

        layout.addStretch()

    def update_color_button(self):
        """Update the color button's background"""
        self.color_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.current_color};
                border: 1px solid #666;
                border-radius: 3px;
            }}
        """)

    def open_color_dialog(self):
        """Open color picker dialog"""
        color = QColorDialog.getColor(QColor(self.current_color), self)
        if color.isValid():
            self.current_color = color.name()
            self.hex_input.setText(self.current_color)
            self.update_color_button()
            self.colorChanged.emit(self.current_color)

    def on_hex_changed(self, text: str):
        """Handle hex input changes"""
        if text.startswith('#') and len(text) == 7:
            try:
                # Validate hex color
                QColor(text)
                self.current_color = text
                self.update_color_button()
                self.colorChanged.emit(self.current_color)
            except:
                pass

    def set_color(self, color: str):
        """Set color programmatically"""
        self.current_color = color
        self.hex_input.setText(color)
        self.update_color_button()

    def get_color(self) -> str:
        """Get current color"""
        return self.current_color


class TerminalColorEditor(QWidget):
    """Editor for terminal-specific colors"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Terminal colors group
        terminal_group = QGroupBox("Terminal Colors")
        terminal_layout = QFormLayout(terminal_group)

        # Basic terminal colors
        self.terminal_colors = {}
        basic_colors = [
            ('foreground', 'Text Color', '#ffffff'),
            ('background', 'Background', '#000000'),
            ('cursor', 'Cursor', '#ffffff'),
            ('selection', 'Selection Background', '#444444'),
            ('selectionForeground', 'Selection Text', '#ffffff'),
        ]

        for key, label, default in basic_colors:
            color_widget = ColorPickerWidget(label, default)
            self.terminal_colors[key] = color_widget
            terminal_layout.addRow(color_widget)

        layout.addWidget(terminal_group)

        # ANSI colors group
        ansi_group = QGroupBox("ANSI Colors")
        ansi_layout = QGridLayout(ansi_group)

        ansi_colors = [
            ('black', 'Black', '#000000'),
            ('red', 'Red', '#cc0000'),
            ('green', 'Green', '#00cc00'),
            ('yellow', 'Yellow', '#cccc00'),
            ('blue', 'Blue', '#0000cc'),
            ('magenta', 'Magenta', '#cc00cc'),
            ('cyan', 'Cyan', '#00cccc'),
            ('white', 'White', '#cccccc'),
            ('brightBlack', 'Bright Black', '#666666'),
            ('brightRed', 'Bright Red', '#ff0000'),
            ('brightGreen', 'Bright Green', '#00ff00'),
            ('brightYellow', 'Bright Yellow', '#ffff00'),
            ('brightBlue', 'Bright Blue', '#0000ff'),
            ('brightMagenta', 'Bright Magenta', '#ff00ff'),
            ('brightCyan', 'Bright Cyan', '#00ffff'),
            ('brightWhite', 'Bright White', '#ffffff'),
        ]

        for i, (key, label, default) in enumerate(ansi_colors):
            color_widget = ColorPickerWidget(label, default)
            self.terminal_colors[key] = color_widget
            ansi_layout.addWidget(color_widget, i // 2, i % 2)

        layout.addWidget(ansi_group)

    def get_terminal_theme(self) -> Dict:
        """Get terminal theme dictionary"""
        return {
            'theme': {key: widget.get_color() for key, widget in self.terminal_colors.items()}
        }

    def set_terminal_theme(self, terminal_data: Dict):
        """Set terminal theme from dictionary"""
        if 'theme' in terminal_data:
            theme_data = terminal_data['theme']
            for key, widget in self.terminal_colors.items():
                if key in theme_data:
                    widget.set_color(theme_data[key])


class ThemePreviewWidget(QWidget):
    """Live preview of theme being edited"""

    def __init__(self, theme_manager=None, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.current_theme_data = {}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Preview label
        self.preview_label = QLabel("Theme Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(self.preview_label)

        # Sample UI elements
        self.create_sample_widgets(layout)

    def create_sample_widgets(self, layout):
        """Create sample widgets to preview theme"""

        # Sample button
        self.sample_button = QPushButton("Sample Button")
        layout.addWidget(self.sample_button)

        # Sample line edit
        self.sample_input = QLineEdit("Sample text input")
        layout.addWidget(self.sample_input)

        # Sample text area
        self.sample_text = QTextEdit()
        self.sample_text.setPlainText("Sample text area\nMultiple lines\nTheme preview")
        self.sample_text.setMaximumHeight(100)
        layout.addWidget(self.sample_text)

        # Sample terminal preview (simplified)
        self.terminal_preview = QTextEdit()
        self.terminal_preview.setPlainText("""
$ ssh user@host
user@host:~$ ls -la
total 24
drwxr-xr-x 3 user user 4096 Jan 15 10:30 .
drwxr-xr-x 5 user user 4096 Jan 15 10:25 ..
-rw-r--r-- 1 user user  220 Jan 15 10:25 .bash_logout
-rw-r--r-- 1 user user 3771 Jan 15 10:25 .bashrc
drwxr-xr-x 2 user user 4096 Jan 15 10:30 Documents
user@host:~$ """)
        self.terminal_preview.setFont(QFont("Courier New", 10))
        self.terminal_preview.setMaximumHeight(150)
        layout.addWidget(self.terminal_preview)

    def update_preview(self, theme_data: Dict):
        """Update preview with new theme data"""
        self.current_theme_data = theme_data

        if THEME_SYSTEM_AVAILABLE and self.theme_manager:
            try:
                # Create temporary theme
                temp_theme = ThemeColors.from_dict(theme_data)

                # Apply theme using theme manager
                stylesheet = self.theme_manager.generate_stylesheet(temp_theme)
                self.setStyleSheet(stylesheet)

                # Update terminal preview colors
                if 'terminal' in theme_data and 'theme' in theme_data['terminal']:
                    terminal_colors = theme_data['terminal']['theme']
                    terminal_style = f"""
                    QTextEdit {{
                        background-color: {terminal_colors.get('background', '#000000')};
                        color: {terminal_colors.get('foreground', '#ffffff')};
                        font-family: 'Courier New';
                        border: 1px solid {theme_data.get('border', '#666666')};
                    }}
                    """
                    self.terminal_preview.setStyleSheet(terminal_style)

            except Exception as e:
                print(f"Error updating preview: {e}")
        else:
            # Fallback preview without theme manager
            self.apply_basic_preview(theme_data)

    def apply_basic_preview(self, theme_data: Dict):
        """Basic preview without theme manager"""
        basic_style = f"""
        QWidget {{
            background-color: {theme_data.get('background', '#ffffff')};
            color: {theme_data.get('text', '#000000')};
        }}
        QPushButton {{
            background-color: {theme_data.get('darker_bg', '#f0f0f0')};
            border: 1px solid {theme_data.get('border', '#cccccc')};
            padding: 5px;
        }}
        QPushButton:hover {{
            background-color: {theme_data.get('button_hover', '#e0e0e0')};
        }}
        QLineEdit, QTextEdit {{
            background-color: {theme_data.get('lighter_bg', '#ffffff')};
            border: 1px solid {theme_data.get('border', '#cccccc')};
            padding: 3px;
        }}
        """
        self.setStyleSheet(basic_style)


class ThemeEditorWindow(QMainWindow):
    """Main theme editor window"""

    def __init__(self, theme_manager=None, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager or self.create_fallback_theme_manager()
        self.current_theme_name = "new_theme"
        self.current_theme_data = self.get_default_theme_data()
        self.unsaved_changes = False

        self.setup_ui()
        self.setup_connections()
        self.update_preview()

    def create_fallback_theme_manager(self):
        """Create fallback theme manager if not available"""
        if THEME_SYSTEM_AVAILABLE:
            return ThemeLibrary()
        return None

    def setup_ui(self):
        self.setWindowTitle("TerminalTelemetry Theme Editor")
        self.setMinimumSize(1200, 800)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout
        main_layout = QHBoxLayout(central_widget)

        # Create splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # Left panel - Editor
        editor_panel = self.create_editor_panel()
        splitter.addWidget(editor_panel)

        # Right panel - Preview
        preview_panel = self.create_preview_panel()
        splitter.addWidget(preview_panel)

        # Set initial sizes
        splitter.setSizes([700, 500])

        # Create menu bar
        self.create_menu_bar()

        # Status bar
        self.statusBar().showMessage("Ready")

    def create_menu_bar(self):
        """Create menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        file_menu.addAction("New Theme", self.new_theme)
        file_menu.addAction("Open Theme...", self.open_theme)
        file_menu.addSeparator()
        file_menu.addAction("Save", self.save_theme)
        file_menu.addAction("Save As...", self.save_theme_as)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction("Reset to Defaults", self.reset_to_defaults)
        edit_menu.addAction("Load from Existing Theme...", self.load_existing_theme)

        # Preview menu
        preview_menu = menubar.addMenu("Preview")
        preview_menu.addAction("Refresh Preview", self.update_preview)
        preview_menu.addAction("Test in Main Application", self.test_in_main_app)

    def create_editor_panel(self) -> QWidget:
        """Create the theme editor panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Theme info section
        info_group = QGroupBox("Theme Information")
        info_layout = QFormLayout(info_group)

        self.theme_name_input = QLineEdit(self.current_theme_name)
        self.theme_name_input.textChanged.connect(self.on_theme_name_changed)
        info_layout.addRow("Theme Name:", self.theme_name_input)

        layout.addWidget(info_group)

        # Tabbed editor
        self.editor_tabs = QTabWidget()

        # Core colors tab
        self.core_colors_tab = self.create_core_colors_tab()
        self.editor_tabs.addTab(self.core_colors_tab, "Core Colors")

        # UI colors tab
        self.ui_colors_tab = self.create_ui_colors_tab()
        self.editor_tabs.addTab(self.ui_colors_tab, "UI Elements")

        # Terminal colors tab
        self.terminal_tab = TerminalColorEditor()
        self.editor_tabs.addTab(self.terminal_tab, "Terminal")

        # JSON editor tab
        self.json_tab = self.create_json_tab()
        self.editor_tabs.addTab(self.json_tab, "JSON Editor")

        layout.addWidget(self.editor_tabs)

        return panel

    def create_core_colors_tab(self) -> QWidget:
        """Create core colors editing tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Scroll area for color pickers
        scroll = QScrollArea()
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # Core color definitions
        self.core_color_widgets = {}
        core_colors = [
            ('primary', 'Primary Color', '#0a8993'),
            ('secondary', 'Secondary Color', '#065359'),
            ('background', 'Background', '#111111'),
            ('darker_bg', 'Darker Background', '#1a1a1a'),
            ('lighter_bg', 'Lighter Background', '#0ac0c8'),
            ('text', 'Text Color', '#0affff'),
            ('grid', 'Grid Color', '#08a2a9'),
            ('line', 'Line Color', '#ffff66'),
            ('border', 'Border Color', '#0a8993'),
            ('success', 'Success Color', '#0a8993'),
            ('error', 'Error Color', '#ff4c4c'),
        ]

        for key, label, default in core_colors:
            color_widget = ColorPickerWidget(label, default)
            color_widget.colorChanged.connect(self.on_color_changed)
            self.core_color_widgets[key] = color_widget
            scroll_layout.addWidget(color_widget)

        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        return widget

    def create_ui_colors_tab(self) -> QWidget:
        """Create UI elements colors tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        scroll = QScrollArea()
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        self.ui_color_widgets = {}
        ui_colors = [
            ('border_light', 'Light Border', 'rgba(10, 255, 255, 0.5)'),
            ('corner_gap', 'Corner Gap', '#010203'),
            ('corner_bright', 'Corner Bright', '#0ff5ff'),
            ('panel_bg', 'Panel Background', 'rgba(0, 0, 0, 0.95)'),
            ('scrollbar_bg', 'Scrollbar Background', 'rgba(6, 20, 22, 0.6)'),
            ('selected_bg', 'Selected Background', 'rgba(10, 137, 147, 0.25)'),
            ('button_hover', 'Button Hover', '#08706e'),
            ('button_pressed', 'Button Pressed', '#064d4a'),
            ('chart_bg', 'Chart Background', 'rgba(6, 83, 89, 0.25)'),
        ]

        for key, label, default in ui_colors:
            color_widget = ColorPickerWidget(label, default)
            color_widget.colorChanged.connect(self.on_color_changed)
            self.ui_color_widgets[key] = color_widget
            scroll_layout.addWidget(color_widget)

        scroll.setWidget(scroll_content)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        return widget

    def create_json_tab(self) -> QWidget:
        """Create JSON editor tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # JSON text editor
        self.json_editor = QTextEdit()
        self.json_editor.setFont(QFont("Courier New", 10))
        layout.addWidget(self.json_editor)

        # Buttons
        button_layout = QHBoxLayout()

        load_from_json_btn = QPushButton("Load from JSON")
        load_from_json_btn.clicked.connect(self.load_from_json)
        button_layout.addWidget(load_from_json_btn)

        update_json_btn = QPushButton("Update JSON")
        update_json_btn.clicked.connect(self.update_json_display)
        button_layout.addWidget(update_json_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        return widget

    def create_preview_panel(self) -> QWidget:
        """Create preview panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Preview title
        title = QLabel("Live Preview")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # Preview widget
        self.preview_widget = ThemePreviewWidget(self.theme_manager)
        layout.addWidget(self.preview_widget)

        # Preview controls
        controls_layout = QHBoxLayout()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.update_preview)
        controls_layout.addWidget(refresh_btn)

        controls_layout.addStretch()
        layout.addLayout(controls_layout)

        return panel

    def setup_connections(self):
        """Setup signal connections"""
        # Connect terminal color changes
        for widget in self.terminal_tab.terminal_colors.values():
            widget.colorChanged.connect(self.on_color_changed)

    def get_default_theme_data(self) -> Dict:
        """Get default theme data"""
        return {
            "primary": "#0a8993",
            "secondary": "#065359",
            "background": "#111111",
            "darker_bg": "#1a1a1a",
            "lighter_bg": "#0ac0c8",
            "text": "#0affff",
            "grid": "#08a2a9",
            "line": "#ffff66",
            "border": "#0a8993",
            "success": "#0a8993",
            "error": "#ff4c4c",
            "border_light": "rgba(10, 255, 255, 0.5)",
            "corner_gap": "#010203",
            "corner_bright": "#0ff5ff",
            "panel_bg": "rgba(0, 0, 0, 0.95)",
            "scrollbar_bg": "rgba(6, 20, 22, 0.6)",
            "selected_bg": "rgba(10, 137, 147, 0.25)",
            "button_hover": "#08706e",
            "button_pressed": "#064d4a",
            "chart_bg": "rgba(6, 83, 89, 0.25)",
            "terminal": {
                "theme": {
                    "foreground": "#0affff",
                    "background": "#111111",
                    "cursor": "#0affff",
                    "selection": "#444444",
                    "selectionForeground": "#ffffff",
                    "black": "#000000",
                    "red": "#ff4c4c",
                    "green": "#0a8993",
                    "yellow": "#ffff66",
                    "blue": "#0a8993",
                    "magenta": "#065359",
                    "cyan": "#08a2a9",
                    "white": "#0affff",
                    "brightBlack": "#666666",
                    "brightRed": "#ff6666",
                    "brightGreen": "#0ac0c8",
                    "brightYellow": "#ffff99",
                    "brightBlue": "#0ff5ff",
                    "brightMagenta": "#0ac0c8",
                    "brightCyan": "#0ff5ff",
                    "brightWhite": "#ffffff"
                }
            }
        }

    def collect_theme_data(self) -> Dict:
        """Collect current theme data from all editors"""
        theme_data = {}

        # Collect core colors
        for key, widget in self.core_color_widgets.items():
            theme_data[key] = widget.get_color()

        # Collect UI colors
        for key, widget in self.ui_color_widgets.items():
            theme_data[key] = widget.get_color()

        # Collect terminal colors
        theme_data['terminal'] = self.terminal_tab.get_terminal_theme()

        return theme_data

    def update_all_editors(self, theme_data: Dict):
        """Update all editors with theme data"""
        # Update core colors
        for key, widget in self.core_color_widgets.items():
            if key in theme_data:
                widget.set_color(theme_data[key])

        # Update UI colors
        for key, widget in self.ui_color_widgets.items():
            if key in theme_data:
                widget.set_color(theme_data[key])

        # Update terminal colors
        if 'terminal' in theme_data:
            self.terminal_tab.set_terminal_theme(theme_data['terminal'])

        # Update JSON display
        self.update_json_display()

    def on_theme_name_changed(self, name: str):
        """Handle theme name change"""
        self.current_theme_name = name
        self.mark_unsaved_changes()

    def on_color_changed(self, color: str):
        """Handle color change"""
        self.mark_unsaved_changes()

        # Update preview with small delay to avoid excessive updates
        if not hasattr(self, '_update_timer'):
            self._update_timer = QTimer()
            self._update_timer.setSingleShot(True)
            self._update_timer.timeout.connect(self.update_preview)

        self._update_timer.start(200)  # 200ms delay

    def mark_unsaved_changes(self):
        """Mark that there are unsaved changes"""
        self.unsaved_changes = True
        title = f"TerminalTelemetry Theme Editor - {self.current_theme_name}"
        if self.unsaved_changes:
            title += " *"
        self.setWindowTitle(title)

    def update_preview(self):
        """Update the preview widget"""
        theme_data = self.collect_theme_data()
        self.preview_widget.update_preview(theme_data)
        self.current_theme_data = theme_data

    def update_json_display(self):
        """Update JSON editor with current theme data"""
        theme_data = self.collect_theme_data()
        json_str = json.dumps(theme_data, indent=2)
        self.json_editor.setPlainText(json_str)

    def load_from_json(self):
        """Load theme from JSON editor"""
        try:
            json_str = self.json_editor.toPlainText()
            theme_data = json.loads(json_str)
            self.update_all_editors(theme_data)
            self.update_preview()
            self.statusBar().showMessage("Theme loaded from JSON", 2000)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON Error", f"Invalid JSON: {str(e)}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load theme: {str(e)}")

    def new_theme(self):
        """Create new theme"""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save them first?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                if not self.save_theme():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.current_theme_name = "new_theme"
        self.theme_name_input.setText(self.current_theme_name)
        self.current_theme_data = self.get_default_theme_data()
        self.update_all_editors(self.current_theme_data)
        self.unsaved_changes = False
        self.setWindowTitle("TerminalTelemetry Theme Editor")
        self.statusBar().showMessage("New theme created", 2000)

    def open_theme(self):
        """Open existing theme file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Theme", "./themes", "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    theme_data = json.load(f)

                self.current_theme_name = Path(file_path).stem
                self.theme_name_input.setText(self.current_theme_name)
                self.update_all_editors(theme_data)
                self.unsaved_changes = False
                self.setWindowTitle(f"TerminalTelemetry Theme Editor - {self.current_theme_name}")
                self.statusBar().showMessage(f"Opened {file_path}", 2000)

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open theme: {str(e)}")

    def save_theme(self) -> bool:
        """Save current theme"""
        if not self.current_theme_name or self.current_theme_name == "new_theme":
            return self.save_theme_as()

        return self.save_theme_to_file(f"./themes/{self.current_theme_name}.json")

    def save_theme_as(self) -> bool:
        """Save theme with new name"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Theme As", f"./themes/{self.current_theme_name}.json",
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            self.current_theme_name = Path(file_path).stem
            self.theme_name_input.setText(self.current_theme_name)
            return self.save_theme_to_file(file_path)

        return False

    def save_theme_to_file(self, file_path: str) -> bool:
        """Save theme to specific file"""
        try:
            # Ensure themes directory exists
            Path(file_path).parent.mkdir(exist_ok=True)

            theme_data = self.collect_theme_data()

            with open(file_path, 'w') as f:
                json.dump(theme_data, f, indent=2)

            self.unsaved_changes = False
            self.setWindowTitle(f"TerminalTelemetry Theme Editor - {self.current_theme_name}")
            self.statusBar().showMessage(f"Saved to {file_path}", 2000)

            return True

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save theme: {str(e)}")
            return False

    def reset_to_defaults(self):
        """Reset theme to defaults"""
        reply = QMessageBox.question(
            self, "Reset Theme",
            "Reset all colors to default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.current_theme_data = self.get_default_theme_data()
            self.update_all_editors(self.current_theme_data)
            self.mark_unsaved_changes()
            self.statusBar().showMessage("Reset to defaults", 2000)

    def load_existing_theme(self):
        """Load from existing theme in theme manager"""
        if not THEME_SYSTEM_AVAILABLE or not self.theme_manager:
            QMessageBox.information(self, "Not Available", "Theme manager not available")
            return

        themes = self.theme_manager.get_theme_names()
        if not themes:
            QMessageBox.information(self, "No Themes", "No existing themes found")
            return

        from PyQt6.QtWidgets import QInputDialog

        theme_name, ok = QInputDialog.getItem(
            self, "Load Existing Theme", "Select theme:", themes, 0, False
        )

        if ok and theme_name:
            theme = self.theme_manager.get_theme(theme_name)
            if theme:
                theme_data = theme.to_dict()
                self.update_all_editors(theme_data)
                self.mark_unsaved_changes()
                self.statusBar().showMessage(f"Loaded theme: {theme_name}", 2000)

    def test_in_main_app(self):
        """Test theme in main application (if connected)"""
        if hasattr(self, 'parent') and self.parent():
            try:
                # Save theme temporarily and apply to parent
                theme_data = self.collect_theme_data()

                if THEME_SYSTEM_AVAILABLE:
                    temp_theme = ThemeColors.from_dict(theme_data)
                    if hasattr(self.parent(), 'theme_manager'):
                        self.parent().theme_manager.apply_theme(self.parent(), temp_theme)
                        self.statusBar().showMessage("Applied to main application", 2000)
                    else:
                        QMessageBox.information(self, "Not Available", "Parent application theme manager not found")
                else:
                    QMessageBox.information(self, "Not Available", "Theme system not available")

            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to apply theme: {str(e)}")
        else:
            QMessageBox.information(self, "Not Available", "Main application not connected")

    def closeEvent(self, event):
        """Handle window close"""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save them?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                if not self.save_theme():
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        event.accept()


def launch_theme_editor(parent=None):
    """Launch the theme editor"""
    theme_manager = None

    # Try to get theme manager from parent
    if parent and hasattr(parent, 'theme_manager'):
        theme_manager = parent.theme_manager
    elif THEME_SYSTEM_AVAILABLE:
        theme_manager = ThemeLibrary()

    editor = ThemeEditorWindow(theme_manager, parent)
    editor.show()
    return editor


def main():
    """Standalone entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Theme Editor")

    editor = ThemeEditorWindow()
    editor.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()