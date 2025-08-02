from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Dict, Optional, Any
import importlib.resources

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QFrame, QVBoxLayout


@dataclass
class ThemeColors:
    # Core colors
    primary: str
    secondary: str
    background: str
    darker_bg: str
    lighter_bg: str
    text: str
    grid: str
    line: str
    border: str
    success: str
    error: str

    # Effects
    border_light: str
    corner_gap: str
    corner_bright: str

    # Transparencies
    panel_bg: str
    scrollbar_bg: str
    selected_bg: str

    # Buttons
    button_hover: str
    button_pressed: str
    chart_bg: str

    # Terminal configuration
    terminal: Optional[Dict[str, Any]] = None
    context_menu: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ThemeColors':
        # Extract terminal configuration
        terminal_config = data.pop('terminal', None)
        context_menu_config = data.pop('context_menu', None)

        # Create instance with core theme fields
        theme_fields = {k: v for k, v in data.items() if k in cls.__annotations__}
        instance = cls(**theme_fields)

        # Set terminal and context menu configuration
        instance.terminal = terminal_config
        instance.context_menu = context_menu_config

        return instance

    def to_dict(self) -> Dict[str, Any]:
        result = self.__dict__.copy()
        if self.terminal is None:
            result.pop('terminal', None)
        if self.context_menu is None:
            result.pop('context_menu', None)
        return result


