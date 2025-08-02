# Add this to your Flask app or a separate theme module

import json
import os
from flask import request, session, app


class ThemeManager:
    def __init__(self, theme_dir="themes"):
        self.theme_dir = theme_dir
        self.themes = {}
        self.load_themes()

    def load_themes(self):
        """Load all theme files from the themes directory"""
        theme_files = {
            'dark': 'dark.json',
            'gruvbox': 'gruvbox.json',
            'light': 'light.json'
        }

        for theme_name, filename in theme_files.items():
            filepath = os.path.join(self.theme_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    self.themes[theme_name] = json.load(f)
            else:
                # Fallback to default dark theme
                self.themes[theme_name] = self.get_default_theme()

    def get_default_theme(self):
        """Default dark theme as fallback"""
        return {
            "primary": "#0F172A",
            "secondary": "#1E293B",
            "background": "#0F172A",
            "darker_bg": "#0D1526",
            "lighter_bg": "#1E293B",
            "text": "#E2E8F0",
            "grid": "rgba(59, 130, 246, 0.1)",
            "line": "#3B82F6",
            "border": "#3B82F6",
            "success": "#22C55E",
            "error": "#EF4444",
            "border_light": "rgba(226, 232, 240, 0.4)",
            "corner_gap": "#0F172A",
            "corner_bright": "#3B82F6",
            "panel_bg": "rgba(15, 23, 42, 0.95)",
            "scrollbar_bg": "rgba(226, 232, 240, 0.1)",
            "selected_bg": "rgba(226, 232, 240, 0.2)",
            "button_hover": "#1E293B",
            "button_pressed": "#0D1526",
            "chart_bg": "rgba(15, 23, 42, 0.25)"
        }

    def get_current_theme(self):
        """Get the current theme based on session or default"""
        theme_name = session.get('theme', 'dark')
        return self.themes.get(theme_name, self.themes['dark'])

    def set_theme(self, theme_name):
        """Set the current theme in session"""
        if theme_name in self.themes:
            session['theme'] = theme_name
            return True
        return False

    def get_available_themes(self):
        """Get list of available theme names"""
        return list(self.themes.keys())


# Initialize theme manager
theme_manager = ThemeManager()


# Add to your Flask app setup
def setup_theme_context(app):
    """Add theme context processor to Flask app"""

    @app.context_processor
    def inject_theme():
        return {
            'theme': theme_manager.get_current_theme(),
            'current_theme_name': session.get('theme', 'dark'),
            'available_themes': theme_manager.get_available_themes()
        }

    @app.route('/api/theme', methods=['GET', 'POST'])
    def theme_api():
        if request.method == 'POST':
            data = request.get_json()
            theme_name = data.get('theme')
            if theme_manager.set_theme(theme_name):
                return {'success': True, 'theme': theme_name}
            return {'success': False, 'error': 'Invalid theme'}, 400
        else:
            return {
                'current_theme': session.get('theme', 'dark'),
                'available_themes': theme_manager.get_available_themes(),
                'theme_data': theme_manager.get_current_theme()
            }


def sync_theme_from_desktop():
    """Sync theme from PyQt6 desktop app"""
    try:
        data = request.get_json()
        theme_name = data.get('theme')

        if not theme_name:
            return {'success': False, 'error': 'No theme specified'}, 400

        # If theme data is provided directly from PyQt6
        if 'theme_data' in data:
            theme_manager.themes[theme_name] = data['theme_data']

        if theme_manager.set_theme(theme_name):
            return {
                'success': True,
                'theme': theme_name,
                'applied_theme': theme_manager.get_current_theme()
            }

        return {'success': False, 'error': 'Failed to apply theme'}, 400

    except Exception as e:
        return {'success': False, 'error': str(e)}, 500


# Chart.js color palette generator based on current theme
def get_chart_colors(theme_data):
    """Generate Chart.js compatible color palette from theme"""
    return [
        theme_data.get('line', '#3B82F6'),
        theme_data.get('success', '#22C55E'),
        '#d79921',  # Yellow
        theme_data.get('error', '#EF4444'),
        '#d946ef',  # Magenta
        '#06b6d4',  # Cyan
        '#f59e0b',  # Amber
        '#8b5cf6',  # Violet
        '#ef4444',  # Red variant
        '#10b981'  # Emerald
    ]