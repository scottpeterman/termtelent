"""
Enhanced theme-aware SVG implementation with fixes for triangle rendering issues.
"""
from PyQt6.QtCore import QBuffer, Qt
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import QVBoxLayout, QLabel, QHBoxLayout

def apply_theme_to_svg_widget(svg_widget, theme_colors, size=32):
    """
    Apply theme colors to an existing QSvgWidget.

    Args:
        svg_widget: QSvgWidget instance to update
        theme_colors: ThemeColors instance or dictionary
        size: Size to set for the widget
    """
    # Generate themed SVG content
    svg_content = get_themed_svg(theme_colors)

    # Load SVG content into widget
    svg_bytes = svg_content.encode('utf-8')
    buffer = QBuffer()
    buffer.setData(svg_bytes)
    buffer.open(QBuffer.OpenModeFlag.ReadOnly)
    svg_widget.load(buffer.data())

    # Set fixed size
    svg_widget.setFixedSize(size, size)

def create_themed_button_with_svg(parent, button, theme_colors, label_text="CONNECT", size=32):
    """
    Create a themed button with an SVG icon.

    Args:
        parent: Parent widget
        button: QPushButton to configure
        theme_colors: ThemeColors instance or dictionary
        label_text: Text to display on the button
        size: Size of the SVG icon

    Returns:
        Configured button with SVG icon
    """
    # Create SVG widget
    icon_widget = QSvgWidget()
    apply_theme_to_svg_widget(icon_widget, theme_colors, size)

    # Create button layout
    button_layout = QHBoxLayout(button)
    button_layout.setContentsMargins(10, 5, 10, 5)
    button_layout.addWidget(icon_widget)
    button_layout.addWidget(QLabel(label_text))
    button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # Style the button based on theme
    if isinstance(theme_colors, dict):
        text_color = theme_colors.get('text', '#ffffff')
        bg_color = theme_colors.get('darker_bg', '#333333')
        border_color = theme_colors.get('border_light', 'rgba(255,255,255,0.5)')
        hover_color = theme_colors.get('button_hover', '#444444')
        pressed_color = theme_colors.get('button_pressed', '#222222')
    else:
        # Handle ThemeColors object
        text_color = getattr(theme_colors, 'text', '#ffffff')
        bg_color = getattr(theme_colors, 'darker_bg', '#333333')
        border_color = getattr(theme_colors, 'border_light', 'rgba(255,255,255,0.5)')
        hover_color = getattr(theme_colors, 'button_hover', '#444444')
        pressed_color = getattr(theme_colors, 'button_pressed', '#222222')

    button.setStyleSheet(f"""
        QPushButton {{
            background-color: {bg_color};
            color: {text_color};
            border: 1px solid {border_color};
            padding: 8px 15px;
            font-family: "Courier New";
            text-transform: uppercase;
            min-height: 30px;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
            border: 1px solid {text_color};
        }}
        QPushButton:pressed {{
            background-color: {pressed_color};
            border: 1px solid {text_color};
        }}
    """)

    return button


