# Theme Management System

A comprehensive theme management system for PyQt6 applications with Flask web component integration, providing dynamic color palettes, real-time theme synchronization, and consistent visual experiences across desktop and web interfaces.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [PyQt6 Theme Manager](#pyqt6-theme-manager)
- [Flask Integration](#flask-integration)
- [Theme Bridge System](#theme-bridge-system)
- [Color Palette Management](#color-palette-management)
- [Usage Examples](#usage-examples)
- [Adding New Components](#adding-new-components)
- [Theme File Format](#theme-file-format)
- [Troubleshooting](#troubleshooting)

## Overview

The theme management system consists of four main components:

1. **PyQt6 Theme Manager** (`themes3.py`) - Core theme management and palette generation
2. **Flask API Integration** - RESTful endpoints for web components
3. **Theme Bridge System** - Real-time synchronization between Qt and web views
4. **Dynamic Color Palettes** - Smart color generation for charts and visualizations

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   PyQt6 App     │    │   Theme Bridge   │    │   Flask Web     │
│                 │◄──►│                  │◄──►│   Components    │
│ • Theme Manager │    │ • QWebChannel    │    │ • API Endpoints │
│ • Color Palettes│    │ • Signal/Slots   │    │ • Chart Colors  │
│ • Stylesheets   │    │ • JS Bridge      │    │ • CSS Variables │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## PyQt6 Theme Manager

### Core Classes

#### `ThemeColors`
Dataclass defining the complete color scheme for a theme:

```python
@dataclass
class ThemeColors:
    # Core colors
    primary: str
    secondary: str
    background: str
    darker_bg: str
    lighter_bg: str
    text: str
    
    # UI elements
    grid: str
    line: str
    border: str
    success: str
    error: str
    
    # Effects and transparency
    border_light: str
    corner_gap: str
    corner_bright: str
    panel_bg: str
    scrollbar_bg: str
    selected_bg: str
    
    # Interactive elements
    button_hover: str
    button_pressed: str
    chart_bg: str
    
    # Optional terminal configuration
    terminal: Optional[Dict[str, Any]] = None
```

#### `ThemeLibrary`
Main theme management class:

```python
# Initialize theme library
theme_manager = ThemeLibrary()

# Get available themes
themes = theme_manager.get_theme_names()

# Apply theme to widget
theme_manager.apply_theme(widget, "cyberpunk")

# Get theme colors
colors = theme_manager.get_colors("cyberpunk")
```

### Key Methods

#### Color Palette Generation
```python
def generate_chart_palette(self, theme_name: str, count: int = 10) -> list[str]:
    """Generate diverse color palette for charts from theme colors"""
    # Creates variations of theme colors for better chart visualization
    
def get_web_theme_data(self, theme_name: str) -> dict:
    """Get theme data optimized for web dashboard with chart palette"""
    # Returns complete theme data including chart colors for web components
```

#### Terminal Theme Generation
```python
def generate_terminal_js(self, theme: ThemeColors) -> str:
    """Generate terminal theme JavaScript for xterm.js"""
    # Creates JavaScript code to apply theme to embedded terminals
```

## Flask Integration

### API Endpoints

#### Theme Information
```python
# Get all available themes
GET /api/themes
Response: {
    "themes": [{"name": "cyberpunk", "display_name": "Cyberpunk"}],
    "current_theme": "cyberpunk",
    "count": 10
}

# Get specific theme data
GET /api/theme/<theme_name>
Response: {
    "name": "cyberpunk",
    "data": { /* theme colors */ }
}

# Get chart colors for theme
GET /api/theme/<theme_name>/chart-colors
Response: {
    "theme_name": "cyberpunk",
    "chart_palette": ["#0affff", "#0a8993", "#ff4c4c", ...],
    "primary_colors": { /* key theme colors */ }
}
```

#### Theme Preview
```python
# Preview theme without applying
GET /api/theme/preview/<theme_name>
Response: {
    "name": "cyberpunk", 
    "css_variables": { "--primary": "#0a8993" },
    "colors": { /* preview colors */ }
}
```

### Flask Implementation

#### Basic Setup
```python
# In your Flask app
from pathlib import Path
import json

@app.route('/api/theme/<theme_name>/chart-colors')
def api_theme_chart_colors(theme_name):
    """API endpoint to get chart colors for a specific theme"""
    try:
        theme_file = Path('themes') / f'{theme_name}.json'
        if not theme_file.exists():
            return jsonify({'error': f'Theme {theme_name} not found'}), 404

        with open(theme_file, 'r') as f:
            theme_data = json.load(f)

        chart_colors = generate_chart_colors_from_theme(theme_data)
        
        return jsonify({
            'theme_name': theme_name,
            'chart_palette': chart_colors,
            'primary_colors': extract_primary_colors(theme_data)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

#### Context Processor
```python
@app.context_processor
def inject_theme():
    """Inject theme data into all templates"""
    current_theme = request.args.get('theme', session.get('theme', 'dark'))
    session['theme'] = current_theme
    
    # Load theme data
    theme_data = load_theme_data(current_theme)
    
    return {
        'theme': theme_data,
        'current_theme_name': current_theme,
        'available_themes': get_available_themes()
    }
```

## Theme Bridge System

### Python Bridge Component

#### `ThemeBridge` Class
```python
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

class ThemeBridge(QObject):
    """Bridge object to communicate theme changes to web views"""
    
    theme_changed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_theme = "cyberpunk"
    
    @pyqtSlot(str)
    def set_theme(self, theme_name):
        """Set current theme and notify all web views"""
        self.current_theme = theme_name
        self.theme_changed.emit(theme_name)
    
    @pyqtSlot(result=str)
    def get_current_theme(self):
        """Get current theme name"""
        return self.current_theme
```

#### `CMDBWrapper` Integration
```python
class CMDBWrapper:
    def __init__(self, cmdb_widget, parent_window=None):
        from PyQt6.QtWebChannel import QWebChannel
        
        self.cmdb = cmdb_widget
        self.parent_window = parent_window
        self.channel = QWebChannel()
        
        # Create and register theme bridge
        self.theme_bridge = ThemeBridge()
        if parent_window and hasattr(parent_window, 'theme'):
            self.theme_bridge.current_theme = parent_window.theme
            
        self.channel.registerObject("themeBridge", self.theme_bridge)
        cmdb_widget.page().setWebChannel(self.channel)
        
        # Connect to parent theme changes
        if parent_window and hasattr(parent_window, 'theme_changed'):
            parent_window.theme_changed.connect(self.theme_bridge.set_theme)

    def update_theme(self, theme_name):
        """Update theme for this web view"""
        self.theme_bridge.set_theme(theme_name)
```

### JavaScript Bridge Component

#### QWebChannel Integration
```javascript
function waitForQtWebChannel() {
    return new Promise((resolve, reject) => {
        // ... existing QWebChannel initialization code ...
        
        new QWebChannel(qt.webChannelTransport, function(channel) {
            // Register theme bridge
            if (channel.objects.themeBridge) {
                window.themeBridge = channel.objects.themeBridge;
                console.log('Theme bridge registered');
            }
            
            resolve(channel);
        });
    });
}

function setupThemeListener() {
    if (window.themeBridge) {
        // Listen for theme changes from Qt
        window.themeBridge.theme_changed.connect(function(themeName) {
            console.log('Theme change received:', themeName);
            applyThemeChange(themeName);
        });
    }
}

function applyThemeChange(themeName) {
    // Prevent reload loops
    const urlParams = new URLSearchParams(window.location.search);
    const currentUrlTheme = urlParams.get('theme');
    
    if (currentUrlTheme === themeName) {
        return; // Already on correct theme
    }
    
    // Update URL and reload
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.set('theme', themeName);
    window.location.href = currentUrl.toString();
}
```

## Color Palette Management

### Chart Color Generation

#### Dynamic Palette Creation
```python
def generate_chart_palette(self, theme_name: str, count: int = 10) -> list[str]:
    """Generate diverse color palette for charts"""
    theme = self.get_theme(theme_name)
    
    # Base colors from theme
    base_colors = [
        theme.line,       # Primary accent
        theme.success,    # Success/positive
        theme.error,      # Error/negative  
        theme.primary,    # Primary brand
        theme.secondary,  # Secondary brand
        theme.grid,       # Grid/subtle accent
    ]
    
    # Generate variations
    additional_colors = []
    for color in base_colors[:3]:
        if color.startswith('#'):
            r, g, b = hex_to_rgb(color)
            
            # Lighter version
            lighter = rgb_to_hex(
                min(255, int(r * 1.3)),
                min(255, int(g * 1.3)),
                min(255, int(b * 1.3))
            )
            additional_colors.append(lighter)
            
            # Darker version
            darker = rgb_to_hex(
                max(0, int(r * 0.7)),
                max(0, int(g * 0.7)),
                max(0, int(b * 0.7))
            )
            additional_colors.append(darker)
    
    return (base_colors + additional_colors)[:count]
```

#### JavaScript Chart Integration
```javascript
// Load theme-specific chart colors
async function loadChartColors() {
    const currentTheme = getCurrentThemeName();
    try {
        const response = await fetch(`/api/theme/${currentTheme}/chart-colors`);
        const data = await response.json();
        
        if (data.chart_palette) {
            currentChartColors = data.chart_palette;
        } else {
            // Fallback to CSS variable-based colors
            const theme = getThemeColors();
            currentChartColors = [
                theme.line, theme.success, theme.error,
                theme.primary, theme.secondary,
                // ... additional fallback colors
            ];
        }
    } catch (error) {
        console.error('Failed to load chart colors:', error);
        // Use hardcoded fallbacks
    }
}

// Apply colors to Chart.js
function initializeCharts() {
    await loadChartColors();
    const chartColors = getChartColors();
    
    // Vendor chart with different colors per segment
    vendorChart = new Chart(vendorCtx, {
        type: 'doughnut',
        data: {
            datasets: [{
                backgroundColor: chartColors.slice(0, vendorData.length),
                // ... other config
            }]
        }
    });
    
    // Role chart with different colors per bar
    const roleColors = roleData.map((_, index) => 
        chartColors[index % chartColors.length]
    );
    
    roleChart = new Chart(roleCtx, {
        type: 'bar',
        data: {
            datasets: [{
                backgroundColor: roleColors,
                // ... other config
            }]
        }
    });
}
```

## Usage Examples

### Adding Theme Support to a New PyQt Widget

```python
# 1. Basic theme application
class MyWidget(QWidget):
    def __init__(self, parent=None, theme_manager=None, theme_name="cyberpunk"):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.theme_name = theme_name
        
        if theme_manager:
            theme_manager.apply_theme(self, theme_name)
    
    def update_theme(self, theme_name):
        """Update widget theme"""
        self.theme_name = theme_name
        if self.theme_manager:
            self.theme_manager.apply_theme(self, theme_name)
```

### Adding Theme Support to Flask Routes

```python
# 1. Theme-aware route
@app.route('/my-dashboard')
def my_dashboard():
    current_theme = session.get('theme', 'dark')
    theme_data = load_theme_data(current_theme)
    
    return render_template('dashboard.html', 
                         theme=theme_data,
                         current_theme_name=current_theme)

# 2. Chart colors API
@app.route('/api/my-component/colors')
def my_component_colors():
    theme_name = request.args.get('theme', session.get('theme', 'dark'))
    chart_colors = generate_chart_colors_from_theme(theme_name)
    
    return jsonify({
        'colors': chart_colors,
        'theme': theme_name
    })
```

### Adding Theme Support to Web Components

```html
<!-- 1. CSS Variables in template -->
<style>
:root {
    --primary: {{ theme.primary }};
    --background: {{ theme.background }};
    --text: {{ theme.text }};
    /* ... other variables */
}

.my-component {
    background-color: var(--background);
    color: var(--text);
    border: 1px solid var(--primary);
}
</style>
```

```javascript
// 2. Dynamic color loading
async function loadMyComponentColors() {
    const theme = getCurrentTheme();
    const response = await fetch(`/api/my-component/colors?theme=${theme}`);
    const data = await response.json();
    
    // Apply colors to your component
    applyColorsToMyComponent(data.colors);
}
```

## Adding New Components

### Step 1: Define Color Requirements
```python
# Identify what colors your component needs
COMPONENT_COLOR_MAPPING = {
    'chart_colors': 8,        # Number of distinct colors needed
    'status_colors': 4,       # Success, warning, error, info
    'ui_colors': 3,          # Background, text, accent
}
```

### Step 2: Extend Theme Manager
```python
# Add component-specific method to ThemeLibrary
def get_component_colors(self, theme_name: str, component: str) -> dict:
    """Get colors specific to a component"""
    theme = self.get_theme(theme_name)
    
    if component == 'my_component':
        return {
            'primary': theme.primary,
            'secondary': theme.secondary,
            'chart_palette': self.generate_chart_palette(theme_name, 8),
            'status': {
                'success': theme.success,
                'error': theme.error,
                'warning': '#d79921',
                'info': theme.line
            }
        }
```

### Step 3: Add Flask API
```python
@app.route('/api/theme/<theme_name>/<component>/colors')
def api_component_colors(theme_name, component):
    """Get colors for specific component"""
    try:
        # Use your theme manager here
        colors = theme_manager.get_component_colors(theme_name, component)
        return jsonify({
            'component': component,
            'theme': theme_name,
            'colors': colors
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### Step 4: Add Bridge Support (if needed)
```python
# If component is in a QWebEngineView, extend CMDBWrapper
class MyComponentWrapper(CMDBWrapper):
    def __init__(self, widget, parent_window=None):
        super().__init__(widget, parent_window)
        # Component-specific initialization
        
    def update_component_theme(self, theme_name):
        """Update theme for this specific component"""
        # Trigger component-specific theme update
        self.theme_bridge.set_theme(theme_name)
```

## Theme File Format

### Basic Theme Structure
```json
{
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
```

### Extended Theme with Terminal Support
```json
{
  // ... basic colors above ...
  
  "terminal": {
    "theme": {
      "foreground": "#0affff",
      "background": "#111111",
      "cursor": "#ffff66",
      "black": "#1a1a1a",
      "red": "#ff4c4c",
      "green": "#0a8993",
      "yellow": "#ffff66",
      "blue": "#0ac0c8",
      "magenta": "#ff66ff",
      "cyan": "#00ffff",
      "white": "#ffffff",
      "brightBlack": "#666666",
      "brightRed": "#ff6666",
      "brightGreen": "#66ff66",
      "brightYellow": "#ffff99",
      "brightBlue": "#66b3ff",
      "brightMagenta": "#ff99ff",
      "brightCyan": "#99ffff",
      "brightWhite": "#ffffff",
      "selectionBackground": "rgba(10, 137, 147, 0.25)",
      "selectionForeground": "#0affff"
    },
    "scrollbar": {
      "background": "rgba(6, 20, 22, 0.6)",
      "thumb": "rgba(10, 255, 255, 0.5)",
      "thumb_hover": "#0affff"
    }
  },
  
  "context_menu": {
    "background": "#065359",
    "text": "#0affff", 
    "selected_bg": "rgba(10, 137, 147, 0.25)",
    "selected_text": "#ffffff",
    "border": "rgba(10, 255, 255, 0.5)"
  }
}
```

## Troubleshooting

### Common Issues

#### 1. Theme Bridge Not Working
```javascript
// Check if QWebChannel is properly initialized
console.log('QWebChannel objects:', Object.keys(channel.objects));

// Verify theme bridge registration
if (!window.themeBridge) {
    console.error('Theme bridge not found. Check CMDBWrapper registration.');
}
```

#### 2. Colors Not Updating
```python
# Verify theme manager is properly initialized
if not hasattr(self, 'theme_manager'):
    print("Theme manager not initialized")

# Check theme file exists
theme_file = Path('themes') / f'{theme_name}.json'
if not theme_file.exists():
    print(f"Theme file not found: {theme_file}")
```

#### 3. Chart Colors Not Loading
```javascript
// Check API endpoint
fetch('/api/theme/cyberpunk/chart-colors')
    .then(response => response.json())
    .then(data => console.log('API Response:', data))
    .catch(error => console.error('API Error:', error));

// Verify fallback colors
console.log('Current chart colors:', currentChartColors);
```

#### 4. Flask Template Variables Missing
```python
# Ensure context processor is registered
@app.context_processor
def inject_theme():
    # ... theme injection code

# Check template context
print("Theme context:", inject_theme())
```

### Debug Commands

```python
# PyQt6 Theme Manager Debug
theme_manager = ThemeLibrary()
print("Available themes:", theme_manager.get_theme_names())
print("Theme colors:", theme_manager.get_colors("cyberpunk"))
print("Chart palette:", theme_manager.generate_chart_palette("cyberpunk"))

# Flask Debug
with app.test_client() as client:
    response = client.get('/api/theme/cyberpunk/chart-colors')
    print("API Response:", response.get_json())
```

```javascript
// JavaScript Debug
console.log('Theme colors from CSS:', getThemeColors());
console.log('Chart colors loaded:', currentChartColors);
console.log('QWebChannel objects:', Object.keys(window));
```

---

## Contributing

When adding new theme-aware components:

1. Follow the established color mapping patterns
2. Add appropriate Flask API endpoints  
3. Include fallback color support
4. Test theme switching functionality
5. Update this documentation

For questions or issues, refer to the theme manager source code in `themes3.py` and the bridge implementation in your QWebEngineView wrappers.