"""
Improved Widget-Integrated Template Editor
Fixed layout and proper theme integration using the cyberpunk theme system
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QTextEdit, QTableWidget, QTableWidgetItem,
                             QSplitter, QTabWidget, QWidget, QComboBox, QMessageBox,
                             QGroupBox, QScrollArea, QFrame, QCheckBox, QHeaderView)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat, QPixmap
import os
import tempfile
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

from termtel.termtelwidgets.textfsm_highlighter import TextFSMSyntaxHighlighter

@dataclass
class WidgetFieldRequirement:
    """Defines what fields a widget needs and how they're used"""
    field_name: str
    display_name: str
    required: bool
    description: str
    example_value: str
    widget_column: str = ""


@dataclass
class WidgetTemplate:
    """Template specification for a specific widget"""
    widget_name: str
    widget_display_name: str
    command_type: str
    required_fields: List[WidgetFieldRequirement]
    optional_fields: List[WidgetFieldRequirement]
    description: str


class WidgetTemplateRegistry:
    """Registry of widget template requirements"""

    @staticmethod
    # Add this to the WidgetTemplateRegistry.get_widget_templates() method in template_editor.py

    def get_widget_templates() -> Dict[str, WidgetTemplate]:
        return {
            'neighbor_widget': WidgetTemplate(
                widget_name='neighbor_widget',
                widget_display_name='CDP/LLDP Neighbors',
                command_type='cdp_neighbors',
                required_fields=[
                    WidgetFieldRequirement(
                        field_name='LOCAL_INTERFACE',
                        display_name='Local Interface',
                        required=True,
                        description='Interface on this device where neighbor is connected',
                        example_value='GigabitEthernet0/1',
                        widget_column='Local Interface'
                    ),
                    WidgetFieldRequirement(
                        field_name='NEIGHBOR_NAME',
                        display_name='Neighbor Device',
                        required=True,
                        description='Hostname or device ID of the neighbor',
                        example_value='SWITCH-01.company.com',
                        widget_column='Neighbor Device'
                    ),
                    WidgetFieldRequirement(
                        field_name='NEIGHBOR_INTERFACE',
                        display_name='Remote Interface',
                        required=True,
                        description='Interface on the neighbor device',
                        example_value='GigabitEthernet1/0/24',
                        widget_column='Remote Interface'
                    ),
                ],
                optional_fields=[
                    WidgetFieldRequirement(
                        field_name='MGMT_ADDRESS',
                        display_name='Management IP',
                        required=False,
                        description='Management IP address of neighbor',
                        example_value='192.168.1.100',
                        widget_column='IP Address'
                    ),
                    WidgetFieldRequirement(
                        field_name='PLATFORM',
                        display_name='Platform',
                        required=False,
                        description='Hardware platform of neighbor device',
                        example_value='cisco WS-C2960X-24TS-L',
                        widget_column='Platform'
                    ),
                ],
                description='Displays network neighbors discovered via CDP or LLDP protocols'
            ),
            'arp_widget': WidgetTemplate(
                widget_name='arp_widget',
                widget_display_name='ARP Table',
                command_type='arp_table',
                required_fields=[
                    WidgetFieldRequirement(
                        field_name='IP_ADDRESS',
                        display_name='IP Address',
                        required=True,
                        description='IP address in the ARP table',
                        example_value='192.168.1.50',
                        widget_column='IP Address'
                    ),
                    WidgetFieldRequirement(
                        field_name='MAC_ADDRESS',
                        display_name='MAC Address',
                        required=True,
                        description='Hardware MAC address',
                        example_value='00:1a:2b:3c:4d:5e',
                        widget_column='MAC Address'
                    ),
                    WidgetFieldRequirement(
                        field_name='INTERFACE',
                        display_name='Interface',
                        required=True,
                        description='Interface where this ARP entry was learned',
                        example_value='Vlan100',
                        widget_column='Interface'
                    ),
                ],
                optional_fields=[
                    WidgetFieldRequirement(
                        field_name='AGE',
                        display_name='Age',
                        required=False,
                        description='Age of the ARP entry in minutes',
                        example_value='15',
                        widget_column='Age'
                    ),
                ],
                description='Displays the device ARP table showing IP to MAC address mappings'
            ),
            # ADD THIS NEW ENTRY:
            'route_widget': WidgetTemplate(
                widget_name='route_widget',
                widget_display_name='Route Table',
                command_type='route_table',
                required_fields=[
                    WidgetFieldRequirement(
                        field_name='NETWORK',
                        display_name='Network',
                        required=True,
                        description='Destination network/subnet',
                        example_value='192.168.1.0/24',
                        widget_column='Network'
                    ),
                    WidgetFieldRequirement(
                        field_name='NEXT_HOP',
                        display_name='Next Hop',
                        required=True,
                        description='Next hop IP address or interface',
                        example_value='10.0.0.1',
                        widget_column='Next Hop'
                    ),
                    WidgetFieldRequirement(
                        field_name='PROTOCOL',
                        display_name='Protocol',
                        required=True,
                        description='Routing protocol that learned this route',
                        example_value='OSPF',
                        widget_column='Protocol'
                    ),
                ],
                optional_fields=[
                    WidgetFieldRequirement(
                        field_name='MASK',
                        display_name='Subnet Mask',
                        required=False,
                        description='Subnet mask for the network',
                        example_value='255.255.255.0',
                        widget_column='Mask'
                    ),
                    WidgetFieldRequirement(
                        field_name='INTERFACE',
                        display_name='Interface',
                        required=False,
                        description='Outgoing interface for this route',
                        example_value='GigabitEthernet0/1',
                        widget_column='Interface'
                    ),
                    WidgetFieldRequirement(
                        field_name='METRIC',
                        display_name='Metric',
                        required=False,
                        description='Route metric/cost',
                        example_value='110',
                        widget_column='Metric'
                    ),
                    WidgetFieldRequirement(
                        field_name='ADMIN_DISTANCE',
                        display_name='Admin Distance',
                        required=False,
                        description='Administrative distance',
                        example_value='90',
                        widget_column='Admin Dist'
                    ),
                    WidgetFieldRequirement(
                        field_name='AGE',
                        display_name='Age',
                        required=False,
                        description='Age of the route entry',
                        example_value='2w1d',
                        widget_column='Age'
                    ),
                    WidgetFieldRequirement(
                        field_name='VRF',
                        display_name='VRF',
                        required=False,
                        description='Virtual Routing and Forwarding instance',
                        example_value='MGMT-VRF',
                        widget_column='VRF'
                    ),
                ],
                description='Displays the device routing table with next hops and metrics'
            ),
        }

