from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                             QPushButton, QFileDialog, QLabel, QLineEdit,
                             QMessageBox, QPlainTextEdit, QSplitter, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtSvgWidgets import QSvgWidget
from pathlib import Path
import json
import copy
import math
import networkx as nx
import matplotlib.pyplot as plt
import subprocess
import platform
import os

from termtel.map_json_platform import create_network_diagrams


class TopologyMergeDialog(QDialog):
    """Dialog for merging multiple topology map files."""

    # Signal emitted when merge is complete with the path to merged file
    merge_complete = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Merge Topology Maps")
        self.resize(1200, 800)  # Larger default size for the dialog
        self.setup_ui()
        self.apply_dark_theme()

    def apply_dark_theme(self):
        """Apply dark theme styling to match the main application."""
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
            }
            QLineEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                padding: 5px;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: #ffffff;
                border: none;
                padding: 5px 15px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4c4c4c;
            }
            QPushButton:disabled {
                background-color: #2c2c2c;
                color: #666666;
            }
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
            }
        """)

    def log_message(self, message: str):
        """Add message to log output."""
        self.log_output.appendPlainText(message)

    def update_buttons(self):
        """Update button states based on selection."""
        file_count = self.file_list.count()
        has_selection = bool(self.file_list.selectedItems())
        has_output = bool(self.output_file.text())

        self.remove_button.setEnabled(has_selection)
        self.preview_button.setEnabled(has_selection and len(self.file_list.selectedItems()) == 1)  # Only enable for single selection
        self.clear_button.setEnabled(file_count > 0)
        self.merge_button.setEnabled(file_count >= 2 and has_output)
        self.open_folder_button.setEnabled(has_output and Path(self.output_file.text()).parent.exists())

    def preview_selected_file(self):
        """Preview the selected topology file."""
        try:
            selected_items = self.file_list.selectedItems()
            if not selected_items:
                return

            # Get selected file path
            file_path = selected_items[0].text()
            self.log_message(f"Generating preview for: {Path(file_path).name}")

            # Load and parse JSON
            with open(file_path, 'r') as f:
                topology_data = json.load(f)

            # Generate temporary SVG for preview
            temp_svg = Path(file_path).with_suffix('.preview.svg')
            self.create_network_svg(topology_data, temp_svg)

            # Update preview widget
            self.preview_widget.load(str(temp_svg))
            self.log_message("Preview updated successfully")

            # Clean up temporary file
            try:
                temp_svg.unlink()
            except Exception as e:
                self.log_message(f"Warning: Could not remove temporary SVG: {e}")

        except Exception as e:
            error_msg = f"Error generating preview: {str(e)}"
            self.log_message(f"ERROR: {error_msg}")
            QMessageBox.warning(self, "Preview Error", error_msg)

    def open_output_folder(self):
        """Open the output folder in the system's file explorer."""
        try:
            output_path = Path(self.output_file.text())
            folder_path = output_path.parent.absolute()

            # Handle different operating systems
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", folder_path])
            else:  # Linux and other Unix-like
                subprocess.run(["xdg-open", folder_path])

            self.log_message(f"Opened folder: {folder_path}")
        except Exception as e:
            self.log_message(f"ERROR: Failed to open folder - {str(e)}")
            QMessageBox.warning(
                self,
                "Warning",
                f"Could not open folder: {str(e)}"
            )

    def add_files(self):
        """Open file dialog to add topology JSON files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Topology Files",
            "",
            "JSON Files (*.json)"
        )

        if files:
            existing_files = set(self.file_list.item(i).text()
                                 for i in range(self.file_list.count()))

            for file in files:
                if file not in existing_files:
                    self.file_list.addItem(file)
                    self.log_message(f"Added file: {Path(file).name}")

            self.update_buttons()
            self.suggest_output_name()

    def remove_selected(self):
        """Remove selected files from the list."""
        for item in self.file_list.selectedItems():
            self.log_message(f"Removed file: {Path(item.text()).name}")
            self.file_list.takeItem(self.file_list.row(item))
        self.update_buttons()

    def browse_output(self):
        """Select output file location."""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Merged Topology",
            self.output_file.text(),
            "JSON Files (*.json)"
        )
        if filename:
            self.output_file.setText(filename)
            self.log_message(f"Set output file: {Path(filename).name}")
            self.update_buttons()

    def suggest_output_name(self):
        """Suggest an output filename based on selected files."""
        if not self.output_file.text() and self.file_list.count() > 0:
            first_file = Path(self.file_list.item(0).text())
            suggested_name = first_file.parent / "merged_topology.json"
            self.output_file.setText(str(suggested_name))
            self.update_buttons()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)

        # Left side - File selection and merge controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # File selection area
        file_layout = QHBoxLayout()
        self.file_list = QListWidget()
        file_layout.addWidget(self.file_list)

        # Buttons for file management
        button_layout = QVBoxLayout()
        self.add_button = QPushButton("Add Files...")
        self.remove_button = QPushButton("Remove Selected")
        self.preview_button = QPushButton("Preview Selected")
        self.clear_button = QPushButton("Clear All")

        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.preview_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        file_layout.addLayout(button_layout)

        left_layout.addLayout(file_layout)

        # Output file selection
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output File:"))
        self.output_file = QLineEdit()
        self.output_file.setPlaceholderText("Enter output filename...")
        output_layout.addWidget(self.output_file)
        self.browse_button = QPushButton("Browse...")
        output_layout.addWidget(self.browse_button)

        left_layout.addLayout(output_layout)

        # Output log
        left_layout.addWidget(QLabel("Output Log"))
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(200)  # Limit height of log window
        left_layout.addWidget(self.log_output)

        # Action buttons
        button_box = QHBoxLayout()
        self.merge_button = QPushButton("Merge Files")
        self.merge_button.setEnabled(False)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.setEnabled(False)
        self.cancel_button = QPushButton("Cancel")
        button_box.addWidget(self.merge_button)
        button_box.addWidget(self.open_folder_button)
        button_box.addWidget(self.cancel_button)

        left_layout.addLayout(button_box)

        # Right side - Preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Preview"))

        # SVG Preview widget
        self.preview_widget = QSvgWidget()
        self.preview_widget.setMinimumSize(600, 600)
        right_layout.addWidget(self.preview_widget)

        # Add splitter between left and right panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)

        main_layout.addWidget(splitter)

        # Connect signals
        self.add_button.clicked.connect(self.add_files)
        self.remove_button.clicked.connect(self.remove_selected)
        self.preview_button.clicked.connect(self.preview_selected_file)

        self.clear_button.clicked.connect(self.file_list.clear)
        self.browse_button.clicked.connect(self.browse_output)
        self.merge_button.clicked.connect(self.merge_files)
        self.open_folder_button.clicked.connect(self.open_output_folder)
        self.cancel_button.clicked.connect(self.reject)
        self.file_list.itemSelectionChanged.connect(self.update_buttons)
        self.file_list.itemSelectionChanged.connect(self.suggest_output_name)

    def create_network_svg(self, map_data: dict, output_path: Path, min_layer_dist=1.0, min_node_dist=0.2,
                           dark_mode=True):
        """Create an SVG visualization of the network map using balloon layout."""
        # Create NetworkX graph
        G = nx.Graph()

        # Add nodes and edges
        added_edges = set()  # Track which edges have been added
        for node, data in map_data.items():
            # Add node with its attributes
            G.add_node(node,
                       ip=data['node_details'].get('ip', ''),
                       platform=data['node_details'].get('platform', ''))

            # Add edges from peer connections
            for peer, peer_data in data['peers'].items():
                if peer in map_data:  # Only add edge if peer exists
                    edge_key = tuple(sorted([node, peer]))
                    if edge_key not in added_edges:
                        # Get connection information
                        connections = peer_data.get('connections', [])
                        if connections:
                            local_port, remote_port = connections[0]
                            label = f"{local_port} - {remote_port}"
                        else:
                            label = ""
                        G.add_edge(node, peer, connection=label)
                        added_edges.add(edge_key)

        # Set up colors based on mode
        if dark_mode:
            bg_color = '#1C1C1C'
            edge_color = '#FFFFFF'
            node_color = '#4B77BE'  # Medium blue
            font_color = 'white'
            node_edge_color = '#FFFFFF'
        else:
            bg_color = 'white'
            edge_color = 'gray'
            node_color = 'lightblue'
            font_color = 'black'
            node_edge_color = 'black'

        # Create figure with larger size
        plt.figure(figsize=(20, 15))

        # Set figure background
        plt.gca().set_facecolor(bg_color)
        plt.gcf().set_facecolor(bg_color)

        # Calculate balloon layout using internal method
        pos = self._calculate_balloon_layout(G)

        # Draw edges with labels
        for edge in G.edges():
            node1, node2 = edge
            pos1 = pos[node1]
            pos2 = pos[node2]

            # Draw edge
            plt.plot([pos1[0], pos2[0]],
                     [pos1[1], pos2[1]],
                     color=edge_color,
                     linewidth=1.0,
                     alpha=0.6)

            # Add edge label at midpoint
            connection = G.edges[edge].get('connection', '')
            if connection:
                mid_x = (pos1[0] + pos2[0]) / 2
                mid_y = (pos1[1] + pos2[1]) / 2
                plt.text(mid_x, mid_y,
                         connection,
                         horizontalalignment='center',
                         verticalalignment='center',
                         fontsize=6,
                         color=font_color,
                         bbox=dict(facecolor=bg_color, edgecolor='none', alpha=0.7, pad=0.2),
                         zorder=1)

        # Draw nodes with rectangles
        node_width = 0.1
        node_height = 0.03
        for node, (x, y) in pos.items():
            plt.gca().add_patch(plt.Rectangle((x - node_width / 2, y - node_height / 2),
                                              node_width, node_height,
                                              facecolor=node_color,
                                              edgecolor=node_edge_color,
                                              linewidth=1.0,
                                              zorder=2))

            # Add node labels
            plt.text(x, y,
                     node,
                     horizontalalignment='center',
                     verticalalignment='center',
                     fontsize=8,
                     color=font_color,
                     bbox=dict(facecolor=node_color, edgecolor='none', pad=0.5),
                     zorder=3)

        # Remove axes
        plt.axis('off')

        # Adjust plot limits
        margin = 0.1
        x_values = [x for x, y in pos.values()]
        y_values = [y for x, y in pos.values()]
        plt.xlim(min(x_values) - margin, max(x_values) + margin)
        plt.ylim(min(y_values) - margin, max(y_values) + margin)

        # Save as SVG
        plt.savefig(output_path,
                    format='svg',
                    bbox_inches='tight',
                    pad_inches=0.1,
                    facecolor=bg_color,
                    edgecolor='none',
                    transparent=False)
        plt.close()

        return G

    def merge_maps(self, file1_data, file2_data):
        """Merge two topology maps while preserving the exact schema."""
        combined_data = copy.deepcopy(file1_data)

        for node, details in file2_data.items():
            if node in combined_data:
                # For existing nodes, merge peers and their connections
                for peer, peer_details in details['peers'].items():
                    if peer in combined_data[node]['peers']:
                        # Merge connections for existing peers
                        existing_connections = combined_data[node]['peers'][peer]['connections']
                        new_connections = peer_details['connections']

                        # Add only unique connections
                        for conn in new_connections:
                            if conn not in existing_connections:
                                existing_connections.append(conn)
                    else:
                        # Add new peers from file2
                        combined_data[node]['peers'][peer] = peer_details
            else:
                # Add new nodes from file2
                combined_data[node] = details

        return combined_data

    def merge_files(self):
        """Merge selected topology files."""
        try:
            self.log_message("Starting merge operation...")

            # Get all files
            files = [self.file_list.item(i).text()
                     for i in range(self.file_list.count())]

            # Start with first file
            self.log_message(f"Loading base file: {Path(files[0]).name}")
            with open(files[0], 'r') as f:
                merged_data = json.load(f)

            # Merge remaining files
            for file in files[1:]:
                self.log_message(f"Merging file: {Path(file).name}")
                with open(file, 'r') as f:
                    file_data = json.load(f)
                merged_data = self.merge_maps(merged_data, file_data)

            # Save merged result
            output_file = self.output_file.text()
            self.log_message(f"Saving merged topology to: {Path(output_file).name}")
            with open(output_file, 'w') as f:
                json.dump(merged_data, f, indent=4)

            # Generate visualization files
            output_dir = str(Path(output_file).parent)
            map_name = Path(output_file).stem
            self.log_message("Generating additional diagram formats...")
            create_network_diagrams(
                json_file=output_file,
                output_dir=output_dir,
                map_name=map_name
            )
            self.log_message("Generated .graphml and .drawio formats")

            # Generate and save SVG preview
            svg_path = Path(output_file).with_suffix('.svg')
            self.log_message("Generating topology visualization...")
            self.create_network_svg(merged_data, svg_path)

            # Update preview widget
            self.preview_widget.load(str(svg_path))
            self.log_message("Updated preview with merged topology")

            self.log_message("Merge completed successfully!")
            self.merge_complete.emit(output_file)

        except Exception as e:
            error_msg = f"Error merging files: {str(e)}"
            self.log_message(f"ERROR: {error_msg}")
            QMessageBox.critical(self, "Error", error_msg)
    def _calculate_balloon_layout(self, G, scale=1.0):
        """Helper method to calculate balloon layout positions."""
        # Find root node (core switch/router)
        core_nodes = [node for node in G.nodes() if 'core' in node.lower()]
        if core_nodes:
            root = max(core_nodes, key=lambda x: G.degree(x))
        else:
            # Fall back to highest degree node
            root = max(G.nodes(), key=lambda x: G.degree(x))

        # Initialize positions
        pos = {}
        pos[root] = (0, 0)

        # Position hub nodes
        hub_nodes = {node for node in G.nodes() if G.degree(node) >= 2 and node != root}
        angle_increment = 2 * math.pi / max(1, len(hub_nodes))

        # Position hubs in a circle around root
        hub_radius = 1.0 * scale
        for i, hub in enumerate(hub_nodes):
            angle = i * angle_increment
            pos[hub] = (
                hub_radius * math.cos(angle),
                hub_radius * math.sin(angle)
            )

        # Position leaf nodes around their hubs
        leaf_radius = 0.5 * scale
        leaf_nodes = set(G.nodes()) - {root} - hub_nodes
        for hub in hub_nodes:
            children = [n for n in G.neighbors(hub) if n in leaf_nodes]
            if children:
                child_angle_increment = 2 * math.pi / len(children)
                for j, child in enumerate(children):
                    angle = j * child_angle_increment
                    pos[child] = (
                        pos[hub][0] + leaf_radius * math.cos(angle),
                        pos[hub][1] + leaf_radius * math.sin(angle)
                    )
                    leaf_nodes.remove(child)

        # Position any remaining nodes
        remaining_radius = 1.5 * hub_radius
        if leaf_nodes:
            angle_increment = 2 * math.pi / len(leaf_nodes)
            for i, node in enumerate(leaf_nodes):
                angle = i * angle_increment
                pos[node] = (
                    remaining_radius * math.cos(angle),
                    remaining_radius * math.sin(angle)
                )

        return pos


if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    dialog = TopologyMergeDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        print("Merge completed successfully!")
    sys.exit(app.exec())