class ThemeLibrary:
    """Standard ThemeLibrary - loads all themes at startup (original behavior)"""

    def __init__(self):
        self.themes: Dict[str, ThemeColors] = {}
        self._load_default_themes()
        self._load_custom_themes()

    def _load_default_themes(self):
        """Load default built-in themes"""
        # Default cyberpunk theme
        cyberpunk = {
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
            "chart_bg": "rgba(6, 83, 89, 0.25)"
        }

        # Dark theme
        dark = {
            "primary": "#1f1f1f",
            "secondary": "#2b2b2b",
            "background": "#121212",
            "darker_bg": "#0d0d0d",
            "lighter_bg": "#eeeeee",
            "text": "#ffffff",
            "grid": "#2b2b2b",
            "line": "#3a86ff",
            "border": "#333333",
            "success": "#00e676",
            "error": "#ff1744",
            "border_light": "rgba(255, 255, 255, 0.4)",
            "corner_gap": "#121212",
            "corner_bright": "#ffffff",
            "panel_bg": "rgba(18, 18, 18, 0.98)",
            "scrollbar_bg": "rgba(33, 33, 33, 0.5)",
            "selected_bg": "rgba(255, 255, 255, 0.1)",
            "button_hover": "#333333",
            "button_pressed": "#444444",
            "chart_bg": "rgba(33, 33, 33, 0.2)"
        }

        # Add the default themes
        self.themes["cyberpunk"] = ThemeColors.from_dict(cyberpunk)
        self.themes["dark"] = ThemeColors.from_dict(dark)

    def _load_custom_themes(self):
        """Load custom themes from themes directory"""
        try:
            custom_themes_dir = Path("./themes")
            print(f"Loading themes from: {custom_themes_dir.absolute()}")

            custom_themes_dir.mkdir(exist_ok=True)
            print("Themes directory created/verified")

            if custom_themes_dir.exists():
                theme_files = list(custom_themes_dir.glob('*.json'))
                print(f"Found {len(theme_files)} theme files")

                for theme_file in custom_themes_dir.glob('*.json'):
                    try:
                        print(f"Loading theme from: {theme_file}")
                        with open(theme_file, 'r') as f:
                            theme_dict = json.load(f)
                            theme_colors = {k: v for k, v in theme_dict.items()
                                            if k in ThemeColors.__annotations__}
                            theme_name = theme_file.stem
                            self.themes[theme_name] = ThemeColors.from_dict(theme_colors)
                            print(f"Successfully loaded theme: {theme_name}")
                    except Exception as e:
                        print(f"Error loading theme {theme_file}: {e}")
        except Exception as e:
            print(f"Error in _load_custom_themes: {e}")

    def get_colors(self, theme_name: str) -> Dict[str, str]:
        """Return the color dictionary for the specified theme."""
        theme = self.get_theme(theme_name)
        if theme:
            return theme.to_dict()
        else:
            print(f"Colors for theme '{theme_name}' not found, returning default.")
            return self.get_theme("cyberpunk").to_dict()

    def get_chart_colors(self, theme_name: str) -> Dict[str, str]:
        """Alias for get_colors() for backwards compatibility."""
        return self.get_colors(theme_name)

    def get_theme(self, theme_name: str) -> Optional[ThemeColors]:
        """Get a theme by name"""
        return self.themes.get(theme_name)

    def add_theme(self, name: str, theme: ThemeColors, save: bool = True) -> bool:
        """Add a new theme and optionally save it to disk"""
        try:
            self.themes[name] = theme
            if save:
                self._save_theme(name, theme)
            return True
        except Exception as e:
            print(f"Error adding theme {name}: {e}")
            return False

    def _save_theme(self, name: str, theme: ThemeColors):
        """Save a theme to the user's themes directory"""
        home = Path("/")
        themes_dir = home / 'themes'
        themes_dir.mkdir(exist_ok=True)

        theme_path = themes_dir / f"{name}.json"
        with open(theme_path, 'w') as f:
            json.dump(theme.to_dict(), f, indent=2)

    def get_theme_names(self) -> list[str]:
        """Get a list of all available theme names"""
        return list(self.themes.keys())

    def generate_stylesheet(self, theme: ThemeColors) -> str:
        """Generate Qt stylesheet from theme colors with WebEngine context menu support"""
        # Get context menu colors, with fully opaque background
        if isinstance(theme, dict):
            # Create a temporary ThemeColors object from the dict
            from copy import deepcopy
            theme_dict = deepcopy(theme)
            temp_theme = ThemeColors()

            # Copy all attributes from the dict to the ThemeColors object
            for key, value in theme_dict.items():
                if key != 'terminal':  # Handle terminal separately
                    setattr(temp_theme, key, value)

            # Handle terminal specially since it's nested
            if 'terminal' in theme_dict:
                temp_theme.terminal = theme_dict['terminal']

            # Use the ThemeColors object instead
            theme = temp_theme

        context_menu = getattr(theme, 'context_menu', {}) or {
            'background': theme.secondary,
            'text': theme.text,
            'selected_bg': theme.selected_bg,
            'selected_text': theme.lighter_bg,
            'border': theme.border_light
        }

        # Ensure background color is fully opaque by converting any rgba to solid color
        menu_bg = context_menu['background']
        if menu_bg.startswith('rgba'):
            # If it's rgba, convert to solid color using theme.secondary
            menu_bg = theme.secondary

        return f"""
            QMainWindow, QWidget {{
                background-color: {theme.background};
                color: {theme.text};
                font-family: "Courier New";
            }}
            QGroupBox {{
                border: 1px solid {theme.border_light};
                margin-top: 1.5em;
                padding: 15px;
            }}
            QGroupBox::title {{
                color: {theme.text};
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            QPushButton {{
                background-color: {theme.darker_bg};
                border: 1px solid {theme.border_light};
                padding: 5px 15px;
                color: {theme.text};
            }}
            QPushButton:hover {{
                background-color: {theme.button_hover} !important;
                border: 1px solid {theme.text};
            }}
            QPushButton:pressed {{
                background-color: {theme.button_pressed};
            }}
            QLineEdit, QTextEdit {{
                background-color: {theme.darker_bg};
                border: 1px solid {theme.border_light};
                color: {theme.text};
                padding: 5px;
            }}
            QTreeWidget {{
                background-color: {theme.darker_bg};
                border: 1px solid {theme.border_light};
                color: {theme.text};
            }}
            QTreeWidget::item:selected {{
                background-color: {theme.selected_bg};
            }}
            QComboBox {{
                background-color: {theme.darker_bg};
                border: 1px solid {theme.border_light};
                color: {theme.text};
                padding: 5px;
            }}
            QComboBox:drop-down {{
                border: none;
            }}
            QComboBox:down-arrow {{
                border: 2px solid {theme.text};
                width: 6px;
                height: 6px;
            }}
            QFrame {{
                border-color: {theme.border_light};
            }}
            QWebEngineView {{
                background: {theme.background};
            }}
            QMenu {{
                background-color: {menu_bg} !important;
                color: {context_menu['text']};
                border: 1px solid {context_menu['border']};
                padding: 5px;
            }}
            QMenu::item {{
                background-color: {menu_bg};
                padding: 5px 30px 5px 30px;
                border: 1px solid transparent;
            }}
            QMenu::item:selected {{
                background-color: {context_menu['selected_bg']};
                color: {context_menu['selected_text']};
            }}
            QMenu::separator {{
                height: 1px;
                background: {context_menu['border']} !important;
                margin: 5px 0px 5px 0px;
            }}

            QScrollBar:vertical {{
                background-color: {theme.scrollbar_bg};
                width: 10px;
                margin: 0;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background: {theme.border_light};
                min-height: 20px;
                border-radius: 4px;
                border: none;
            }}

            QScrollBar::handle:vertical:hover {{
                background: {theme.text};
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
                background: none;
                border: none;
            }}

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: {theme.scrollbar_bg};
                border: none;
            }}
        """

    def apply_theme(self, widget, theme_name: str):
        """Apply a theme to a widget"""
        theme = self.get_theme(theme_name)
        if hasattr(widget, 'apply_theme') and callable(widget.apply_theme):
            # The widget has its own theme handling
            widget.apply_theme(self, theme_name)
            return
        if theme:
            stylesheet = self.generate_stylesheet(theme)
            widget.setStyleSheet(stylesheet)
        else:
            print(f"Theme '{theme_name}' not found")


