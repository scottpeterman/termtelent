from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QLabel, QFileDialog, QTabWidget,
                             QScrollArea, QFrame, QColorDialog, QSplitter,
                             QTreeWidget, QTreeWidgetItem, QLineEdit, QCheckBox,
                             QGroupBox, QApplication, QMainWindow, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPalette, QIcon

import os
import sys
import json
import logging
from pathlib import Path
from copy import deepcopy

# Import theme components from themes3.py
from termtel.themes3 import ThemeColors, ThemeLibrary, LayeredHUDFrame

logger = logging.getLogger('termtel.theme_editor')


class ColorButton(QPushButton):
    """Custom button for color selection with color preview"""

    def __init__(self, color="#000000", parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(30, 30)
        self.update_color(color)
        self.clicked.connect(self.choose_color)

    def update_color(self, color):
        """Update button appearance with the selected color"""
        self.color = color
        if color.startswith('rgba'):
            # Handle rgba colors
            rgba = color.strip('rgba()').split(',')
            r, g, b = map(int, [rgba[0], rgba[1], rgba[2]])
            a = float(rgba[3])
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba({r},{g},{b},{a});
                    border: 1px solid #cccccc;
                }}
                QPushButton:hover {{
                    border: 1px solid white;
                }}
            """)
        else:
            # Handle hex colors
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 1px solid #cccccc;
                }}
                QPushButton:hover {{
                    border: 1px solid white;
                }}
            """)

    def choose_color(self):
        """Open color dialog and emit color change signal"""
        if self.color.startswith('rgba'):
            # Handle rgba colors
            rgba = self.color.strip('rgba()').split(',')
            r, g, b = map(int, [rgba[0], rgba[1], rgba[2]])
            a = float(rgba[3])
            initial_color = QColor(r, g, b, int(a * 255))
            dialog = QColorDialog(initial_color, self)
            dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel)
        else:
            # Handle hex colors
            dialog = QColorDialog(QColor(self.color), self)

        if dialog.exec():
            new_color = dialog.selectedColor()
            if new_color.isValid():
                if new_color.alpha() < 255:
                    # Use rgba format for transparent colors
                    color_str = f"rgba({new_color.red()},{new_color.green()},{new_color.blue()},{new_color.alpha() / 255})"
                else:
                    # Use hex format for solid colors
                    color_str = new_color.name()
                self.update_color(color_str)
                self.parent().color_changed(self.objectName(), color_str)


class ColorConfigItem(QWidget):
    """Widget for a single color configuration item"""

    color_changed_signal = pyqtSignal(str, str)

    def __init__(self, name, color, parent=None):
        super().__init__(parent)
        self.name = name
        self.color = color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Label
        self.label = QLabel(name)
        self.label.setFixedWidth(150)

        # Color button
        self.color_btn = ColorButton(color, self)
        self.color_btn.setObjectName(name)

        # Color value display
        self.value_label = QLineEdit(color)
        self.value_label.setReadOnly(True)

        layout.addWidget(self.label)
        layout.addWidget(self.color_btn)
        layout.addWidget(self.value_label)

    def color_changed(self, name, color):
        """Handle color change events"""
        self.color = color
        self.value_label.setText(color)
        # Emit signal instead of trying to call parent directly
        self.color_changed_signal.emit(name, color)


