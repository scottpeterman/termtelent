"""
Updated About Dialog for TerminalTelemetry
Reflects the true scope of the comprehensive network operations platform
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTabWidget, QWidget, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QPainter, QBrush, QColor
from PyQt6.QtSvg import QSvgRenderer
from pathlib import Path


class AboutDialog(QDialog):
    """Comprehensive About dialog showcasing TerminalTelemetry's full capabilities"""

    def __init__(self, parent=None, theme_manager=None, current_theme="cyberpunk"):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.current_theme = current_theme
        self.parent = parent
        self.setWindowTitle("About TerminalTelemetry Enterprise")
        self.setModal(True)
        self.setFixedSize(900, 700)

        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Setup the comprehensive about dialog UI"""
        layout = QVBoxLayout(self)

        # Header section
        header_layout = self._create_header_section()
        layout.addLayout(header_layout)

        # Tab widget for detailed information
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self._create_overview_tab()
        self._create_features_tab()
        self._create_technical_tab()
        self._create_integrations_tab()
        self._create_credits_tab()

        # Close button
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_layout.addWidget(close_button)
        layout.addLayout(close_layout)

    def _create_header_section(self):
        """Create the header with branded SVG logo and main title"""
        header_layout = QVBoxLayout()

        # Logo container using themed SVG
        logo_container = QWidget()
        logo_container.setFixedHeight(120)
        logo_layout = QVBoxLayout(logo_container)

        # Create themed SVG logo
        logo_label = QLabel()
        logo_label.setFixedSize(100, 100)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Get themed SVG content
        svg_content = self._get_themed_svg()

        try:
            # Create QPixmap from SVG
            renderer = QSvgRenderer()
            renderer.load(svg_content.encode())

            pixmap = QPixmap(100, 100)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()

            logo_label.setPixmap(pixmap)
        except Exception:
            # Fallback to text logo if SVG fails
            logo_label.setText("🔺\nTT")
            logo_label.setStyleSheet("font-size: 24px; font-weight: bold; text-align: center;")

        logo_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignCenter)

        header_layout.addWidget(logo_container)

        # Main title
        title_label = QLabel("TerminalTelemetry")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)

        # Subtitle
        subtitle_label = QLabel("Advanced Network Operations Platform")
        subtitle_font = QFont()
        subtitle_font.setPointSize(14)
        subtitle_font.setItalic(True)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle_label)

        # Version and description
        version_label = QLabel("Version 0.10.0 • Where Retro Aesthetics Meet Modern Network Operations")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(version_label)

        return header_layout

    def _get_themed_svg(self):
        from termtel.logo import get_themed_svg

        theme_colors = self.parent.theme_manager.get_colors(self.parent.theme)
        svg=get_themed_svg(theme_colors)
        return svg
    def _create_overview_tab(self):
        """Create overview tab with platform description"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Create scrollable area
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        overview_text = """
        <h2>Platform Overview</h2>
        
        <p><strong>TerminalTelemetry - <small>Enterprise</small></strong> is a comprehensive network operations platform that revolutionizes 
        how network engineers interact with infrastructure. What started as a cyber-inspired terminal emulator 
        has evolved into a complete ecosystem for network discovery, monitoring, and management.</p>
        
        <h3>Architecture</h3>
        <ul>
            <li><strong>Core Terminal Application</strong> - Advanced SSH client with embedded telemetry</li>
            <li><strong>Real-Time Telemetry System</strong> - Live device monitoring and metrics</li>
            <li><strong>Network Discovery Engine</strong> - Automated topology mapping and device inventory</li>
            <li><strong>RapidCMDB Platform</strong> - Enterprise-grade configuration management database</li>
            <li><strong>Advanced Theme System</strong> - 20+ retro-inspired themes with cyberpunk aesthetics</li>
        </ul>
        
        <h3>Philosophy</h3>
        <p>Combining the nostalgia of retro computing aesthetics with cutting-edge network automation 
        capabilities. TerminalTelemetry bridges the gap between traditional CLI-based network management 
        and modern GUI-driven workflows.</p>
        
        <h3>Target Users</h3>
        <ul>
            <li><strong>Network Engineers</strong> - Daily operations and troubleshooting</li>
            <li><strong>NOC Teams</strong> - Real-time monitoring and incident response</li>
            <li><strong>DevOps Teams</strong> - Infrastructure automation and CI/CD integration</li>
            <li><strong>Enterprise IT</strong> - Asset management and compliance reporting</li>
        </ul>
        """

        text_widget = QTextEdit()
        text_widget.setHtml(overview_text)
        text_widget.setReadOnly(True)
        scroll_layout.addWidget(text_widget)

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.tab_widget.addTab(tab, "Overview")

    def _create_features_tab(self):
        """Create features tab showcasing all capabilities"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        features_text = """
        <h2>Core Capabilities</h2>
        
        <h3>Advanced SSH Terminal</h3>
        <ul>
            <li><strong>Multi-Session Management</strong> - Tabbed interface with session persistence</li>
            <li><strong>Platform Detection</strong> - Automatic optimization for Cisco, Arista, Juniper, etc.</li>
            <li><strong>Session Import</strong> - NetBox and LogicMonitor integration</li>
            <li><strong>Credential Vault</strong> - AES-256 encrypted credential management</li>
            <li><strong>Quick Connect</strong> - Rapid device access with credential auto-fill</li>
        </ul>
        
        <h3>Real-Time Network Telemetry</h3>
        <ul>
            <li><strong>Live Device Monitoring</strong> - CPU, memory, interface utilization</li>
            <li><strong>Neighbor Discovery</strong> - CDP/LLDP topology mapping</li>
            <li><strong>ARP Table Monitoring</strong> - Real-time MAC address tracking</li>
            <li><strong>Route Table Analysis</strong> - Multi-VRF routing table visualization</li>
            <li><strong>System Log Streaming</strong> - Live log monitoring and alerting</li>
            <li><strong>CSV Export</strong> - All telemetry data exportable for analysis</li>
        </ul>
        
        <h3>Network Discovery & Mapping</h3>
        <ul>
            <li><strong>Automated Discovery</strong> - SNMP/SSH-based network scanning</li>
            <li><strong>Topology Visualization</strong> - Interactive network maps with multiple layouts</li>
            <li><strong>Device Classification</strong> - Intelligent vendor/model fingerprinting</li>
            <li><strong>Professional Diagrams</strong> - DrawIO and GraphML export for documentation</li>
            <li><strong>Map Enhancement Tools</strong> - Icon libraries and layout algorithms</li>
        </ul>
        
        <h3>Configuration Management</h3>
        <ul>
            <li><strong>Automated Collection</strong> - NAPALM-based configuration backup</li>
            <li><strong>Change Detection</strong> - Configuration versioning and diff visualization</li>
            <li><strong>Template Engine</strong> - 200+ TextFSM templates for data parsing</li>
            <li><strong>Bulk Operations</strong> - Mass device configuration and management</li>
        </ul>
        
        <h3>NAPALM Integration</h3>
        <ul>
            <li><strong>Multi-Vendor Support</strong> - Cisco, Arista, Juniper, HP, Fortinet unified API</li>
            <li><strong>Enhanced Connection Dialog</strong> - Session picker with credential integration</li>
            <li><strong>Comprehensive Operations</strong> - 50+ NAPALM getters organized by category</li>
            <li><strong>Real-Time Testing</strong> - Live connection validation and troubleshooting</li>
            <li><strong>JSON/Tree Visualization</strong> - Multiple output formats with syntax highlighting</li>
        </ul>
        
        <h3>Advanced Theme System</h3>
        <ul>
            <li><strong>20+ Built-in Themes</strong> - Cyberpunk, CRT, Doom, Borland, and more</li>
            <li><strong>Live Theme Switching</strong> - No restart required</li>
            <li><strong>Custom Theme Creation</strong> - JSON-based theme editor</li>
            <li><strong>Per-Component Theming</strong> - Individual terminal and widget themes</li>
            <li><strong>Cross-Platform Sync</strong> - Unified theming across desktop and web</li>
        </ul>
        """

        text_widget = QTextEdit()
        text_widget.setHtml(features_text)
        text_widget.setReadOnly(True)
        scroll_layout.addWidget(text_widget)

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.tab_widget.addTab(tab, "Features")

    def _create_technical_tab(self):
        """Create technical specifications tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        technical_text = """
        <h2>Technical Architecture</h2>
        
        <h3>Core Technology Stack</h3>
        <ul>
            <li><strong>Framework:</strong> PyQt6 for cross-platform native GUI</li>
            <li><strong>SSH Client:</strong> Paramiko and Netmiko for device connectivity</li>
            <li><strong>Web Platform:</strong> Flask with SQLite/PostgreSQL backend</li>
            <li><strong>Template Engine:</strong> TextFSM with 200+ pre-built templates</li>
            <li><strong>Visualization:</strong> Interactive topology with multiple layout engines</li>
            <li><strong>Security:</strong> Fernet encryption with PBKDF2 key derivation</li>
        </ul>
        
        <h3>Platform Support Matrix</h3>
        <table border="1" cellpadding="5" cellspacing="0">
            <tr><th>Platform</th><th>SSH</th><th>Telemetry</th><th>NAPALM</th><th>Discovery</th></tr>
            <tr><td>Cisco IOS/IOS-XE</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td></tr>
            <tr><td>Cisco NX-OS</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td></tr>
            <tr><td>Arista EOS</td><td>✅</td><td>✅</td><td>✅</td><td>✅</td></tr>
            <tr><td>Juniper JunOS</td><td>✅</td><td>⚠️</td><td>✅</td><td>✅</td></tr>
            <tr><td>HP ProCurve</td><td>✅</td><td>⚠️</td><td>✅</td><td>✅</td></tr>
            <tr><td>Fortinet FortiOS</td><td>✅</td><td>⚠️</td><td>✅</td><td>✅</td></tr>
            <tr><td>Palo Alto PAN-OS</td><td>✅</td><td>⚠️</td><td>✅</td><td>✅</td></tr>
        </table>
        <p><small>Full Support | Partial Support</small></p>
        
        <h3>Performance Specifications</h3>
        <ul>
            <li><strong>Concurrent Sessions:</strong> 50+ simultaneous SSH connections</li>
            <li><strong>Discovery Rate:</strong> ~100 devices per minute</li>
            <li><strong>Database Capacity:</strong> 20,000+ devices tested</li>
            <li><strong>Telemetry Refresh:</strong> Sub-second update intervals</li>
            <li><strong>Memory Usage:</strong> ~50MB base, scales with device count</li>
            <li><strong>Export Performance:</strong> <500ms for 1000+ row tables</li>
        </ul>
        
        <h3>Security Features</h3>
        <ul>
            <li><strong>Credential Encryption:</strong> AES-256 with PBKDF2 (480,000 iterations)</li>
            <li><strong>Platform Security:</strong> Machine-specific encryption keys</li>
            <li><strong>Network Security:</strong> SSH-only device access, no agents required</li>
            <li><strong>Data Protection:</strong> No plaintext credential storage</li>
            <li><strong>Access Control:</strong> Rate-limited authentication with lockout</li>
        </ul>
        
        <h3>Integration APIs</h3>
        <ul>
            <li><strong>NetBox:</strong> Bidirectional device sync and IPAM integration</li>
            <li><strong>LogicMonitor:</strong> Device import and monitoring data exchange</li>
            <li><strong>REST APIs:</strong> Programmatic access to all platform data</li>
            <li><strong>Export Formats:</strong> CSV, JSON, XML, DrawIO, GraphML</li>
            <li><strong>Webhook Support:</strong> Real-time event notifications</li>
        </ul>
        """

        text_widget = QTextEdit()
        text_widget.setHtml(technical_text)
        text_widget.setReadOnly(True)
        scroll_layout.addWidget(text_widget)

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.tab_widget.addTab(tab, "Technical")

    def _create_integrations_tab(self):
        """Create integrations and enterprise features tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        integrations_text = """
        <h2>Enterprise Integrations</h2>
        
        <h3>RapidCMDB Platform</h3>
        <ul>
            <li><strong>Web-Based CMDB:</strong> Comprehensive device inventory and management</li>
            <li><strong>Automated Discovery:</strong> Network-wide device scanning and classification</li>
            <li><strong>Configuration Management:</strong> Version control with automated change detection</li>
            <li><strong>Executive Dashboards:</strong> KPI tracking and trend analysis</li>
            <li><strong>Report Generation:</strong> Automated compliance and asset reports</li>
        </ul>
        
        <h3>NetBox Integration</h3>
        <ul>
            <li><strong>Device Synchronization:</strong> Bidirectional sync with NetBox IPAM/DCIM</li>
            <li><strong>Site Organization:</strong> Automatic site-based device grouping</li>
            <li><strong>IP Address Management:</strong> Sync IP assignments and subnet planning</li>
            <li><strong>Rack Management:</strong> Physical location tracking and visualization</li>
            <li><strong>Custom Fields:</strong> Support for NetBox custom attributes</li>
        </ul>
        
        <h3>LogicMonitor Integration</h3>
        <ul>
            <li><strong>Device Import:</strong> Bulk import of monitored devices</li>
            <li><strong>Monitoring Data:</strong> Performance baseline and threshold sync</li>
            <li><strong>Alert Correlation:</strong> Cross-reference configuration with alerts</li>
            <li><strong>Capacity Planning:</strong> Historical data analysis and trending</li>
        </ul>
        
        <h3>Network Mapping Suite</h3>
        <ul>
            <li><strong>Interactive Topology Viewer:</strong> Real-time network exploration</li>
            <li><strong>Professional Diagram Export:</strong> DrawIO and GraphML formats</li>
            <li><strong>Icon Management:</strong> Vendor-specific device representation</li>
            <li><strong>Map Enhancement:</strong> Automated layout and styling</li>
            <li><strong>Multi-Network Merging:</strong> Campus-wide topology consolidation</li>
        </ul>
        
        <h3>Development & Automation</h3>
        <ul>
            <li><strong>REST APIs:</strong> Full programmatic access to platform data</li>
            <li><strong>CLI Tools:</strong> Command-line utilities for automation</li>
            <li><strong>Python SDK:</strong> Native Python library for custom integrations</li>
            <li><strong>Webhook Integration:</strong> Real-time event notifications</li>
            <li><strong>CI/CD Support:</strong> Network change validation pipelines</li>
        </ul>
        
        <h3>Enterprise Deployment</h3>
        <ul>
            <li><strong>Scalable Architecture:</strong> Support for 20,000+ devices</li>
            <li><strong>High Availability:</strong> Redundant deployment options</li>
            <li><strong>Multi-Tenant:</strong> Isolated environments for MSPs</li>
            <li><strong>LDAP/AD Integration:</strong> Enterprise authentication</li>
            <li><strong>Audit Logging:</strong> Comprehensive access and change tracking</li>
        </ul>
        
        <h3>Modern Interfaces</h3>
        <ul>
            <li><strong>Desktop Application:</strong> Native PyQt6 interface</li>
            <li><strong>Web Interface:</strong> Browser-based access and management</li>
            <li><strong>Mobile Responsive:</strong> Touch-optimized for tablets and phones</li>
            <li><strong>API Dashboard:</strong> Real-time metrics and system status</li>
        </ul>
        """

        text_widget = QTextEdit()
        text_widget.setHtml(integrations_text)
        text_widget.setReadOnly(True)
        scroll_layout.addWidget(text_widget)

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.tab_widget.addTab(tab, "Enterprise")

    def _create_credits_tab(self):
        """Create credits and acknowledgments tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        credits_text = """
        <h2>Credits & Acknowledgments</h2>
        
        <h3>Core Development</h3>
        <ul>
            <li><strong>Lead Developer:</strong> Scott Peterman</li>
            <li><strong>Architecture:</strong> Modern PyQt6 application framework</li>
            <li><strong>Design Philosophy:</strong> Retro aesthetics with modern functionality</li>
        </ul>
        
        <h3>Technology Foundation</h3>
        <ul>
            <li><strong>PyQt6:</strong> Cross-platform GUI framework</li>
            <li><strong>Paramiko & Netmiko:</strong> SSH connectivity and device automation</li>
            <li><strong>NAPALM:</strong> Network Automation and Programmability Abstraction Layer</li>
            <li><strong>TextFSM:</strong> Template-based text parsing for network devices</li>
            <li><strong>Flask:</strong> Web application framework for RapidCMDB</li>
            <li><strong>SQLite/PostgreSQL:</strong> Database storage and management</li>
        </ul>
        
        <h3>Design & Themes</h3>
        <ul>
            <li><strong>Cyberpunk Aesthetics:</strong> Inspired by retro-futuristic computing</li>
            <li><strong>CRT Themes:</strong> Authentic vintage terminal experience</li>
            <li><strong>Color Palettes:</strong> Carefully curated for both style and usability</li>
            <li><strong>Typography:</strong> Monospace fonts optimized for terminal work</li>
        </ul>
        
        <h3>Community & Standards</h3>
        <ul>
            <li><strong>NTC Templates:</strong> Community-maintained TextFSM template library</li>
            <li><strong>Network Automation Community:</strong> Best practices and methodology</li>
            <li><strong>Open Source:</strong> Built on and contributing back to open source</li>
            <li><strong>RFC Standards:</strong> Adherence to networking protocol standards</li>
        </ul>
        
        <h3>Inspiration</h3>
        <ul>
            <li><strong>Classic Terminals:</strong> VT100, IBM 3270, and early computer aesthetics</li>
            <li><strong>Cyberpunk Culture:</strong> Neon-lit, high-tech, retro-futuristic design</li>
            <li><strong>Gaming History:</strong> Classic PC games like Doom and Quake</li>
            <li><strong>Developer Tools:</strong> Borland IDE, Norton Commander, and classic dev environments</li>
        </ul>
        
        <h3>Documentation & Resources</h3>
        <ul>
            <li><strong>User Guides:</strong> Comprehensive documentation for all features</li>
            <li><strong>API Reference:</strong> Complete REST API documentation</li>
            <li><strong>Video Tutorials:</strong> Step-by-step feature walkthroughs</li>
            <li><strong>Community Forums:</strong> User support and feature discussions</li>
        </ul>
        
        <h3>Special Thanks</h3>
        <ul>
            <li><strong>Network Engineers:</strong> Feedback and real-world testing</li>
            <li><strong>Beta Testers:</strong> Early adopters who helped shape the platform</li>
            <li><strong>Open Source Community:</strong> Libraries, tools, and inspiration</li>
            <li><strong>Users:</strong> Everyone who chose TerminalTelemetry for their daily work</li>
        </ul>
        
        <h3>Contact & Support</h3>
        <ul>
            <li><strong>GitHub:</strong> https://github.com/scottpeterman/terminaltelemetry</li>

        </ul>
        
        <hr>
        <p style="text-align: center; font-style: italic; margin-top: 20px;">
        <strong>"Where Retro Aesthetics Meet Modern Network Operations"</strong><br>
        TerminalTelemetry - Revolutionizing network engineering, one terminal at a time.
        </p>
        """

        text_widget = QTextEdit()
        text_widget.setHtml(credits_text)
        text_widget.setReadOnly(True)
        scroll_layout.addWidget(text_widget)

        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.tab_widget.addTab(tab, "Credits")

    def _apply_theme(self):
        """Apply the current theme to the dialog"""
        if self.theme_manager:
            self.theme_manager.apply_theme(self, self.current_theme)

            # Apply cyberpunk-specific styling if applicable
            if self.current_theme == "cyberpunk":
                self._apply_cyberpunk_styling()

    def _apply_cyberpunk_styling(self):
        """Apply cyberpunk-specific styling"""
        # Enhanced styling for cyberpunk theme
        tab_style = """
            QTabWidget::pane {
                border: 2px solid #00ffff;
                border-radius: 4px;
                background-color: #1a1a1a;
            }
            QTabBar::tab {
                background-color: #2a2a2a;
                border: 2px solid #00ffff;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 8px 16px;
                color: #00ffff;
                font-weight: bold;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1a1a1a;
                border-bottom: 2px solid #1a1a1a;
            }
            QTabBar::tab:hover {
                background-color: #00ffff;
                color: #000000;
            }
        """

        text_style = """
            QTextEdit {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 4px;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                padding: 10px;
            }
        """

        button_style = """
            QPushButton {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 10px 20px;
                color: #00ffff;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #00ffff;
                color: #000000;
            }
            QPushButton:pressed {
                background-color: #00ff88;
                border-color: #00ff88;
            }
        """

        self.tab_widget.setStyleSheet(tab_style)

        for text_edit in self.findChildren(QTextEdit):
            text_edit.setStyleSheet(text_style)

        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)


# Usage function to integrate with existing menu system
def show_about_dialog(parent, theme_manager=None, current_theme="cyberpunk"):
    """Show the updated about dialog"""
    dialog = AboutDialog(parent, theme_manager, current_theme)
    dialog.exec()