class OptimizedThemeLibrary(ThemeLibrary):
    """Optimized ThemeLibrary that loads themes on-demand"""

    def __init__(self):
        self.themes: Dict[str, ThemeColors] = {}
        self._theme_file_cache = {}  # Cache of available theme files
        self._loaded_themes = set()  # Track which themes are actually loaded

        # Load default themes only
        self._load_default_themes()

        # Scan for available theme files but don't load them yet
        self._scan_theme_files()

    def _scan_theme_files(self):
        """Scan for available theme files without loading them"""
        try:
            custom_themes_dir = Path("./themes")

            if custom_themes_dir.exists():
                theme_files = list(custom_themes_dir.glob('*.json'))
                print(f"Found {len(theme_files)} theme files (not loaded yet)")

                for theme_file in theme_files:
                    theme_name = theme_file.stem
                    self._theme_file_cache[theme_name] = theme_file

        except Exception as e:
            print(f"Error scanning theme files: {e}")

    def get_theme_names(self) -> list[str]:
        """Get list of all available themes (loaded + available files)"""
        # Return both loaded themes and available theme files
        all_themes = set(self.themes.keys()) | set(self._theme_file_cache.keys())
        return sorted(list(all_themes))

    def get_theme(self, theme_name: str) -> Optional[ThemeColors]:
        """Get theme, loading it on-demand if needed"""
        # If already loaded, return it
        if theme_name in self.themes:
            return self.themes[theme_name]

        # If available as file, load it now
        if theme_name in self._theme_file_cache and theme_name not in self._loaded_themes:
            self._load_theme_file(theme_name)
            self._loaded_themes.add(theme_name)
            return self.themes.get(theme_name)

        print(f"Theme '{theme_name}' not found")
        return None

    def _load_theme_file(self, theme_name: str):
        """Load a specific theme file"""
        if theme_name not in self._theme_file_cache:
            return

        theme_file = self._theme_file_cache[theme_name]
        try:
            print(f"Loading theme on-demand: {theme_name}")
            with open(theme_file, 'r') as f:
                theme_dict = json.load(f)
                theme_colors = {k: v for k, v in theme_dict.items()
                              if k in ThemeColors.__annotations__}
                self.themes[theme_name] = ThemeColors.from_dict(theme_colors)
                print(f"Successfully loaded theme: {theme_name}")
        except Exception as e:
            print(f"Error loading theme {theme_file}: {e}")

    def get_colors(self, theme_name: str) -> Dict[str, str]:
        """Return the color dictionary for the specified theme (with on-demand loading)"""
        theme = self.get_theme(theme_name)
        if theme:
            return theme.to_dict()
        else:
            print(f"Colors for theme '{theme_name}' not found, returning default.")
            fallback = self.get_theme("cyberpunk") or self.get_theme("dark")
            return fallback.to_dict() if fallback else {}

    def get_loaded_theme_count(self) -> int:
        """Get count of actually loaded themes (for debugging)"""
        return len(self.themes)

    def get_available_theme_count(self) -> int:
        """Get count of available themes (loaded + files)"""
        return len(self.get_theme_names())