class ThemeEditorWidget(QWidget):
    """Theme editor widget for termtel"""

    theme_changed = pyqtSignal(str, dict)

    def __init__(self, theme_manager=None, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager or ThemeLibrary()
        self.current_theme_name = "cyberpunk"
        self.current_theme = None
        self.auto_apply_enabled = True  # Flag to enable/disable auto-apply
        self.setup_ui()

        # Populate the theme dropdown
        self.refresh_theme_list()

        # Load the default theme
        if self.theme_manager:
            self.load_theme(self.current_theme_name)

    def setup_ui(self):
        """Set up the user interface"""
        self.main_layout = QVBoxLayout(self)

        # Toolbar for file operations
        self.setup_toolbar()

        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_layout.addWidget(self.splitter)

        # Left side: Theme configuration
        self.config_widget = QWidget()
        self.config_layout = QVBoxLayout(self.config_widget)

        # Tabs for different theme sections
        self.config_tabs = QTabWidget()
        self.setup_theme_tabs()
        self.config_layout.addWidget(self.config_tabs)

        # Right side: Theme preview
        self.preview_widget = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_widget)

        # Scroll area for preview
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        self.preview_container = QWidget()
        self.preview_container_layout = QVBoxLayout(self.preview_container)
        preview_scroll.setWidget(self.preview_container)
        self.preview_layout.addWidget(preview_scroll)

        # Add preview elements
        self.setup_preview_widgets()

        # Add to splitter
        self.splitter.addWidget(self.config_widget)
        self.splitter.addWidget(self.preview_widget)
        self.splitter.setSizes([400, 600])

    def setup_toolbar(self):
        """Set up toolbar with file operations"""
        toolbar = QHBoxLayout()

        # New theme button
        self.new_btn = QPushButton("New Theme")
        self.new_btn.clicked.connect(self.new_theme)
        toolbar.addWidget(self.new_btn)

        # Theme selection dropdown
        self.theme_dropdown_label = QLabel("Theme:")
        toolbar.addWidget(self.theme_dropdown_label)

        self.theme_dropdown = QComboBox()
        self.theme_dropdown.setMinimumWidth(150)
        # Will be populated in refresh_theme_list method
        self.theme_dropdown.currentTextChanged.connect(self.on_theme_selected_from_dropdown)
        toolbar.addWidget(self.theme_dropdown)

        # Load theme from file button
        self.load_file_btn = QPushButton("Load File...")
        self.load_file_btn.clicked.connect(self.load_theme_file)
        toolbar.addWidget(self.load_file_btn)

        # Save theme button
        self.save_btn = QPushButton("Save Theme")
        self.save_btn.clicked.connect(self.save_theme)
        toolbar.addWidget(self.save_btn)

        # Save as button
        self.save_as_btn = QPushButton("Save As...")
        self.save_as_btn.clicked.connect(self.save_theme_as)
        toolbar.addWidget(self.save_as_btn)

        # Apply button
        self.apply_btn = QPushButton("Apply Theme")
        self.apply_btn.clicked.connect(self.apply_theme)
        toolbar.addWidget(self.apply_btn)

        # Auto-apply checkbox
        self.auto_apply_cb = QCheckBox("Auto-Apply")
        self.auto_apply_cb.setChecked(self.auto_apply_enabled)
        self.auto_apply_cb.stateChanged.connect(self.toggle_auto_apply)
        toolbar.addWidget(self.auto_apply_cb)

        # Theme name
        self.theme_name_label = QLabel("Theme Name:")
        toolbar.addWidget(self.theme_name_label)

        self.theme_name_edit = QLineEdit()
        toolbar.addWidget(self.theme_name_edit)

        # Add toolbar to main layout
        self.main_layout.addLayout(toolbar)

    def setup_theme_tabs(self):
        """Set up tabs for different theme sections"""
        # Basic Colors Tab
        self.basic_tab = QWidget()
        self.basic_layout = QVBoxLayout(self.basic_tab)

        # Scroll area for basic colors
        basic_scroll = QScrollArea()
        basic_scroll.setWidgetResizable(True)
        basic_container = QWidget()
        self.basic_colors_layout = QVBoxLayout(basic_container)
        basic_scroll.setWidget(basic_container)
        self.basic_layout.addWidget(basic_scroll)

        # Effect Colors Tab
        self.effects_tab = QWidget()
        self.effects_layout = QVBoxLayout(self.effects_tab)

        # Terminal Colors Tab
        self.terminal_tab = QWidget()
        self.terminal_layout = QVBoxLayout(self.terminal_tab)

        # Add tabs
        self.config_tabs.addTab(self.basic_tab, "Basic Colors")
        self.config_tabs.addTab(self.effects_tab, "Effects")
        self.config_tabs.addTab(self.terminal_tab, "Terminal")

    def setup_preview_widgets(self):
        """Set up preview widgets showing theme elements"""
        # Main preview label
        preview_label = QLabel("Theme Preview")
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_container_layout.addWidget(preview_label)

        # Create bordered frame with theme style
        self.frame = LayeredHUDFrame(self, theme_manager=self.theme_manager, theme_name=self.current_theme_name)
        frame_layout = QVBoxLayout()
        self.frame.content_layout.addLayout(frame_layout)

        # Add window title and controls to simulate appearance
        title_layout = QHBoxLayout()
        title_label = QLabel("termtel Preview")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(title_label)
        frame_layout.addLayout(title_layout)

        # Add session tree preview
        tree_group = QGroupBox("Sessions")
        tree_layout = QVBoxLayout(tree_group)
        self.session_tree = QTreeWidget()
        self.session_tree.setHeaderHidden(True)
        tree_item = QTreeWidgetItem(["Example"])
        self.session_tree.addTopLevelItem(tree_item)
        session = QTreeWidgetItem(["Terminal 1"])
        tree_item.addChild(session)
        tree_layout.addWidget(self.session_tree)
        frame_layout.addWidget(tree_group)

        # Add terminal preview
        term_group = QGroupBox("Terminal")
        term_layout = QVBoxLayout(term_group)
        term_preview = QLabel(
            "user@hostname:~$ ls -la\ntotal 32\ndrwxr-xr-x  5 user group 4096 Mar 30 10:25 .\ndrwxr-xr-x 25 user group 4096 Mar 30 09:14 ..\n-rw-r--r--  1 user group  220 Jan  1  2022 .bash_logout")
        term_preview.setStyleSheet("font-family: 'Courier New'; background-color: #000;")
        term_layout.addWidget(term_preview)
        frame_layout.addWidget(term_group)

        # Add buttons preview
        button_group = QGroupBox("Controls")
        button_layout = QHBoxLayout(button_group)
        normal_btn = QPushButton("Normal Button")
        button_layout.addWidget(normal_btn)
        hover_btn = QPushButton("Hover Button")
        hover_btn.setStyleSheet("background-color: var(--button-hover);")
        button_layout.addWidget(hover_btn)
        frame_layout.addWidget(button_group)

        # Add form elements preview
        form_group = QGroupBox("Form Elements")
        form_layout = QGridLayout(form_group)
        form_layout.addWidget(QLabel("Text Input:"), 0, 0)
        form_layout.addWidget(QLineEdit("Input text"), 0, 1)
        form_layout.addWidget(QLabel("Checkbox:"), 1, 0)
        form_layout.addWidget(QCheckBox("Check me"), 1, 1)
        frame_layout.addWidget(form_group)

        # Add the frame to the preview container
        self.preview_container_layout.addWidget(self.frame)

    def refresh_theme_list(self):
        """Refresh the list of available themes in the dropdown"""
        # Save current selection
        current_text = self.theme_dropdown.currentText()

        # Clear and repopulate
        self.theme_dropdown.clear()

        # Get theme names from manager
        theme_names = self.theme_manager.get_theme_names()

        # Also scan themes directory for JSON files
        themes_dir = Path("./themes")
        if themes_dir.exists():
            for theme_file in themes_dir.glob('*.json'):
                theme_name = theme_file.stem
                if theme_name not in theme_names:
                    theme_names.append(theme_name)

        # Add to dropdown
        self.theme_dropdown.addItems(sorted(theme_names))

        # Restore selection if possible
        index = self.theme_dropdown.findText(current_text)
        if index >= 0:
            self.theme_dropdown.setCurrentIndex(index)
        elif self.theme_dropdown.count() > 0:
            self.theme_dropdown.setCurrentIndex(0)

    def on_theme_selected_from_dropdown(self, theme_name):
        """Handle theme selection from dropdown"""
        if theme_name and theme_name != self.current_theme_name:
            self.load_theme(theme_name)

    def load_theme_dialog(self):
        """Open dialog to select theme to load (legacy method)"""
        # This is kept for backward compatibility
        # The dropdown now handles theme selection

        # If no themes available, open file dialog
        if self.theme_dropdown.count() == 0:
            self.load_theme_file()

    def toggle_auto_apply(self, state):
        """Toggle auto-apply feature"""
        self.auto_apply_enabled = state == Qt.CheckState.Checked

    def auto_apply_theme(self):
        """Apply theme automatically if auto-apply is enabled"""
        if not self.auto_apply_enabled:
            return

        # Use a very short timer to allow UI to update first
        QTimer.singleShot(10, self._perform_auto_apply)

    def _perform_auto_apply(self):
        """Internal method to perform the actual auto-apply"""
        if not self.current_theme:
            return

        # Add to theme manager with temporary name if needed
        theme_name = self.theme_name_edit.text().strip()
        if not theme_name:
            theme_name = f"temp_{self.current_theme_name}"

        # Add theme to manager without saving to disk
        self.theme_manager.add_theme(theme_name, self.current_theme, save=False)

        # Notify that theme changed
        self.theme_changed.emit(theme_name, self.current_theme.to_dict())

    def load_theme(self, theme_name):
        """Load a theme by name from the theme manager"""
        try:
            # Get theme from manager
            theme = self.theme_manager.get_theme(theme_name)
            if not theme:
                logger.error(f"Theme '{theme_name}' not found")
                return False

            # Set as current theme
            self.current_theme_name = theme_name
            self.current_theme = theme
            self.theme_name_edit.setText(theme_name)

            # Update UI with theme colors
            self.update_color_editors(theme)

            # Update preview
            self.update_preview()

            return True
        except Exception as e:
            logger.error(f"Error loading theme '{theme_name}': {e}")
            return False

    def update_color_editors(self, theme):
        """Update color editor UI with theme values"""
        # Clear existing widgets
        for layout in [self.basic_colors_layout, self.effects_layout, self.terminal_layout]:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        # Basic colors
        basic_group = QGroupBox("Core Colors")
        basic_layout = QVBoxLayout(basic_group)
        for name in ['primary', 'secondary', 'background', 'darker_bg', 'lighter_bg',
                     'text', 'grid', 'line', 'border', 'success', 'error']:
            if hasattr(theme, name):
                item = ColorConfigItem(name, getattr(theme, name), self)
                item.color_changed_signal.connect(self.color_changed)
                basic_layout.addWidget(item)
        self.basic_colors_layout.addWidget(basic_group)

        # Effect colors
        effects_group = QGroupBox("Effect Colors")
        effects_layout = QVBoxLayout(effects_group)
        for name in ['border_light', 'corner_gap', 'corner_bright', 'panel_bg',
                     'scrollbar_bg', 'selected_bg', 'button_hover', 'button_pressed', 'chart_bg']:
            if hasattr(theme, name):
                item = ColorConfigItem(name, getattr(theme, name), self)
                item.color_changed_signal.connect(self.color_changed)
                effects_layout.addWidget(item)
        self.effects_layout.addWidget(effects_group)

        # Terminal colors
        if hasattr(theme, 'terminal') and theme.terminal and 'theme' in theme.terminal:
            terminal_group = QGroupBox("Terminal Colors")
            terminal_layout = QVBoxLayout(terminal_group)

            for key, value in theme.terminal['theme'].items():
                if key != 'scrollbar' and isinstance(value, str):
                    item = ColorConfigItem(f"terminal.{key}", value, self)
                    item.color_changed_signal.connect(self.color_changed)
                    terminal_layout.addWidget(item)

            # Add scrollbar colors if they exist
            if 'scrollbar' in theme.terminal['theme']:
                scrollbar_group = QGroupBox("Terminal Scrollbar")
                scrollbar_layout = QVBoxLayout(scrollbar_group)

                for key, value in theme.terminal['theme']['scrollbar'].items():
                    item = ColorConfigItem(f"terminal.scrollbar.{key}", value, self)
                    item.color_changed_signal.connect(self.color_changed)
                    scrollbar_layout.addWidget(item)

                self.terminal_layout.addWidget(scrollbar_group)

            self.terminal_layout.addWidget(terminal_group)

    def update_preview(self):
        """Update the preview with current theme"""
        if self.current_theme and self.frame:
            self.frame.set_theme(self.current_theme_name)

            # Update all other preview elements
            self.update_ui_preview()

    def update_ui_preview(self):
        """Update UI preview with current theme colors"""
        if not self.current_theme:
            return

        # Get theme colors
        colors = self.current_theme

        # Update session tree colors
        self.session_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {colors.darker_bg};
                color: {colors.text};
                border: 1px solid {colors.border_light};
            }}
            QTreeWidget::item:selected {{
                background-color: {colors.selected_bg};
            }}
        """)

    def color_changed(self, name, color):
        """Handle color change from editor"""
        if not self.current_theme:
            return

        # Update theme with new color
        if "." in name:
            # Handle nested properties (e.g. terminal.foreground)
            parts = name.split(".")
            if parts[0] == "terminal":
                if len(parts) == 2:
                    # Simple terminal property
                    if not hasattr(self.current_theme, 'terminal'):
                        self.current_theme.terminal = {'theme': {}}
                    elif 'theme' not in self.current_theme.terminal:
                        self.current_theme.terminal['theme'] = {}
                    self.current_theme.terminal['theme'][parts[1]] = color
                elif len(parts) == 3 and parts[1] == "scrollbar":
                    # Terminal scrollbar property
                    if not hasattr(self.current_theme, 'terminal'):
                        self.current_theme.terminal = {'theme': {'scrollbar': {}}}
                    elif 'theme' not in self.current_theme.terminal:
                        self.current_theme.terminal['theme'] = {'scrollbar': {}}
                    elif 'scrollbar' not in self.current_theme.terminal['theme']:
                        self.current_theme.terminal['theme']['scrollbar'] = {}
                    self.current_theme.terminal['theme']['scrollbar'][parts[2]] = color
        else:
            # Simple property
            setattr(self.current_theme, name, color)

        # Immediately update preview
        self.update_preview()

        # Apply theme to the application immediately for real-time feedback
        self.auto_apply_theme()

    def new_theme(self):
        """Create a new theme based on cyberpunk"""
        # Get default theme as base
        base_theme = self.theme_manager.get_theme("cyberpunk")
        if not base_theme:
            logger.error("Default theme 'cyberpunk' not found")
            return

        # Create new theme
        self.current_theme = deepcopy(base_theme)
        self.current_theme_name = "new_theme"
        self.theme_name_edit.setText(self.current_theme_name)

        # Update UI
        self.update_color_editors(self.current_theme)
        self.update_preview()

    def load_theme_file(self):
        """Load theme from JSON file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Theme File",
            str(Path("./themes")),
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    theme_dict = json.load(f)

                # Convert to ThemeColors
                theme = ThemeColors.from_dict(theme_dict)

                # Set as current theme
                self.current_theme = theme
                self.current_theme_name = Path(file_path).stem
                self.theme_name_edit.setText(self.current_theme_name)

                # Update UI
                self.update_color_editors(theme)
                self.update_preview()

                # Add to theme manager
                self.theme_manager.add_theme(self.current_theme_name, theme, save=False)

                # Refresh the theme list and select the loaded theme
                self.refresh_theme_list()
                index = self.theme_dropdown.findText(self.current_theme_name)
                if index >= 0:
                    self.theme_dropdown.setCurrentIndex(index)

                logger.info(f"Loaded theme from {file_path}")
            except Exception as e:
                logger.error(f"Error loading theme from {file_path}: {e}")

    def save_theme(self):
        """Save current theme"""
        if not self.current_theme:
            return

        theme_name = self.theme_name_edit.text().strip()
        if not theme_name:
            self.save_theme_as()
            return

        # Update theme name
        self.current_theme_name = theme_name

        # Add to theme manager (which saves it)
        self.theme_manager.add_theme(theme_name, self.current_theme, save=True)
        logger.info(f"Saved theme '{theme_name}'")

        # Refresh the theme list
        self.refresh_theme_list()

        # Find and select the theme in the dropdown
        index = self.theme_dropdown.findText(theme_name)
        if index >= 0:
            self.theme_dropdown.setCurrentIndex(index)

        # Notify that theme changed
        self.theme_changed.emit(theme_name, self.current_theme.to_dict())

    def save_theme_as(self):
        """Save theme with a new name"""
        if not self.current_theme:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Theme As",
            str(Path("./themes")),
            "JSON Files (*.json);;All Files (*)"
        )

        if file_path:
            try:
                # Ensure file has .json extension
                if not file_path.lower().endswith('.json'):
                    file_path += '.json'

                # Save theme to file
                with open(file_path, 'w') as f:
                    json.dump(self.current_theme.to_dict(), f, indent=2)

                # Update theme name to match file
                self.current_theme_name = Path(file_path).stem
                self.theme_name_edit.setText(self.current_theme_name)

                # Add to theme manager
                self.theme_manager.add_theme(self.current_theme_name, self.current_theme, save=False)

                # Refresh the theme list and select the new theme
                self.refresh_theme_list()
                index = self.theme_dropdown.findText(self.current_theme_name)
                if index >= 0:
                    self.theme_dropdown.setCurrentIndex(index)

                logger.info(f"Saved theme to {file_path}")

                # Notify that theme changed
                self.theme_changed.emit(self.current_theme_name, self.current_theme.to_dict())
            except Exception as e:
                logger.error(f"Error saving theme to {file_path}: {e}")

    def apply_theme(self):
        """Apply current theme to the application"""
        if not self.current_theme:
            return

        theme_name = self.theme_name_edit.text().strip()
        if not theme_name:
            theme_name = "temp_theme"

        # Update theme name
        self.current_theme_name = theme_name

        # Add to theme manager
        self.theme_manager.add_theme(theme_name, self.current_theme, save=False)

        # Notify that theme changed
        self.theme_changed.emit(theme_name, self.current_theme.to_dict())

        # Try to apply globally if parent is a window
        parent = self.parent()
        while parent:
            if hasattr(parent, 'switch_theme'):
                parent.switch_theme(theme_name)
                break
            parent = parent.parent()