def get_themed_svg(theme_colors=None):
    """
    Generate a themed version of the SVG logo based on provided theme colors.
    Preserves all details from the original SVG including grid lines, circles, and glow effects.

    Args:
        theme_colors: ThemeColors instance or dictionary, or None for default colors

    Returns:
        Themed SVG content as string
    """
    # Base SVG with key color placeholders
    svg_template = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <!-- Dark background -->
  <rect width="500" height="500" fill="{bg_color}"/>

  <!-- Grid pattern -->
  <g stroke="{primary_color}" stroke-width="0.5" opacity="0.3">
    <!-- Vertical lines -->
    <g>
      <line x1="25" y1="0" x2="25" y2="500"/>
      <line x1="50" y1="0" x2="50" y2="500"/>
      <line x1="75" y1="0" x2="75" y2="500"/>
      <line x1="100" y1="0" x2="100" y2="500"/>
      <line x1="125" y1="0" x2="125" y2="500"/>
      <line x1="150" y1="0" x2="150" y2="500"/>
      <line x1="175" y1="0" x2="175" y2="500"/>
      <line x1="200" y1="0" x2="200" y2="500"/>
      <line x1="225" y1="0" x2="225" y2="500"/>
      <line x1="250" y1="0" x2="250" y2="500"/>
      <line x1="275" y1="0" x2="275" y2="500"/>
      <line x1="300" y1="0" x2="300" y2="500"/>
      <line x1="325" y1="0" x2="325" y2="500"/>
      <line x1="350" y1="0" x2="350" y2="500"/>
      <line x1="375" y1="0" x2="375" y2="500"/>
      <line x1="400" y1="0" x2="400" y2="500"/>
      <line x1="425" y1="0" x2="425" y2="500"/>
      <line x1="450" y1="0" x2="450" y2="500"/>
      <line x1="475" y1="0" x2="475" y2="500"/>
    </g>

    <!-- Horizontal lines -->
    <g>
      <line x1="0" y1="25" x2="500" y2="25"/>
      <line x1="0" y1="50" x2="500" y2="50"/>
      <line x1="0" y1="75" x2="500" y2="75"/>
      <line x1="0" y1="100" x2="500" y2="100"/>
      <line x1="0" y1="125" x2="500" y2="125"/>
      <line x1="0" y1="150" x2="500" y2="150"/>
      <line x1="0" y1="175" x2="500" y2="175"/>
      <line x1="0" y1="200" x2="500" y2="200"/>
      <line x1="0" y1="225" x2="500" y2="225"/>
      <line x1="0" y1="250" x2="500" y2="250"/>
      <line x1="0" y1="275" x2="500" y2="275"/>
      <line x1="0" y1="300" x2="500" y2="300"/>
      <line x1="0" y1="325" x2="500" y2="325"/>
      <line x1="0" y1="350" x2="500" y2="350"/>
      <line x1="0" y1="375" x2="500" y2="375"/>
      <line x1="0" y1="400" x2="500" y2="400"/>
      <line x1="0" y1="425" x2="500" y2="425"/>
      <line x1="0" y1="450" x2="500" y2="450"/>
      <line x1="0" y1="475" x2="500" y2="475"/>
    </g>

    <!-- Grid dots -->
    <g fill="{primary_color}">
      <g id="dot-row" opacity="0.8">
        <circle cx="25" cy="25" r="1.5"/>
        <circle cx="50" cy="25" r="1.5"/>
        <circle cx="75" cy="25" r="1.5"/>
        <circle cx="100" cy="25" r="1.5"/>
        <circle cx="125" cy="25" r="1.5"/>
        <circle cx="150" cy="25" r="1.5"/>
        <circle cx="175" cy="25" r="1.5"/>
        <circle cx="200" cy="25" r="1.5"/>
        <circle cx="225" cy="25" r="1.5"/>
        <circle cx="250" cy="25" r="1.5"/>
        <circle cx="275" cy="25" r="1.5"/>
        <circle cx="300" cy="25" r="1.5"/>
        <circle cx="325" cy="25" r="1.5"/>
        <circle cx="350" cy="25" r="1.5"/>
        <circle cx="375" cy="25" r="1.5"/>
        <circle cx="400" cy="25" r="1.5"/>
        <circle cx="425" cy="25" r="1.5"/>
        <circle cx="450" cy="25" r="1.5"/>
        <circle cx="475" cy="25" r="1.5"/>
      </g>

      <!-- Use the dot-row pattern for other rows -->
      <use href="#dot-row" y="25"/>
      <use href="#dot-row" y="50"/>
      <use href="#dot-row" y="75"/>
      <use href="#dot-row" y="100"/>
      <use href="#dot-row" y="125"/>
      <use href="#dot-row" y="150"/>
      <use href="#dot-row" y="175"/>
      <use href="#dot-row" y="200"/>
      <use href="#dot-row" y="225"/>
      <use href="#dot-row" y="250"/>
      <use href="#dot-row" y="275"/>
      <use href="#dot-row" y="300"/>
      <use href="#dot-row" y="325"/>
      <use href="#dot-row" y="350"/>
      <use href="#dot-row" y="375"/>
      <use href="#dot-row" y="400"/>
      <use href="#dot-row" y="425"/>
      <use href="#dot-row" y="450"/>
    </g>
  </g>

  <!-- Outer Circle -->
  <circle cx="250" cy="250" r="180" fill="none" stroke="{primary_color}" stroke-width="3" opacity="0.8"/>

  <!-- Circular grid lines -->
  <g fill="none" stroke="{primary_color}" stroke-width="1.5" opacity="0.6">
    <circle cx="250" cy="250" r="160"/>
    <circle cx="250" cy="250" r="140"/>
    <circle cx="250" cy="250" r="120"/>
  </g>

  <!-- Circular dotted pattern -->
  <circle cx="250" cy="250" r="170" fill="none" stroke="{text_color}" stroke-width="0.5" stroke-dasharray="2,4" opacity="0.8"/>

  <!-- Crosshair lines -->
  <g stroke="{primary_color}" stroke-width="1" opacity="0.7">
    <line x1="100" y1="250" x2="400" y2="250"/>
    <line x1="250" y1="100" x2="250" y2="400"/>
    <line x1="150" y1="150" x2="350" y2="350"/>
    <line x1="150" y1="350" x2="350" y2="150"/>
  </g>

  <!-- Outer triangle -->
  <path d="M250 100 L400 350 L100 350 Z" fill="none" stroke="{text_color}" stroke-width="5" opacity="0.9"/>

  <!-- Middle triangle -->
  <path d="M250 150 L350 325 L150 325 Z" fill="none" stroke="{text_color}" stroke-width="4" opacity="0.9"/>

  <!-- Inner triangle -->
  <path d="M250 200 L325 300 L175 300 Z" fill="none" stroke="{text_color}" stroke-width="3" opacity="0.9"/>

  <!-- Triangle inner grid lines -->
  <g stroke="{primary_color}" stroke-width="0.75" opacity="0.5">
    <!-- Outer triangle grid -->
    <line x1="250" y1="100" x2="175" y2="225"/>
    <line x1="250" y1="100" x2="325" y2="225"/>
    <line x1="100" y1="350" x2="225" y2="225"/>
    <line x1="400" y1="350" x2="275" y2="225"/>
    <line x1="225" y1="225" x2="275" y2="225"/>

    <!-- Inner triangle grids -->
    <line x1="250" y1="150" x2="200" y2="250"/>
    <line x1="250" y1="150" x2="300" y2="250"/>
    <line x1="150" y1="325" x2="200" y2="250"/>
    <line x1="350" y1="325" x2="300" y2="250"/>
    <line x1="200" y1="250" x2="300" y2="250"/>
  </g>

  <!-- Glow effects -->
  <g filter="url(#glow)">
    <!-- Triangle edge highlights -->
    <path d="M250 100 L400 350 L100 350 Z" fill="none" stroke="{text_color}" stroke-width="1.5" opacity="0.7"/>
    <path d="M250 150 L350 325 L150 325 Z" fill="none" stroke="{text_color}" stroke-width="1.5" opacity="0.7"/>
    <path d="M250 200 L325 300 L175 300 Z" fill="none" stroke="{text_color}" stroke-width="1.5" opacity="0.7"/>

    <!-- Center triangle point -->
    <circle cx="250" cy="85" r="3" fill="{accent_color}"/>
  </g>

  <!-- Text label in upper left -->
  <text x="40" y="50" fill="{primary_color}" font-family="monospace" font-size="16" font-weight="bold">SSH</text>

  <!-- Filters for glow effects -->
  <defs>
    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="5" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>