# For backwards compatibility, keep ThemeMapper and other classes
class ThemeMapper:
    """Maps application themes to terminal themes with dictionary-like behavior"""

    def __init__(self, theme_library):
        self.theme_library = theme_library
        self._default_mappings = {
            "cyberpunk": "Cyberpunk",
            "dark_mode": "Dark",
            "light_mode": "Light",
            "retro_green": "Green",
            "retro_amber": "Amber",
            "neon_blue": "Neon"
        }
        # Cache the mapping to avoid regenerating it repeatedly
        self._mapping = None

    def _generate_mapping(self):
        """Generate mapping dictionary from theme library"""
        mapping = {}

        # Get all available themes
        for theme_name in self.theme_library.get_theme_names():
            theme = self.theme_library.get_theme(theme_name)

            # Check if theme has terminal config in JSON
            if hasattr(theme, 'terminal') and theme.terminal and hasattr(theme.terminal, 'theme'):
                terminal_theme = theme.terminal.theme.get('name', self._default_mappings.get(theme_name))
                if terminal_theme:
                    mapping[theme_name] = terminal_theme
            else:
                # Fall back to default mapping
                mapping[theme_name] = self._default_mappings.get(theme_name, "Cyberpunk")

        return mapping

    @property
    def mapping(self):
        """Lazy-load and cache the mapping"""
        if self._mapping is None:
            self._mapping = self._generate_mapping()
        return self._mapping

    def get(self, key, default=None):
        """Dictionary-style get method with default value"""
        return self.mapping.get(key, default)

    def __getitem__(self, key):
        """Dictionary-style bracket access"""
        return self.mapping[key]

    def __contains__(self, key):
        """Support for 'in' operator"""
        return key in self.mapping

    def __iter__(self):
        """Support for iteration"""
        return iter(self.mapping)

    def __len__(self):
        """Support for len()"""
        return len(self.mapping)

    def items(self):
        """Support for .items() method"""
        return self.mapping.items()

    def keys(self):
        """Support for .keys() method"""
        return self.mapping.keys()

    def values(self):
        """Support for .values() method"""
        return self.mapping.values()

    def refresh(self):
        """Force regeneration of the mapping"""
        self._mapping = None
        return self.mapping


