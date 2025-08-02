from PyQt6.QtWidgets import (QTextEdit, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QFileDialog, QTabWidget)
from PyQt6.QtCore import Qt, pyqtSignal
import os
import logging

logger = logging.getLogger('termtel.notepad')


class NotepadWidget(QWidget):
    """A rich text editor widget with save/load functionality"""

    # Signal when content changes (can be used for "unsaved changes" indicator)
    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path = None
        self.has_unsaved_changes = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Create toolbar
        toolbar = QHBoxLayout()

        # Add save button
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save_content)
        toolbar.addWidget(self.save_btn)

        # Add save as button
        self.save_as_btn = QPushButton("Save As...")
        self.save_as_btn.clicked.connect(self.save_content_as)
        toolbar.addWidget(self.save_as_btn)

        # Add open button
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self.load_content)
        toolbar.addWidget(self.open_btn)

        # Add spacer to push buttons to left
        toolbar.addStretch()

        # Create text editor
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Type your notes here...")
        self.editor.textChanged.connect(self.handle_content_change)

        # Add widgets to layout
        layout.addLayout(toolbar)
        layout.addWidget(self.editor)

    def handle_content_change(self):
        """Handle changes to the editor content"""
        if not self.has_unsaved_changes:
            self.has_unsaved_changes = True
            self.update_title()
        self.content_changed.emit()

    def update_title(self):
        """Update the tab title to show unsaved status"""
        try:
            # Walk up the widget hierarchy to find the QTabWidget
            parent = self.parent()
            while parent is not None:
                if isinstance(parent, QTabWidget):
                    # Found the tab widget
                    for i in range(parent.count()):
                        if parent.widget(i).findChild(NotepadWidget) == self:
                            current_title = parent.tabText(i)
                            if self.has_unsaved_changes and not current_title.endswith('*'):
                                parent.setTabText(i, current_title + '*')
                            elif not self.has_unsaved_changes and current_title.endswith('*'):
                                parent.setTabText(i, current_title[:-1])
                            break
                    break
                parent = parent.parent()
        except Exception as e:
            logger.warning(f"Failed to update tab title: {e}")

    def save_content(self):
        """Save the content to the current file or prompt for location"""
        if self.file_path:
            self._save_to_file(self.file_path)
        else:
            self.save_content_as()

    def save_content_as(self):
        """Prompt for save location and save content"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Note As",
            os.path.expanduser("~/Documents"),
            "Text Files (*.txt);;HTML Files (*.html);;All Files (*)"
        )

        if file_path:
            self._save_to_file(file_path)

    def _save_to_file(self, file_path):
        """Save content to specified file"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if file_path.lower().endswith('.html'):
                    f.write(self.editor.toHtml())
                else:
                    f.write(self.editor.toPlainText())

            self.file_path = file_path
            self.has_unsaved_changes = False
            self.update_title()
            logger.info(f"Successfully saved note to {file_path}")

        except Exception as e:
            logger.error(f"Error saving note: {e}")
            raise

    def load_content(self):
        """Load content from a file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Note",
            os.path.expanduser("~/Documents"),
            "Text Files (*.txt);;HTML Files (*.html);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if file_path.lower().endswith('.html'):
                    self.editor.setHtml(content)
                else:
                    self.editor.setPlainText(content)

                self.file_path = file_path
                self.has_unsaved_changes = False
                self.update_title()
                logger.info(f"Successfully loaded note from {file_path}")

            except Exception as e:
                logger.error(f"Error loading note: {e}")
                raise

    def get_content(self):
        """Get the current content"""
        return self.editor.toPlainText()

    def set_content(self, content):
        """Set the editor content"""
        self.editor.setPlainText(content)
        self.has_unsaved_changes = False
        self.update_title()