def main():
    """Run the theme editor as a standalone application"""
    app = QApplication(sys.argv)
    app.setApplicationName("Theme Editor Test")

    # Create main window
    main_window = QMainWindow()
    main_window.setWindowTitle("TermninalTelemetry Theme Editor")

    # Get the primary screen's geometry
    screen = app.primaryScreen()
    screen_geometry = screen.availableGeometry()

    # Calculate 80% width and 70% height
    width = int(screen_geometry.width() * 1)
    height = int(screen_geometry.height() * 1)

    # Set window size
    main_window.resize(width, height)

    # Center the window on screen (optional)
    main_window.setGeometry(
        int((screen_geometry.width() - width) / 2),
        int((screen_geometry.height() - height) / 2),
        width,
        height
    )

    # Create theme library
    theme_library = ThemeLibrary()

    # Create and set up theme editor widget
    theme_editor = ThemeEditorWidget(theme_manager=theme_library)

    # Connect theme changed signal to a handler
    def on_theme_changed(name, data):
        print(f"Theme changed: {name}")
        # Apply theme to the main window (basic styling only)
        main_window.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {data.get('background', '#000000')};
                color: {data.get('text', '#ffffff')};
            }}
        """)

    theme_editor.theme_changed.connect(on_theme_changed)

    # Set as central widget
    main_window.setCentralWidget(theme_editor)

    # Show window
    main_window.show()

    # Run application
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())