# Keep all other classes (LayeredHUDFrame, generate_terminal_themes, etc.) unchanged from original themes.py
class LayeredHUDFrame(QFrame):
    def __init__(self, parent=None, theme_manager=None, theme_name="cyberpunk"):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.theme_name = theme_name
        self.setup_ui()
        if theme_manager:
            self.update_theme_colors()

    def setup_ui(self):
        # Main content layout
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(1, 1, 1, 1)

        # Create corner lines (bright)
        self.corner_lines = []
        for i in range(8):
            line = QFrame(self)
            if i < 4:  # Horizontal corner pieces
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(1)
            else:  # Vertical corner pieces
                line.setFrameShape(QFrame.Shape.VLine)
                line.setFixedWidth(1)
            self.corner_lines.append(line)

        # Create connecting lines (dim)
        self.connecting_lines = []
        for i in range(4):
            line = QFrame(self)
            if i < 2:  # Horizontal connectors
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFixedHeight(1)
            else:  # Vertical connectors
                line.setFrameShape(QFrame.Shape.VLine)
                line.setFixedWidth(1)
            self.connecting_lines.append(line)

        self.setStyleSheet("background-color: transparent;")

        # Set initial colors (will be overridden if theme_manager is provided)
        self.update_line_colors("#0f969e", "rgba(15, 150, 158, 0.3)")

    def update_theme_colors(self):
        """Update colors based on current theme"""
        if self.theme_manager:
            # Get theme colors - handle both old and new theme managers
            if hasattr(self.theme_manager, 'get_colors'):
                # New ThemeLibrary way
                colors = self.theme_manager.get_colors(self.theme_name)
            else:
                # Fallback for old theme manager
                colors = self.theme_manager.get_chart_colors(self.theme_name)

            if isinstance(colors, dict):
                # Get colors directly from dict
                bright_color = colors.get('corner_bright', colors.get('border', '#0f969e'))
                dim_color = colors.get('border_light', 'rgba(15, 150, 158, 0.3)')
            else:
                # Handle ThemeColors dataclass
                bright_color = getattr(colors, 'corner_bright', getattr(colors, 'border', '#0f969e'))
                dim_color = getattr(colors, 'border_light', 'rgba(15, 150, 158, 0.3)')

            # Convert hex to rgba if needed
            if bright_color.startswith('#'):
                r = int(bright_color[1:3], 16)
                g = int(bright_color[3:5], 16)
                b = int(bright_color[5:7], 16)
                dim_color = f"rgba({r}, {g}, {b}, 0.4)"

            self.update_line_colors(bright_color, dim_color)

    def update_line_colors(self, bright_color, dim_color):
        """Update line colors with provided colors"""
        # Update corner lines (bright)
        for line in self.corner_lines:
            line.setStyleSheet(f"background-color: {bright_color};")

        # Update connecting lines (dim)
        for line in self.connecting_lines:
            line.setStyleSheet(f"background-color: {dim_color};")

    def set_theme(self, theme_name):
        """Change the theme of the frame"""
        self.theme_name = theme_name
        self.update_theme_colors()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        corner_length = 20  # Length of bright corner pieces

        # Top-left corner
        self.corner_lines[0].setGeometry(0, 0, corner_length, 1)  # Horizontal
        self.corner_lines[4].setGeometry(0, 0, 1, corner_length)  # Vertical

        # Top-right corner
        self.corner_lines[1].setGeometry(w - corner_length, 0, corner_length, 1)  # Horizontal
        self.corner_lines[5].setGeometry(w - 1, 0, 1, corner_length)  # Vertical

        # Bottom-left corner
        self.corner_lines[2].setGeometry(0, h - 1, corner_length, 1)  # Horizontal
        self.corner_lines[6].setGeometry(0, h - corner_length, 1, corner_length)  # Vertical

        # Bottom-right corner
        self.corner_lines[3].setGeometry(w - corner_length, h - 1, corner_length, 1)  # Horizontal
        self.corner_lines[7].setGeometry(w - 1, h - corner_length, 1, corner_length)  # Vertical

        # Connecting lines (dim)
        # Top
        self.connecting_lines[0].setGeometry(corner_length, 0, w - 2 * corner_length, 1)
        # Bottom
        self.connecting_lines[1].setGeometry(corner_length, h - 1, w - 2 * corner_length, 1)
        # Left
        self.connecting_lines[2].setGeometry(0, corner_length, 1, h - 2 * corner_length)
        # Right
        self.connecting_lines[3].setGeometry(w - 1, corner_length, 1, h - 2 * corner_length)