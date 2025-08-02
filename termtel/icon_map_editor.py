import json
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
import pkg_resources
from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QMessageBox, QDialog, QLineEdit,
    QFormLayout, QApplication, QFileDialog, QHeaderView, QCompleter
)
from PyQt6.QtCore import Qt, QStringListModel


class AddMappingDialog(QDialog):
    def __init__(self, is_drawio: bool, icons_path: Optional[Path] = None):
        super().__init__()
        self.is_drawio = is_drawio
        self.icons_path = icons_path
        self.drawio_shapes = [
            "shape=mxgraph.cisco.switches.layer_3_switch",
            "shape=mxgraph.cisco.switches.workgroup_switch",
            "shape=mxgraph.cisco.switches.multilayer_remote_switch",
            "shape=mxgraph.cisco.routers.router",
            "shape=mxgraph.cisco.misc.voice_router",
            "shape=mxgraph.cisco.misc.ip_phone",
            "shape=mxgraph.cisco.misc.ata"
        ]
        self.setup_ui()

    def setup_ui(self) -> None:
        self.setWindowTitle("Add New Mapping")
        layout = QFormLayout(self)

        # Create input fields
        self.pattern = QLineEdit()
        self.icon = QLineEdit()

        icon_widget = QWidget()
        icon_layout = QHBoxLayout(icon_widget)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.addWidget(self.icon)

        # Add browse button for GraphML
        if not self.is_drawio and self.icons_path:
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(self.browse_icon)
            icon_layout.addWidget(browse_btn)

        # Set placeholders and labels
        icon_label = "Shape" if self.is_drawio else "Icon File"
        self.pattern.setPlaceholderText("e.g., C9300")
        self.icon.setPlaceholderText(
            "e.g., shape=mxgraph.cisco.switches.layer_3_switch" if self.is_drawio
            else "e.g., layer_3_switch.jpg"
        )

        # Set up autocomplete for Draw.io shapes
        if self.is_drawio:
            completer = QCompleter(self.drawio_shapes)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self.icon.setCompleter(completer)

        # Add fields to layout
        layout.addRow("Pattern:", self.pattern)
        layout.addRow(f"{icon_label}:", icon_widget)

        # Add buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")

        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        layout.addRow("", button_layout)

    def browse_icon(self) -> None:
        if not self.icons_path or not self.icons_path.exists():
            return

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon File",
            str(self.icons_path),
            "Image Files (*.jpg *.jpeg)"
        )
        if filename:
            self.icon.setText(Path(filename).name)


class IconConfigEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.drawio_data: Optional[Dict] = None
        self.graphml_data: Optional[Dict] = None
        self.icons_path: Optional[Path] = None
        self.setup_ui()
        self.load_configs()

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Create tabs
        self.tabs = QTabWidget()
        self.drawio_table = self.create_table(["Pattern", "Shape"])
        self.graphml_table = self.create_table(["Pattern", "Icon", "Browse"])

        self.tabs.addTab(self.drawio_table, "Draw.io Mappings")
        self.tabs.addTab(self.graphml_table, "GraphML Mappings")

        # Add buttons
        button_layout = QHBoxLayout()
        buttons = {
            "Add Mapping": self.add_mapping,
            "Remove Selected": self.remove_mapping,
            "Save Changes": self.save_configs
        }

        for text, slot in buttons.items():
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            button_layout.addWidget(btn)

        layout.addWidget(self.tabs)
        layout.addLayout(button_layout)

    def create_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        return table

    def get_config_paths(self) -> Tuple[Path, Path]:
        try:
            base_path = Path(pkg_resources.resource_filename('secure_cartography', 'icons_lib'))
        except ModuleNotFoundError:
            base_path = Path(__file__).parent / 'icons_lib'

        self.icons_path = base_path
        return (
            base_path / 'platform_icon_drawio.json',
            base_path / 'platform_icon_map.json'
        )

    def load_configs(self) -> None:
        drawio_path, graphml_path = self.get_config_paths()

        for path, attr_name, table in [
            (drawio_path, 'drawio_data', self.drawio_table),
            (graphml_path, 'graphml_data', self.graphml_table)
        ]:
            try:
                with open(path) as f:
                    setattr(self, attr_name, json.load(f))
                    self.populate_table(
                        table,
                        getattr(self, attr_name)['platform_patterns']
                    )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Load Error",
                    f"Error loading {path.stem} config: {str(e)}"
                )

    def populate_table(self, table: QTableWidget, data: Dict) -> None:
        table.setRowCount(len(data))
        is_graphml = table == self.graphml_table

        for row, (pattern, icon) in enumerate(data.items()):
            table.setItem(row, 0, QTableWidgetItem(pattern))
            table.setItem(row, 1, QTableWidgetItem(icon))
            if is_graphml:
                browse_btn = QPushButton("Browse")
                browse_btn.clicked.connect(self.browse_icons)
                table.setCellWidget(row, 2, browse_btn)

    def add_mapping(self) -> None:
        is_drawio = self.tabs.currentWidget() == self.drawio_table
        dialog = AddMappingDialog(is_drawio, self.icons_path)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            pattern, icon = dialog.pattern.text(), dialog.icon.text()

            if not pattern or not icon:
                QMessageBox.warning(
                    self,
                    "Input Error",
                    "Both pattern and icon/shape must be provided"
                )
                return

            current_table = self.tabs.currentWidget()
            row = current_table.rowCount()
            current_table.insertRow(row)
            current_table.setItem(row, 0, QTableWidgetItem(pattern))
            current_table.setItem(row, 1, QTableWidgetItem(icon))

            if current_table == self.graphml_table:
                browse_btn = QPushButton("Browse")
                browse_btn.clicked.connect(self.browse_icons)
                current_table.setCellWidget(row, 2, browse_btn)

    def browse_icons(self) -> None:
        if not self.icons_path or not self.icons_path.exists():
            return

        button = self.sender()
        if not button:
            return

        row = self.graphml_table.indexAt(button.pos()).row()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon File",
            str(self.icons_path),
            "Image Files (*.jpg *.jpeg)"
        )
        if filename:
            self.graphml_table.setItem(row, 1, QTableWidgetItem(Path(filename).name))

    def remove_mapping(self) -> None:
        current_table = self.tabs.currentWidget()
        selected = current_table.selectedItems()
        if selected:
            current_table.removeRow(selected[0].row())

    def save_configs(self) -> None:
        try:
            drawio_path, graphml_path = self.get_config_paths()

            for path, data, table in [
                (drawio_path, self.drawio_data, self.drawio_table),
                (graphml_path, self.graphml_data, self.graphml_table)
            ]:
                if data:
                    data['platform_patterns'] = self.get_table_data(table)
                    with open(path, 'w') as f:
                        json.dump(data, f, indent=2)

            QMessageBox.information(self, "Success", "Configurations saved successfully")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Save Error",
                f"Error saving configurations: {str(e)}"
            )

    def get_table_data(self, table: QTableWidget) -> Dict:
        return {
            table.item(row, 0).text(): table.item(row, 1).text()
            for row in range(table.rowCount())
        }


def main():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Icon Configuration Editor")

    layout = QVBoxLayout(window)
    editor = IconConfigEditor()
    layout.addWidget(editor)

    window.resize(800, 400)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()