class ImprovedFieldRequirementsWidget(QWidget):
    """Improved field requirements display with better spacing and layout"""

    def __init__(self, widget_template: WidgetTemplate, parent=None):
        super().__init__(parent)
        self.widget_template = widget_template
        self._setup_ui()

    def _setup_ui(self):
        """Setup the field requirements display with improved layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Widget header with better styling
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 12, 12, 12)

        # Title with icon
        title = QLabel(f" {self.widget_template.widget_display_name}")
        title.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                font-size: 16px; 
                color: #00ffff; 
                padding: 5px;
                border-bottom: 2px solid #00ffff;
            }
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title)

        # Description with better formatting
        desc = QLabel(self.widget_template.description)
        desc.setWordWrap(True)
        desc.setStyleSheet("""
            QLabel {
                color: #cccccc; 
                font-size: 12px;
                padding: 8px;
                line-height: 1.4;
                background-color: rgba(0, 255, 255, 0.1);
                border-radius: 4px;
            }
        """)
        header_layout.addWidget(desc)
        layout.addWidget(header_frame)

        # Required fields section with improved styling
        if self.widget_template.required_fields:
            required_group = self._create_improved_field_group(
                " Required Fields",
                self.widget_template.required_fields,
                "#ff6b6b",
                "#2a0f0f"
            )
            layout.addWidget(required_group)

        # Optional fields section with improved styling
        if self.widget_template.optional_fields:
            optional_group = self._create_improved_field_group(
                " Optional Fields",
                self.widget_template.optional_fields,
                "#4ecdc4",
                "#0f2a2a"
            )
            layout.addWidget(optional_group)

        layout.addStretch()

    def _create_improved_field_group(self, title: str, fields: List[WidgetFieldRequirement],
                                   color: str, bg_color: str) -> QGroupBox:
        """Create an improved field group with better styling"""
        group = QGroupBox(title)
        group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                font-size: 14px;
                color: {color};
                border: 2px solid {color};
                border-radius: 8px;
                margin-top: 15px;
                padding-top: 15px;
                background-color: {bg_color};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                background-color: #1a1a1a;
            }}
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 20, 12, 12)

        if not fields:
            no_fields = QLabel("None defined")
            no_fields.setStyleSheet("color: #888888; font-style: italic; padding: 10px;")
            layout.addWidget(no_fields)
            return group

        # Create improved table for fields
        table = QTableWidget(len(fields), 4)
        table.setHorizontalHeaderLabels(["Field Name", "Widget Column", "Example", "Description"])
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Improve table styling
        table.setStyleSheet("""
            QTableWidget {
                gridline-color: rgba(0, 255, 255, 0.3);
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 4px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(0, 255, 255, 0.1);
            }
            QTableWidget::item:selected {
                background-color: rgba(0, 255, 255, 0.2);
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #00ffff;
                padding: 8px;
                border: 1px solid #333333;
                font-weight: bold;
            }
        """)

        for row, field in enumerate(fields):
            # Field name (code style)
            field_item = QTableWidgetItem(field.field_name)
            field_item.setFont(QFont("Consolas", 10))
            field_item.setForeground(QColor("#ffd93d"))
            table.setItem(row, 0, field_item)

            # Widget column
            column_item = QTableWidgetItem(field.widget_column)
            column_item.setForeground(QColor("#6bcf7f"))
            column_item.setFont(QFont("Arial", 10))
            table.setItem(row, 1, column_item)

            # Example (with ellipsis for long values)
            example_text = field.example_value
            if len(example_text) > 25:
                example_text = example_text[:22] + "..."
            example_item = QTableWidgetItem(example_text)
            example_item.setFont(QFont("Consolas", 9))
            example_item.setForeground(QColor("#a8e6cf"))
            example_item.setToolTip(f"Full example: {field.example_value}")
            table.setItem(row, 2, example_item)

            # Description (truncated with tooltip)
            desc_text = field.description
            if len(desc_text) > 30:
                desc_text = desc_text[:27] + "..."
            desc_item = QTableWidgetItem(desc_text)
            desc_item.setForeground(QColor("#cccccc"))
            desc_item.setToolTip(field.description)
            table.setItem(row, 3, desc_item)

        # Auto-resize columns
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        # Set reasonable table height
        table.setMinimumHeight(200)
        table.setMaximumHeight(300)

        layout.addWidget(table)
        return group


class WidgetTemplateEditor(QDialog):
    """Improved template editor with proper theme integration and better layout"""

    template_saved = pyqtSignal(str, str, str)

    def __init__(self, widget_type: str, controller, theme_library=None, parent=None):
        super().__init__(parent)
        self.widget_type = widget_type
        self.controller = controller
        self.theme_library = theme_library
        self.parent_widget = parent

        # Get widget template spec
        self.widget_templates = WidgetTemplateRegistry.get_widget_templates()
        self.widget_template = self.widget_templates.get(widget_type)

        if not self.widget_template:
            raise ValueError(f"Unknown widget type: {widget_type}")

        self.current_platform = "cisco_ios"
        self.current_template_content = ""
        self.has_unsaved_changes = False

        self._setup_ui()
        self._load_initial_template()
        self._apply_theme_properly()

    def _apply_theme_properly(self):
        """Apply theme using the parent's theme system"""
        if not self.theme_library:
            return

        try:
            # Get current theme from parent
            current_theme = "cyberpunk"  # fallback

            if hasattr(self.parent_widget, 'current_theme'):
                current_theme = self.parent_widget.current_theme
            elif hasattr(self.parent_widget, 'theme'):
                current_theme = self.parent_widget.theme
            elif hasattr(self.controller, 'current_theme'):
                current_theme = self.controller.current_theme

            print(f" Applying theme '{current_theme}' to template editor")

            # Apply theme using the theme library
            self.theme_library.apply_theme(self, current_theme)

            # Apply custom cyberpunk styling for specific elements
            self._apply_cyberpunk_enhancements()

        except Exception as e:
            print(f" Error applying theme: {e}")

    def _apply_cyberpunk_enhancements(self):
        """Apply additional cyberpunk styling enhancements"""
        # Enhanced dialog styling
        self.setStyleSheet(self.styleSheet() + """
            QDialog {
                background-color: #0a0a0a;
                border: 2px solid #00ffff;
                border-radius: 8px;
            }
            
            QSplitter::handle {
                background-color: #00ffff;
                border: 1px solid #00ffff;
                border-radius: 2px;
                margin: 2px;
            }
            
            QSplitter::handle:horizontal {
                width: 4px;
            }
            
            QSplitter::handle:vertical {
                height: 4px;
            }
            
            QTabWidget::pane {
                border: 2px solid #00ffff;
                border-radius: 4px;
                background-color: #1a1a1a;
            }
            
            QTabBar::tab {
                background-color: #2a2a2a;
                color: #00ffff;
                padding: 8px 16px;
                margin-right: 2px;
                border: 2px solid #00ffff;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            
            QTabBar::tab:selected {
                background-color: #00ffff;
                color: #000000;
                font-weight: bold;
            }
            
            QTabBar::tab:hover:!selected {
                background-color: #003333;
            }
        """)

        # Style specific elements
        if hasattr(self, 'template_editor'):
            self.template_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #0f0f0f;
                    border: 2px solid #00ffff;
                    border-radius: 4px;
                    color: #ffffff;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 11px;
                    line-height: 1.4;
                    padding: 8px;
                }
                QTextEdit:focus {
                    border-color: #00ff88;
                    background-color: #111111;
                }
            """)

        if hasattr(self, 'sample_data_editor'):
            self.sample_data_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #0f0f0f;
                    border: 2px solid #444444;
                    border-radius: 4px;
                    color: #cccccc;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 10px;
                    padding: 8px;
                }
            """)

    def _setup_ui(self):
        """Setup the improved template editor UI with proper sizing and window controls"""
        self.setWindowTitle(f"Template Editor - {self.widget_template.widget_display_name}")

        # Enable window controls (minimize, maximize, restore)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowSystemMenuHint
        )

        # Make it non-modal so user can interact with other windows
        self.setModal(False)

        # Get screen information
        if self.parent_widget:
            screen = self.parent_widget.screen()
        else:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()

        if screen:
            screen_rect = screen.availableGeometry()
            # Use exactly 90% of screen size as requested
            width = int(screen_rect.width() * 0.90)
            height = int(screen_rect.height() * 0.90)

            self.resize(width, height)

            # Center on screen to ensure it's fully visible
            x = screen_rect.x() + (screen_rect.width() - width) // 2
            y = screen_rect.y() + (screen_rect.height() - height) // 2

            # Ensure the dialog is not positioned off-screen
            x = max(screen_rect.x(), min(x, screen_rect.x() + screen_rect.width() - width))
            y = max(screen_rect.y(), min(y, screen_rect.y() + screen_rect.height() - height))

            self.move(x, y)
        else:
            # Fallback for when screen detection fails
            self.resize(1400, 1000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)  # Reduced margins
        layout.setSpacing(8)  # Reduced spacing

        # Improved header
        header_layout = self._create_improved_header()
        layout.addLayout(header_layout)

        # Main content with better proportions
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # Left panel - Field requirements (fixed width)
        requirements_panel = self._create_improved_requirements_panel()
        requirements_panel.setMinimumWidth(350)  # Reduced from 400
        requirements_panel.setMaximumWidth(400)  # Reduced from 450
        main_splitter.addWidget(requirements_panel)

        # Center panel - Template editor (flexible)
        editor_panel = self._create_improved_editor_panel()
        main_splitter.addWidget(editor_panel)

        # Right panel - Test and preview (flexible)
        test_panel = self._create_improved_test_panel()
        main_splitter.addWidget(test_panel)

        # Better initial proportions - adjusted for smaller dialog
        main_splitter.setSizes([375, 500, 500])  # More balanced
        layout.addWidget(main_splitter)

        # Improved bottom buttons
        button_layout = self._create_improved_button_layout()
        layout.addLayout(button_layout)
    def _create_improved_header(self):
        """Create improved header with better styling"""
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 2px solid #00ffff;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(15, 10, 15, 10)

        # Widget info with icon
        widget_label = QLabel(f" Template Editor: {self.widget_template.widget_display_name}")
        widget_label.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                font-size: 18px; 
                color: #00ffff;
                padding: 5px;
            }
        """)
        header_layout.addWidget(widget_label)

        header_layout.addStretch()

        # Platform selection with better styling
        platform_label = QLabel("Platform:")
        platform_label.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 14px;")
        header_layout.addWidget(platform_label)

        self.platform_combo = QComboBox()
        self.platform_combo.addItems([
            "cisco_ios", "cisco_nxos", "arista_eos",
            "aruba_aos", "juniper_junos", "linux"
        ])
        self.platform_combo.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                border: 2px solid #00ffff;
                border-radius: 4px;
                padding: 6px 12px;
                color: #ffffff;
                font-size: 12px;
                min-width: 120px;
            }
            QComboBox:hover {
                border-color: #00ff88;
            }
            QComboBox::drop-down {
                border: none;
                background: #00ffff;
                width: 20px;
                border-radius: 0 4px 4px 0;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                border: 2px solid #00ffff;
                selection-background-color: #00ffff;
                selection-color: #000000;
                color: #ffffff;
            }
        """)
        self.platform_combo.currentTextChanged.connect(self._on_platform_changed)
        header_layout.addWidget(self.platform_combo)

        # Template status
        self.template_status = QLabel(" Template: Loading...")
        self.template_status.setStyleSheet("""
            QLabel {
                color: #888888; 
                font-size: 12px;
                margin-left: 20px;
                padding: 4px 8px;
                background-color: #2a2a2a;
                border-radius: 4px;
            }
        """)
        header_layout.addWidget(self.template_status)

        layout = QVBoxLayout()
        layout.addWidget(header_frame)
        return layout

    def _create_improved_requirements_panel(self):
        """Create improved requirements panel"""
        # Use improved requirements widget
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: 2px solid #333333;
                border-radius: 4px;
                background-color: #1a1a1a;
            }
        """)

        requirements_widget = ImprovedFieldRequirementsWidget(self.widget_template)
        scroll.setWidget(requirements_widget)

        return scroll

    def _create_improved_editor_panel(self):
        """Create improved template editor panel"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        panel.setStyleSheet("""
            QFrame {
                border: 2px solid #333333;
                border-radius: 4px;
                background-color: #1a1a1a;
            }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

        # Editor header with better styling
        editor_header = QHBoxLayout()

        title = QLabel(" Template Editor")
        title.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                font-size: 16px; 
                color: #ffd93d;
                padding: 5px;
            }
        """)
        editor_header.addWidget(title)

        editor_header.addStretch()

        # Improved load from device button
        load_from_device_btn = QPushButton(" Load from Device")
        load_from_device_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #ffd93d;
                border-radius: 4px;
                padding: 8px 16px;
                color: #ffd93d;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ffd93d;
                color: #000000;
            }
        """)
        load_from_device_btn.clicked.connect(self._load_sample_from_device)
        load_from_device_btn.setToolTip("Load sample output from connected device")
        editor_header.addWidget(load_from_device_btn)

        layout.addLayout(editor_header)

        # Template editor with improved styling
        self.template_editor = QTextEdit()
        self.template_editor.setFont(QFont("Consolas", 11))
        self.template_editor.textChanged.connect(self._on_template_changed_save_only)
        self.template_editor.setPlaceholderText(
            "TextFSM template will be loaded here...\n\n"
            "Template should define Value fields that match the required fields shown on the left.\n\n"
            "Click 'Run Test' button to test your template against sample data."
        )

        # Add syntax highlighting
        try:
            self.highlighter = TextFSMSyntaxHighlighter(self.template_editor.document())
        except Exception as e:
            print(f"Syntax highlighting not available: {e}")

        layout.addWidget(self.template_editor)

        # Template validation status with better styling
        self.validation_status = QLabel(" Validation: Click 'Run Test' to validate")
        self.validation_status.setStyleSheet("""
            QLabel {
                font-size: 11px; 
                color: #888888; 
                padding: 8px;
                background-color: #2a2a2a;
                border-radius: 4px;
                border: 1px solid #333333;
            }
        """)
        layout.addWidget(self.validation_status)

        return panel

    def _create_improved_test_panel(self):
        """Create improved test panel"""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        panel.setStyleSheet("""
            QFrame {
                border: 2px solid #333333;
                border-radius: 4px;
                background-color: #1a1a1a;
            }
        """)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)

        # Test header with prominent test button
        test_header = QHBoxLayout()

        title = QLabel(" Test & Preview")
        title.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                font-size: 16px; 
                color: #4ecdc4;
                padding: 5px;
            }
        """)
        test_header.addWidget(title)

        test_header.addStretch()

        # Prominent test button
        test_btn = QPushButton(" RUN TEST")
        test_btn.clicked.connect(self._run_template_test)
        test_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 14px 24px;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 16px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #45a049;
                transform: scale(1.05);
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        test_header.addWidget(test_btn)

        layout.addLayout(test_header)

        # Test tabs with better styling
        test_tabs = QTabWidget()
        test_tabs.setStyleSheet("""
            QTabWidget::tab-bar {
                alignment: center;
            }
        """)

        # Sample data tab
        sample_tab = self._create_improved_sample_data_tab()
        test_tabs.addTab(sample_tab, " Sample Data")

        # Widget preview tab
        preview_tab = self._create_improved_widget_preview_tab()
        test_tabs.addTab(preview_tab, " Widget Preview")

        layout.addWidget(test_tabs)

        return panel

    def _create_improved_sample_data_tab(self):
        """Create improved sample data input tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        # Sample data editor with better styling
        self.sample_data_editor = QTextEdit()
        self.sample_data_editor.setFont(QFont("Consolas", 10))
        self.sample_data_editor.setPlaceholderText(
            "Paste sample command output here...\n\n"
            "This should be the raw output from the device command that this template will parse.\n\n"
            "Click 'RUN TEST' button to test template against this data."
        )
        layout.addWidget(self.sample_data_editor)

        # Load controls with better styling
        load_layout = QHBoxLayout()

        load_file_btn = QPushButton(" Load from File")
        load_file_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #4ecdc4;
                border-radius: 4px;
                padding: 8px 16px;
                color: #4ecdc4;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4ecdc4;
                color: #000000;
            }
        """)
        load_file_btn.clicked.connect(self._load_sample_from_file)
        load_layout.addWidget(load_file_btn)

        clear_btn = QPushButton(" Clear")
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #ff6b6b;
                border-radius: 4px;
                padding: 8px 16px;
                color: #ff6b6b;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
                color: #000000;
            }
        """)
        clear_btn.clicked.connect(self.sample_data_editor.clear)
        load_layout.addWidget(clear_btn)

        load_layout.addStretch()
        layout.addLayout(load_layout)

        return tab

    def _create_improved_widget_preview_tab(self):
        """Create improved widget preview tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        # Preview header
        preview_header = QLabel(" Widget Preview - How data will appear in the actual widget")
        preview_header.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                color: #ff6b6b; 
                font-size: 14px;
                margin-bottom: 10px;
                padding: 8px;
                background-color: rgba(255, 107, 107, 0.1);
                border-radius: 4px;
            }
        """)
        layout.addWidget(preview_header)

        # Field mapping status
        self.field_mapping_status = QLabel("Field Mapping: Click 'RUN TEST' to check mapping")
        self.field_mapping_status.setStyleSheet("""
            QLabel {
                font-size: 12px; 
                color: #888888; 
                margin-bottom: 10px;
                padding: 6px;
                background-color: #2a2a2a;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.field_mapping_status)

        # Widget preview table
        self.widget_preview_table = QTableWidget(0, 0)
        self.widget_preview_table.setAlternatingRowColors(True)
        self.widget_preview_table.setStyleSheet("""
            QTableWidget {
                gridline-color: rgba(0, 255, 255, 0.3);
                background-color: #0f0f0f;
                border: 2px solid #333333;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #00ffff;
                padding: 8px;
                border: 1px solid #333333;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.widget_preview_table)

        # Field coverage report
        coverage_label = QLabel(" Field Coverage Report:")
        coverage_label.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                font-size: 12px; 
                margin-top: 10px;
                color: #ffd93d;
            }
        """)
        layout.addWidget(coverage_label)

        self.field_coverage_display = QTextEdit()
        self.field_coverage_display.setMaximumHeight(120)
        self.field_coverage_display.setReadOnly(True)
        self.field_coverage_display.setFont(QFont("Consolas", 10))
        self.field_coverage_display.setStyleSheet("""
            QTextEdit {
                background-color: #0f0f0f;
                border: 2px solid #333333;
                border-radius: 4px;
                color: #cccccc;
                padding: 8px;
            }
        """)
        layout.addWidget(self.field_coverage_display)

        return tab

    def _create_improved_button_layout(self):
        """Create improved bottom button layout"""
        button_frame = QFrame()
        button_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        button_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 2px solid #333333;
                border-radius: 6px;
                padding: 8px;
            }
        """)

        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(15, 8, 15, 8)

        # Validation button
        validate_btn = QPushButton(" Check Syntax")
        validate_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #ffd93d;
                border-radius: 4px;
                padding: 10px 18px;
                color: #ffd93d;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ffd93d;
                color: #000000;
            }
        """)
        validate_btn.clicked.connect(self._validate_template_syntax_only)
        validate_btn.setToolTip("Check template syntax without running test")
        button_layout.addWidget(validate_btn)

        # Save button
        self.save_btn = QPushButton(" Save Template")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #4CAF50;
                border-radius: 4px;
                padding: 10px 18px;
                color: #4CAF50;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4CAF50;
                color: #000000;
            }
            QPushButton:disabled {
                background-color: #1a1a1a;
                border-color: #444444;
                color: #666666;
            }
        """)
        self.save_btn.clicked.connect(self._save_template)
        self.save_btn.setEnabled(False)
        button_layout.addWidget(self.save_btn)

        button_layout.addStretch()

        # Reset button
        reset_btn = QPushButton(" Reset")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #ff9500;
                border-radius: 4px;
                padding: 10px 18px;
                color: #ff9500;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ff9500;
                color: #000000;
            }
        """)
        reset_btn.clicked.connect(self._reset_template)
        button_layout.addWidget(reset_btn)

        # Cancel button
        cancel_btn = QPushButton(" Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #ff6b6b;
                border-radius: 4px;
                padding: 10px 18px;
                color: #ff6b6b;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ff6b6b;
                color: #000000;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        # Close button
        close_btn = QPushButton(" Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 2px solid #00ffff;
                border-radius: 4px;
                padding: 10px 18px;
                color: #00ffff;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #00ffff;
                color: #000000;
            }
        """)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout = QVBoxLayout()
        layout.addWidget(button_frame)
        return layout

    # ... include all the existing functionality methods unchanged ...
    def _load_initial_template(self):
        """Load the initial template for the current platform"""
        self._load_template_for_platform(self.current_platform)

    def _load_template_for_platform(self, platform: str):
        """Load template file for specific platform"""
        command_map = {
            'cdp_neighbors': 'show_cdp_neighbors_detail',
            'arp_table': 'show_ip_arp',
            'route_table': 'show_ip_route',
            'system_info': 'show_version'
        }

        command_name = command_map.get(self.widget_template.command_type, self.widget_template.command_type)
        template_filename = f"{platform}_{command_name}.textfsm"
        template_path = os.path.join("templates/textfsm", template_filename)

        self.template_status.setText(f" Template: {template_filename}")

        try:
            if os.path.exists(template_path):
                with open(template_path, 'r') as f:
                    content = f.read()

                self.template_editor.setPlainText(content)
                self.current_template_content = content
                self.has_unsaved_changes = False
                self.save_btn.setEnabled(False)

                self.template_status.setStyleSheet("color: #00ff00;")
                self.template_status.setText(f" Template: {template_filename} (Loaded)")

                self.validation_status.setText(" Validation: Template loaded - click 'RUN TEST' to validate")
                self.validation_status.setStyleSheet("color: #888888;")

            else:
                basic_template = self._create_basic_template()
                self.template_editor.setPlainText(basic_template)
                self.current_template_content = ""
                self.has_unsaved_changes = True
                self.save_btn.setEnabled(True)

                self.template_status.setStyleSheet("color: #ff6600;")
                self.template_status.setText(f" Template: {template_filename} (New)")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load template: {str(e)}")

    def _create_basic_template(self) -> str:
        """Create a basic template with required fields"""
        lines = ["# TextFSM Template for " + self.widget_template.widget_display_name]
        lines.append("# Auto-generated basic template - customize as needed")
        lines.append("")

        for field in self.widget_template.required_fields:
            lines.append(f"Value {field.field_name} (\\S+)")

        for field in self.widget_template.optional_fields:
            lines.append(f"Value {field.field_name} (\\S+)")

        lines.append("")
        lines.append("Start")
        lines.append("  # Add parsing rules here")
        lines.append("  ^.*$$ -> Continue")
        lines.append("")
        lines.append("EOF")

        return '\n'.join(lines)

    def _on_platform_changed(self, platform: str):
        """Handle platform selection change"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Load template for new platform anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                self.platform_combo.setCurrentText(self.current_platform)
                return

        self.current_platform = platform
        self._load_template_for_platform(platform)

    def _on_template_changed_save_only(self):
        """Handle template content changes"""
        current_content = self.template_editor.toPlainText()
        self.has_unsaved_changes = (current_content != self.current_template_content)
        self.save_btn.setEnabled(self.has_unsaved_changes)

        self.validation_status.setText(" Validation: Content changed - click 'RUN TEST' to validate")
        self.validation_status.setStyleSheet("color: #888888;")

    def _validate_template_syntax_only(self):
        """Validate template syntax only"""
        template_content = self.template_editor.toPlainText()

        if not template_content.strip():
            self.validation_status.setText(" Validation: No template content")
            self.validation_status.setStyleSheet("color: #888888;")
            return False

        try:
            import textfsm
            from io import StringIO

            template_file = StringIO(template_content)
            template = textfsm.TextFSM(template_file)

            template_fields = set(template.header)
            required_fields = {field.field_name for field in self.widget_template.required_fields}
            missing_required = required_fields - template_fields

            optional_fields = {field.field_name for field in self.widget_template.optional_fields}
            covered_optional = optional_fields.intersection(template_fields)

            if missing_required:
                self.validation_status.setText(f" Syntax OK, but missing required fields: {', '.join(missing_required)}")
                self.validation_status.setStyleSheet("color: #ff6600;")
                return False
            else:
                coverage_pct = (len(covered_optional) / len(optional_fields) * 100) if optional_fields else 100
                self.validation_status.setText(f" Syntax valid! Optional coverage: {coverage_pct:.0f}%")
                self.validation_status.setStyleSheet("color: #00ff00;")
                return True

        except Exception as e:
            self.validation_status.setText(f" Syntax error: {str(e)}")
            self.validation_status.setStyleSheet("color: #ff4444;")
            return False

    def _load_sample_from_device(self):
        """Load sample data from connected device"""
        if not hasattr(self.controller, 'is_connected') or not self.controller.is_connected:
            QMessageBox.warning(self, "No Connection", "Please connect to a device first")
            return

        try:
            command_type = self.widget_template.command_type
            success, output, _ = self.controller.execute_command_and_parse(command_type)

            if success:
                self.sample_data_editor.setPlainText(output)
                QMessageBox.information(self, "Success", "Sample data loaded from device")
                QMessageBox.information(self, "Data Loaded",
                                      "Sample data loaded successfully.\nClick 'RUN TEST' button to test your template.")
            else:
                QMessageBox.warning(self, "Error", "Failed to get sample data from device")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading from device: {str(e)}")

    def _load_sample_from_file(self):
        """Load sample data from file"""
        from PyQt6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Sample Data", "", "Text Files (*.txt);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                self.sample_data_editor.setPlainText(content)
                QMessageBox.information(self, "Data Loaded",
                                      "Sample data loaded from file.\nClick 'RUN TEST' button to test your template.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file: {str(e)}")

    def _run_template_test(self):
        """Test template against sample data"""
        template_content = self.template_editor.toPlainText()
        sample_data = self.sample_data_editor.toPlainText()

        if not template_content.strip():
            self.field_mapping_status.setText(" Status: No template to test")
            self.field_mapping_status.setStyleSheet("color: #ff6600; font-weight: bold;")
            return

        if not sample_data.strip():
            self.field_mapping_status.setText(" Status: No sample data to test against")
            self.field_mapping_status.setStyleSheet("color: #ff6600; font-weight: bold;")
            return

        try:
            import textfsm
            from io import StringIO

            template_file = StringIO(template_content)
            template = textfsm.TextFSM(template_file)

            parsed_rows = template.ParseText(sample_data)
            headers = template.header

            self.field_mapping_status.setText(f"Field Mapping:  Test passed - {len(parsed_rows)} entries")
            self.field_mapping_status.setStyleSheet("color: #00ff00;")

            self.validation_status.setText(f" Validation:  Template tested successfully")
            self.validation_status.setStyleSheet("color: #00ff00;")

            self._update_widget_preview(parsed_rows, headers)
            self._update_field_coverage(headers)

        except Exception as e:
            self.field_mapping_status.setText("Field Mapping:  Test failed")
            self.field_mapping_status.setStyleSheet("color: #ff4444;")

            self.validation_status.setText(f" Validation:  Template test failed")
            self.validation_status.setStyleSheet("color: #ff4444;")

            self.field_coverage_display.setPlainText(f"Template test error:\n{str(e)}")
            self.widget_preview_table.setRowCount(0)
            self.widget_preview_table.setColumnCount(0)

    def _update_widget_preview(self, parsed_rows: list, headers: list):
        """Update widget preview to show how data will appear in actual widget"""
        if not parsed_rows:
            return

        # DEBUG: Show what protocols we're getting from the template
        if self.widget_type == 'route_widget':
            print(f"\n TEMPLATE EDITOR PREVIEW DEBUG")
            print(f"Widget type: {self.widget_type}")
            print(f"Headers found: {headers}")

            # Show sample of protocols
            protocol_samples = set()
            for row in parsed_rows[:5]:  # First 5 rows
                row_dict = dict(zip(headers, row))
                if 'PROTOCOL' in row_dict:
                    protocol_samples.add(row_dict['PROTOCOL'])
            print(f"Sample protocols from template: {sorted(protocol_samples)}")

        widget_columns = []
        field_mapping = {}

        for field in self.widget_template.required_fields + self.widget_template.optional_fields:
            if field.widget_column and field.field_name in headers:
                widget_columns.append(field.widget_column)
                field_mapping[field.widget_column] = field.field_name

        if not widget_columns:
            self.widget_preview_table.setRowCount(0)
            self.widget_preview_table.setColumnCount(0)
            self.field_mapping_status.setText("Field Mapping:  No fields mapped to widget columns")
            self.field_mapping_status.setStyleSheet("color: #ff4444;")
            return

        self.widget_preview_table.setRowCount(len(parsed_rows))
        self.widget_preview_table.setColumnCount(len(widget_columns))
        self.widget_preview_table.setHorizontalHeaderLabels(widget_columns)

        for row, data_row in enumerate(parsed_rows):
            data_dict = dict(zip(headers, data_row))

            for col, widget_column in enumerate(widget_columns):
                field_name = field_mapping[widget_column]
                value = data_dict.get(field_name, "")

                # Apply widget-specific normalization
                if self.widget_type == 'route_widget' and widget_column == 'Protocol':
                    original_value = value
                    value = self._normalize_protocol_for_preview(value)
                    if row < 3:  # Debug first few rows
                        print(f"  Row {row}: '{original_value}' -> '{value}'")

                item = QTableWidgetItem(str(value))

                # Apply the same color coding as the actual widget
                if self.widget_type == 'route_widget' and widget_column == 'Protocol':
                    protocol_colors = {
                        'Static': '#ffff00',
                        'Static Default': '#ffff00',
                        'Connected': '#00ff00',
                        'Local': '#00ff88',
                        'OSPF': '#ff8800',
                        'OSPF Inter-Area': '#ff8800',
                        'OSPF External': '#ff8800',
                        'OSPF NSSA': '#ff8800',
                        'BGP': '#ff0088',
                        'BGP Internal': '#ff0088',
                        'BGP External': '#ff0088',
                        'EIGRP': '#8800ff',
                        'RIP': '#0088ff',
                        'ISIS': '#00ffff',
                        'ISIS Level-1': '#00ffff',
                        'ISIS Level-2': '#00ffff',
                        'Kernel': '#888888',
                        'Mobile': '#ff8888'
                    }
                    color = protocol_colors.get(value, '#ffffff')
                    item.setForeground(QColor(color))

                    if row < 3:  # Debug coloring
                        print(f"  Color for '{value}': {color}")

                elif any(f.field_name == field_name and f.required for f in self.widget_template.required_fields):
                    item.setForeground(QColor("#ff6b6b"))
                else:
                    item.setForeground(QColor("#4ecdc4"))

                self.widget_preview_table.setItem(row, col, item)

        self.widget_preview_table.resizeColumnsToContents()

        mapped_count = len(widget_columns)
        total_count = len(self.widget_template.required_fields) + len(self.widget_template.optional_fields)
        self.field_mapping_status.setText(f"Field Mapping:  {mapped_count}/{total_count} fields mapped")
        self.field_mapping_status.setStyleSheet("color: #00ff00;")

    def _normalize_protocol_for_preview(self, raw_protocol: str) -> str:
        """Apply the same protocol normalization that the real widget uses"""
        platform = self.platform_combo.currentText()

        # Use the same protocol mappings as in your platforms.json
        protocol_maps = {
            'arista_eos': {
                "S": "Static", "S*": "Static Default", "C": "Connected",
                "O": "OSPF", "O I": "OSPF Inter-Area", "O E": "OSPF External", "O N": "OSPF NSSA",
                "B": "BGP", "B I": "BGP Internal", "B E": "BGP External",
                "I": "ISIS", "i": "ISIS", "L1": "ISIS Level-1", "L2": "ISIS Level-2",
                "K": "Kernel",  "R": "RIP"
            },
            'cisco_ios': {
                "S": "Static", "C": "Connected", "L": "Local",
                "O": "OSPF", "B": "BGP", "D": "EIGRP", "R": "RIP", "I": "IGRP"
            },
            'cisco_nxos': {
                "S": "Static", "C": "Connected", "O": "OSPF", "B": "BGP", "E": "EIGRP"
            }
        }

        platform_map = protocol_maps.get(platform, protocol_maps.get('cisco_ios', {}))
        return platform_map.get(raw_protocol.strip(), raw_protocol)
    def _update_field_coverage(self, headers: list):
        """Update field coverage report"""
        template_fields = set(headers)
        required_fields = {field.field_name for field in self.widget_template.required_fields}
        optional_fields = {field.field_name for field in self.widget_template.optional_fields}

        covered_required = required_fields.intersection(template_fields)
        missing_required = required_fields - template_fields
        covered_optional = optional_fields.intersection(template_fields)
        missing_optional = optional_fields - template_fields
        extra_fields = template_fields - required_fields - optional_fields

        report_lines = []

        if covered_required:
            report_lines.append(f" Required fields covered ({len(covered_required)}):")
            report_lines.extend(f"  + {field}" for field in sorted(covered_required))

        if missing_required:
            report_lines.append(f"\n Required fields missing ({len(missing_required)}):")
            report_lines.extend(f"  - {field}" for field in sorted(missing_required))

        if covered_optional:
            report_lines.append(f"\n Optional fields covered ({len(covered_optional)}):")
            report_lines.extend(f"  + {field}" for field in sorted(covered_optional))

        if missing_optional:
            report_lines.append(f"\n Optional fields missing ({len(missing_optional)}):")
            report_lines.extend(f"  - {field}" for field in sorted(missing_optional))

        if extra_fields:
            report_lines.append(f"\n Extra fields in template ({len(extra_fields)}):")
            report_lines.extend(f"  ? {field}" for field in sorted(extra_fields))

        self.field_coverage_display.setPlainText('\n'.join(report_lines))

    def _save_template(self):
        """Save template to file"""
        try:
            command_map = {
                'cdp_neighbors': 'show_cdp_neighbors_detail',
                'arp_table': 'show_ip_arp',
                'route_table': 'show_ip_route',
                'system_info': 'show_version'
            }

            command_name = command_map.get(self.widget_template.command_type, self.widget_template.command_type)
            template_filename = f"{self.current_platform}_{command_name}.textfsm"
            template_path = os.path.join("templates/textfsm", template_filename)

            os.makedirs(os.path.dirname(template_path), exist_ok=True)

            content = self.template_editor.toPlainText()
            with open(template_path, 'w') as f:
                f.write(content)

            self.current_template_content = content
            self.has_unsaved_changes = False
            self.save_btn.setEnabled(False)

            self.template_saved.emit(self.widget_type, self.current_platform, content)

            QMessageBox.information(self, "Success", f"Template saved to {template_path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save template: {str(e)}")

    def _reset_template(self):
        """Reset template to original state"""
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "Reset Template",
                "This will discard all unsaved changes. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._load_template_for_platform(self.current_platform)