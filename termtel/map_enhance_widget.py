import json
import sys
from importlib import resources

from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QDialog, QFileDialog, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QPushButton, QLabel,
                             QCheckBox, QComboBox, QGroupBox, QMessageBox, QWidget,
                             QTextEdit)
from PyQt6.QtCore import Qt

from termtel.drawio_mapper2 import NetworkDrawioExporter
from termtel.graphml_mapper4 import NetworkGraphMLExporter
from termtel.icon_map_editor import IconConfigEditor
from termtel.map_editor import TopologyWidget as EditorWidget
from termtel.enh_int_normalizer import InterfaceNormalizer


class TopologyEnhanceWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Set window flags to ensure proper cleanup
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # with resources.path('termtel', 'icons_lib') as icons_path:
        #     self.icons_path = str(icons_path)
        self.icons_path = str(Path(__file__).parent / 'icons_lib')
        self.node_editor = None
        self.icon_editor = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Input File Selection
        input_group = QGroupBox("Input Topology File")
        input_layout = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Select input JSON topology file...")
        self.input_path.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_path)
        input_layout.addWidget(browse_btn)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Output Directory Selection
        output_group = QGroupBox("Output Directory")
        output_layout = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Select output directory...")
        self.output_path.setReadOnly(True)
        output_browse_btn = QPushButton("Browse...")
        output_browse_btn.clicked.connect(self.browse_output)
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(output_browse_btn)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Options Group
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout()

        # Layout selection
        layout_box = QHBoxLayout()
        layout_box.addWidget(QLabel("Layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems(['grid', 'tree', 'balloon'])
        layout_box.addWidget(self.layout_combo)
        options_layout.addLayout(layout_box)

        # Checkboxes
        self.include_endpoints = QCheckBox("Include endpoint devices")
        self.include_endpoints.setChecked(True)
        options_layout.addWidget(self.include_endpoints)

        self.use_icons = QCheckBox("Use icons for device visualization")
        self.use_icons.setChecked(True)
        options_layout.addWidget(self.use_icons)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Add informational note about endpoints
        note_group = QGroupBox("⚠️ Important Note About Endpoint Filtering")
        note_layout = QVBoxLayout()

        note_text = QTextEdit()
        note_text.setMaximumHeight(80)
        note_text.setReadOnly(True)
        note_text.setStyleSheet("QTextEdit { background-color: #221c47; border: 1px solid #ffeaa7; }")

        note_content = """The "Include endpoint devices" checkbox only works when endpoints appear as peer references without their own top-level entries in the JSON. If RapidCMDB was exported without "Network Only" mode, endpoints may have been promoted to full network nodes and cannot be filtered out here. In that case, re-export from RapidCMDB using "Network Only" mode."""

        note_text.setPlainText(note_content)
        note_layout.addWidget(note_text)
        note_group.setLayout(note_layout)
        layout.addWidget(note_group)

        editor_mapping_btn = QPushButton("Manual Node Editor")
        editor_mapping_btn.clicked.connect(self.edit_nodes)
        layout.addWidget(editor_mapping_btn)

        icon_mapping_btn = QPushButton("Edit Icon Mappings")
        icon_mapping_btn.clicked.connect(self.edit_icon_mappings)
        layout.addWidget(icon_mapping_btn)

        # Export Button
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.export_topology)
        layout.addWidget(export_btn)

        # Add stretch to push everything to the top
        layout.addStretch()

    def closeEvent(self, event):
        """Override closeEvent to ensure proper cleanup"""
        # Close any child windows
        if self.node_editor is not None:
            self.node_editor.close()
            self.node_editor = None

        if self.icon_editor is not None:
            self.icon_editor.close()
            self.icon_editor = None

        # Accept the close event
        event.accept()

        # Explicitly delete this widget
        self.deleteLater()

    def normalize_topology_interfaces(self, network_data: dict) -> dict:
        """
        Normalize all interface names in the topology data before processing.
        This ensures consistent interface naming and prevents duplicate connections.
        """
        normalized_data = {}

        for node_id, node_data in network_data.items():
            # Copy node details as-is
            normalized_data[node_id] = {
                'node_details': node_data.get('node_details', {}),
                'peers': {}
            }

            # Process peers and normalize interface names
            peers = node_data.get('peers', {})
            for peer_id, peer_data in peers.items():
                # Copy peer metadata
                normalized_data[node_id]['peers'][peer_id] = {
                    'ip': peer_data.get('ip', ''),
                    'platform': peer_data.get('platform', ''),
                    'connections': []
                }

                # Normalize all connection interface names
                connections = peer_data.get('connections', [])
                for connection in connections:
                    if isinstance(connection, list) and len(connection) == 2:
                        local_port = InterfaceNormalizer.normalize(connection[0], use_short_name=True)
                        remote_port = InterfaceNormalizer.normalize(connection[1], use_short_name=True)
                        normalized_data[node_id]['peers'][peer_id]['connections'].append([local_port, remote_port])
                    else:
                        # Keep non-standard connection formats as-is
                        normalized_data[node_id]['peers'][peer_id]['connections'].append(connection)

        return normalized_data

    def edit_icon_mappings(self):
        # Close existing editor if it exists
        if self.icon_editor is not None:
            self.icon_editor.close()

        self.icon_editor = IconConfigEditor()
        self.icon_editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.icon_editor.show()

    def edit_nodes(self):
        # Close existing editor if it exists
        if self.node_editor is not None:
            self.node_editor.close()

        self.node_editor = EditorWidget()
        self.node_editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.node_editor.resize(800, 400)
        self.node_editor.show()

    def _get_icons_path(self):
        with resources.path('termtel', 'icons_lib') as icons_path:
            return str(icons_path)

    def browse_input(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Topology JSON File",
            ".",  # Current working directory
            "JSON Files (*.json)"
        )
        if filename:
            self.input_path.setText(filename)
            if not self.output_path.text():
                self.output_path.setText(str(Path(filename).parent))

    def browse_output(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            ".",  # Current working directory
            QFileDialog.Option.ShowDirsOnly
        )
        if directory:
            self.output_path.setText(directory)

    def export_topology(self):
        input_file = self.input_path.text()
        output_dir = self.output_path.text()

        if not input_file or not output_dir:
            QMessageBox.warning(self, "Missing Information",
                                "Please select both input file and output directory.")
            return

        try:
            with open(input_file, 'r') as f:
                network_data = json.load(f)

            # NORMALIZE INTERFACES BEFORE PROCESSING
            normalized_data = self.normalize_topology_interfaces(network_data)

            base_name = Path(input_file).stem
            output_base = Path(output_dir) / base_name

            # Get checkbox state
            include_endpoints = self.include_endpoints.isChecked()

            print(f"DEBUG: Include endpoints checkbox is {'checked' if include_endpoints else 'unchecked'}")

            common_params = {
                'include_endpoints': include_endpoints,  # Make sure this is passed correctly
                'use_icons': self.use_icons.isChecked(),
                'layout_type': self.layout_combo.currentText(),
                'icons_dir': self.icons_path
            }

            # Use normalized data for both exporters
            drawio_exporter = NetworkDrawioExporter(**common_params)
            drawio_output = output_base.with_suffix('.drawio')
            drawio_exporter.export_to_drawio(normalized_data, drawio_output)

            graphml_exporter = NetworkGraphMLExporter(**common_params)
            graphml_output = output_base.with_suffix('.graphml')
            graphml_exporter.export_to_graphml(normalized_data, graphml_output)

            QMessageBox.information(self, "Export Complete",
                                    f"Successfully exported to:\n{drawio_output}\n{graphml_output}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error during export:\n{str(e)}")
            import traceback
            traceback.print_exc()  # This will help debug any errors


def main():
    app = QApplication(sys.argv)

    # Set application quit behavior
    app.setQuitOnLastWindowClosed(True)

    # Create a window to hold our widget
    window = TopologyEnhanceWidget()  # Make the widget itself the main window
    window.setWindowTitle("Topology Enhance")

    # Show the window
    window.resize(600, 500)  # Increased height to accommodate the note
    window.show()

    # Start the event loop
    sys.exit(app.exec())


if __name__ == '__main__':
    main()