</svg>'''

    # Cyberpunk default colors (matching your paste-2.txt example)
    default_colors = {
        'bg_color': '#111122',  # Dark blue/black background
        'primary_color': '#00CCCC',  # Cyan primary elements
        'text_color': '#00FFFF',  # Brighter cyan text and highlights
        'accent_color': '#FFFFFF'  # White accent for special highlights
    }

    # Extract colors from theme if provided
    if theme_colors:
        if isinstance(theme_colors, dict):
            # Handle dictionary of colors
            bg_color = theme_colors.get('background', default_colors['bg_color'])
            primary_color = theme_colors.get('border', default_colors['primary_color'])
            text_color = theme_colors.get('text', default_colors['text_color'])
            accent_color = theme_colors.get('border', default_colors['accent_color'])
        else:
            # Handle ThemeColors object
            bg_color = getattr(theme_colors, 'background', default_colors['bg_color'])
            primary_color = getattr(theme_colors, 'border', default_colors['primary_color'])
            text_color = getattr(theme_colors, 'text', default_colors['text_color'])
            accent_color = getattr(theme_colors, 'border', default_colors['accent_color'])
    else:
        # Use cyberpunk default colors if no theme provided
        bg_color = default_colors['bg_color']
        primary_color = default_colors['border']
        text_color = default_colors['text_color']
        accent_color = default_colors['border']

    # Format the SVG with theme colors
    formatted_svg = svg_template.format(
        bg_color=bg_color,
        primary_color=primary_color,
        text_color=text_color,
        accent_color=accent_color
    )

    return formatted_svg
