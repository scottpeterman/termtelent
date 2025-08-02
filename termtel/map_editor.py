import traceback

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QLineEdit, QFileDialog, QHeaderView, QDialog,
                             QFormLayout, QComboBox, QDialogButtonBox, QLabel)
from PyQt6.QtCore import Qt
import json


class NodeEditorDialog(QDialog):
    def __init__(self, node_name="", ip="", platform="", existing_platforms=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Node")
        self.existing_platforms = existing_platforms or []

        layout = QFormLayout()

        # Node name field
        self.node_name = QLineEdit(node_name)
        layout.addRow("Node Name:", self.node_name)

        # IP address field
        self.ip = QLineEdit(ip)
        layout.addRow("IP Address:", self.ip)

        # Platform combo box
        self.platform = QComboBox()
        self.platform.setEditable(True)
        self.platform.addItems(self.existing_platforms)
        if platform and platform not in self.existing_platforms:
            self.platform.addItem(platform)
        self.platform.setCurrentText(platform)
        layout.addRow("Platform:", self.platform)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def get_values(self):
        return {
            'node_name': self.node_name.text(),
            'ip': self.ip.text(),
            'platform': self.platform.currentText()
        }


class TopologyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.topology_data = {}

    def initUI(self):
        layout = QVBoxLayout()

        # File selection area
        file_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Topology file path...")
        self.select_button = QPushButton("Select File")
        self.save_button = QPushButton("Save As")
        self.save_button.clicked.connect(self.saveTopology)
        file_layout.addWidget(self.save_button)
        self.select_button.clicked.connect(self.selectFile)
        file_layout.addWidget(self.path_input)
        file_layout.addWidget(self.select_button)

        # Tables area
        tables_layout = QHBoxLayout()

        # Top-level nodes table
        self.nodes_table = QTableWidget()
        self.nodes_table.setColumnCount(3)
        self.nodes_table.setHorizontalHeaderLabels(["Node", "IP", "Platform"])
        self.nodes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.nodes_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.nodes_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.nodes_table.cellDoubleClicked.connect(lambda row, col: self.editNode(self.nodes_table, row))

        # Peers-only table
        self.peers_table = QTableWidget()
        self.peers_table.setColumnCount(3)
        self.peers_table.setHorizontalHeaderLabels(["Peer", "IP", "Platform"])
        self.peers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.peers_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.peers_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.peers_table.cellDoubleClicked.connect(lambda row, col: self.editNode(self.peers_table, row))

        tables_layout.addWidget(self.nodes_table)
        tables_layout.addWidget(self.peers_table)

        layout.addLayout(file_layout)
        layout.addLayout(tables_layout)
        self.setLayout(layout)

    def getExistingPlatforms(self):
        platforms = set()
        for table in [self.nodes_table, self.peers_table]:
            for row in range(table.rowCount()):
                platform = table.item(row, 2)
                if platform and platform.text():
                    platforms.add(platform.text())
        return sorted(list(platforms))

    def editNode(self, table, row):
        node_name = table.item(row, 0).text()
        ip = table.item(row, 1).text()
        platform = table.item(row, 2).text() if table.item(row, 2) else ""

        dialog = NodeEditorDialog(
            node_name=node_name,
            ip=ip,
            platform=platform,
            existing_platforms=self.getExistingPlatforms(),
            parent=self
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.get_values()
            if table == self.peers_table:
                # Update all instances of this peer
                self.updateAllPeerInstances(node_name, values)
            else:
                # Handle top-level node update
                self.updateTopologyData(table, row, values)

            # Update table display
            table.item(row, 0).setText(values['node_name'])
            table.item(row, 1).setText(values['ip'])
            table.item(row, 2).setText(values['platform'])

    def updateAllPeerInstances(self, old_peer_name, new_values):
        for row in range(self.nodes_table.rowCount()):
            node_data = self.nodes_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if 'peers' in node_data and old_peer_name in node_data['peers']:
                connections = node_data['peers'][old_peer_name].get('connections', [])

                if old_peer_name != new_values['node_name']:
                    node_data['peers'][new_values['node_name']] = {
                        'ip': new_values['ip'],
                        'platform': new_values['platform'],
                        'connections': connections
                    }
                    del node_data['peers'][old_peer_name]
                else:
                    node_data['peers'][old_peer_name].update({
                        'ip': new_values['ip'],
                        'platform': new_values['platform']
                    })

                # Update the UserRole data
                self.nodes_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, node_data)


    def refreshPeersTable(self):
        self.peers_table.setRowCount(0)
        seen_peers = set(self.topology_data.keys())

        for node_data in self.topology_data.values():
            for peer_name, peer_data in node_data.get('peers', {}).items():
                if peer_name not in seen_peers:
                    seen_peers.add(peer_name)
                    self.addPeerToTable(peer_name, peer_data['ip'],
                                        peer_data['platform'])

    def saveTopology(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Save Topology File", "", "JSON Files (*.json)")
        if filename:
            try:
                new_topology = {}
                for row in range(self.nodes_table.rowCount()):
                    node_name = self.nodes_table.item(row, 0).text()
                    node_data = self.nodes_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

                    print(f"Saving node {node_name}:")  # Debug
                    print(json.dumps(node_data, indent=2))  # Debug

                    if 'node_details' not in node_data:
                        node_data['node_details'] = {}

                    node_data['node_details'].update({
                        'ip': self.nodes_table.item(row, 1).text(),
                        'platform': self.nodes_table.item(row, 2).text()
                    })

                    new_topology[node_name] = node_data

                with open(filename, 'w') as f:
                    json.dump(new_topology, f, indent=4)

                self.loadTopology(filename)

            except Exception as e:
                traceback.print_exc()

    def updateTopologyData(self, table, row, values):
        old_name = table.item(row, 0).text()
        new_name = values['node_name']

        if table == self.nodes_table:
            node_data = self.topology_data.get(old_name, {})
            if 'node_details' not in node_data:
                node_data['node_details'] = {}

            node_data['node_details'].update({
                'ip': values['ip'],
                'platform': values['platform']
            })

            if old_name != new_name:
                self.topology_data[new_name] = node_data
                del self.topology_data[old_name]
        else:
            # Update peer information in all nodes
            for node_data in self.topology_data.values():
                if 'peers' in node_data and old_name in node_data['peers']:
                    peer_data = node_data['peers'][old_name]
                    if old_name != new_name:
                        node_data['peers'][new_name] = peer_data
                        del node_data['peers'][old_name]

                    peer_data.update({
                        'ip': values['ip'],
                        'platform': values['platform']
                    })

    def selectFile(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Topology File", "", "JSON Files (*.json)")
        if filename:
            self.path_input.setText(filename)
            self.loadTopology(filename)

    def loadTopology(self, filename):
        try:
            with open(filename, 'r') as f:
                self.topology_data = json.load(f)

            self.nodes_table.setRowCount(0)
            self.peers_table.setRowCount(0)

            # Add all top-level nodes
            for node_name, node_data in self.topology_data.items():
                details = node_data.get('node_details', {})
                self.addNodeToTable(
                    self.nodes_table,
                    node_name,
                    details.get('ip', ''),
                    details.get('platform', ''),
                    node_data
                )

            # Add unique peers
            # Add unique peers
            seen_peers = set(self.topology_data.keys())
            for node_name, node_data in self.topology_data.items():
                for peer_name, peer_data in node_data.get('peers', {}).items():
                    if peer_name not in seen_peers:
                        seen_peers.add(peer_name)
                        self.addPeerToTable(peer_name, peer_data['ip'], peer_data['platform'],
                                            [(node_name, peer_data)])

        except Exception as e:
            print(e)
            traceback.print_exc()

    def addPeerToTable(self, peer_name, ip, platform, references=None):
        row = self.peers_table.rowCount()
        self.peers_table.insertRow(row)

        peer_item = QTableWidgetItem(peer_name)
        if references:
            peer_item.setData(Qt.ItemDataRole.UserRole, references)

        self.peers_table.setItem(row, 0, peer_item)
        self.peers_table.setItem(row, 1, QTableWidgetItem(ip))
        self.peers_table.setItem(row, 2, QTableWidgetItem(platform))

        return row

    def addNodeToTable(self, table, name, ip, platform, node_data=None):
        row = table.rowCount()
        table.insertRow(row)

        name_item = QTableWidgetItem(name)
        if node_data:
            name_item.setData(Qt.ItemDataRole.UserRole, node_data)

        table.setItem(row, 0, name_item)
        table.setItem(row, 1, QTableWidgetItem(ip))
        table.setItem(row, 2, QTableWidgetItem(platform))

        return row

def main():
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    widget = TopologyWidget()
    widget.resize(800, 400)
    widget.show()
    sys.exit(app.exec())

# Example usage:
if __name__ == '__main__':
    main()