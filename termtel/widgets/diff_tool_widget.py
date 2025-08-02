# diff_tool_widget.py
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QRect
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont, QPalette, QPainter, QTextFormat, QTextOption
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
                             QPushButton, QFileDialog, QSplitter, QLabel, QToolBar,
                             QStatusBar, QToolButton, QStyle, QTextEdit, QApplication)
import logging

logger = logging.getLogger('termtel.diff_tool')

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setFont(QFont("Consolas", 10))

    def sizeHint(self):
        return QSize(self.editor.lineNumberAreaWidth(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class DiffToolWrapper:
    """Wrapper class for the DiffToolWidget to standardize interface with the tab system"""

    def __init__(self, diff_tool_widget):
        self.diff_tool = diff_tool_widget

    def cleanup(self):
        """Handle cleanup when tab is closed"""
        if hasattr(self.diff_tool, 'cleanup'):
            self.diff_tool.cleanup()

    def update_theme(self, theme_manager, theme_name):
        """Pass theme updates to the diff tool widget"""
        if hasattr(self.diff_tool, 'apply_theme'):
            self.diff_tool.apply_theme(theme_manager, theme_name)

# Enhanced DiffEditor with proper theme support
class DiffEditor(QPlainTextEdit):
    updateRequest = pyqtSignal(object, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lineNumberArea = LineNumberArea(self)
        self.blockCountChanged.connect(self.updateLineNumberAreaWidth)
        self.updateRequest.connect(self.updateLineNumberArea)
        self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateLineNumberAreaWidth(0)
        self.setReadOnly(True)

        # Theme colors - will be updated by apply_theme
        self.bg_color = "#2b2b2b"
        self.text_color = "#f8f8f2"
        self.line_number_bg = "#313335"
        self.line_number_text = "#787878"
        self.current_line_bg = "#3a3a3a"

        # Set font to monospace for better code viewing
        font = QFont("Consolas", 10)
        self.setFont(font)

        # Apply initial styling
        self.update_styling()

    def update_styling(self):
        """Update editor styling based on current theme colors"""
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {self.bg_color};
                color: {self.text_color};
                border: none;
            }}
        """)

        # Force redraw of line numbers
        self.updateLineNumberAreaWidth(0)

    def lineNumberAreaWidth(self):
        digits = max(1, len(str(self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def apply_theme(self, colors):
        """Apply theme colors to editor"""
        if not colors:
            return

        self.bg_color = colors.get('background', '#2b2b2b')
        self.text_color = colors.get('text', '#f8f8f2')
        self.line_number_bg = colors.get('darker_bg', '#313335')
        self.line_number_text = colors.get('grid', '#787878')
        self.current_line_bg = colors.get('secondary', '#3a3a3a')

        self.update_styling()
        # Update line number area
        self.lineNumberArea.update()
        # Update current line highlighting
        self.highlightCurrentLine()

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.lineNumberArea)
        painter.fillRect(event.rect(), QColor(self.line_number_bg))

        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(blockNumber + 1)
                painter.setPen(QColor(self.line_number_text))
                # Make sure top is an integer
                rect = QRect(0, int(top), self.lineNumberArea.width(), self.fontMetrics().height())
                painter.drawText(rect, Qt.AlignmentFlag.AlignRight, number + " ")

            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            blockNumber += 1

    def lineNumberAreaWidth(self):
        digits = max(1, len(str(self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def updateLineNumberAreaWidth(self, _):
        self.setViewportMargins(self.lineNumberAreaWidth(), 0, 0, 0)

    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.lineNumberArea.setGeometry(cr.left(), cr.top(), self.lineNumberAreaWidth(), cr.height())

    def highlightCurrentLine(self):
        extraSelections = []

        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            lineColor = QColor(self.current_line_bg)
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extraSelections.append(selection)

        self.setExtraSelections(extraSelections)


# Enhanced navigation bar with theme support
class DiffNavigationBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(20)
        self.diffLocations = []  # List of (y_position, diff_type) tuples

        # Theme colors
        self.bg_color = "#313335"
        self.left_color = "#FFAAAA"  # Deletion
        self.right_color = "#AAFFAA"  # Addition
        self.changed_color = "#AAAAFF"  # Changes

        self.setStyleSheet(f"background-color: {self.bg_color};")

    def setDiffLocations(self, locations):
        self.diffLocations = locations
        self.update()

    def apply_theme(self, colors):
        """Apply theme colors to navigation bar"""
        if not colors:
            return

        self.bg_color = colors.get('darker_bg', '#313335')

        # Use theme's error, success and primary colors for diff markers
        self.left_color = colors.get('error', '#FFAAAA')
        self.right_color = colors.get('success', '#AAFFAA')
        self.changed_color = colors.get('primary', '#AAAAFF')

        self.setStyleSheet(f"background-color: {self.bg_color};")
        self.update()

    def paintEvent(self, event):
        if not self.diffLocations:
            return

        painter = QPainter(self)
        height = self.height()

        for pos, diff_type in self.diffLocations:
            # Map relative position (0-1) to widget height
            y = int(pos * height)

            if diff_type == "left":
                color = QColor(self.left_color)
            elif diff_type == "right":
                color = QColor(self.right_color)
            else:  # changed
                color = QColor(self.changed_color)

            painter.fillRect(0, y, self.width(), 3, color)


# Enhanced DiffWidget with theme support
class DiffWidget(QSplitter):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)

        # Theme variables
        self.splitter_bg = "#3c3f41"
        self.splitter_border = "#323232"
        self.splitter_hover = "#4b6eaf"

        # Left editor with navigation bar
        leftContainer = QWidget()
        leftLayout = QHBoxLayout(leftContainer)
        leftLayout.setContentsMargins(0, 0, 0, 0)
        leftLayout.setSpacing(0)

        self.leftEditor = DiffEditor()
        self.leftEditor.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.leftNavBar = DiffNavigationBar()

        leftLayout.addWidget(self.leftEditor)
        leftLayout.addWidget(self.leftNavBar)

        # Right editor with navigation bar
        rightContainer = QWidget()
        rightLayout = QHBoxLayout(rightContainer)
        rightLayout.setContentsMargins(0, 0, 0, 0)
        rightLayout.setSpacing(0)

        self.rightEditor = DiffEditor()
        self.rightEditor.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.rightNavBar = DiffNavigationBar()

        rightLayout.addWidget(self.rightEditor)
        rightLayout.addWidget(self.rightNavBar)

        # Add to splitter with custom handle
        self.addWidget(leftContainer)
        self.addWidget(rightContainer)

        # Set the handle width and style
        self.setHandleWidth(10)
        self.update_splitter_style()

        # Connect the scroll bars for synchronized scrolling
        self.leftEditor.verticalScrollBar().valueChanged.connect(self.syncScroll)
        self.rightEditor.verticalScrollBar().valueChanged.connect(self.syncScroll)

    def compareTexts(self):
        leftText = self.leftEditor.toPlainText()
        rightText = self.rightEditor.toPlainText()

        # Clear previous highlighting
        leftCursor = self.leftEditor.textCursor()
        leftCursor.select(QTextCursor.SelectionType.Document)
        leftCursor.setCharFormat(QTextCharFormat())

        rightCursor = self.rightEditor.textCursor()
        rightCursor.select(QTextCursor.SelectionType.Document)
        rightCursor.setCharFormat(QTextCharFormat())

        # Prepare formats
        leftOnlyFormat = QTextCharFormat()
        leftOnlyFormat.setBackground(QColor("#4f2b2b"))  # Darker red
        leftOnlyFormat.setForeground(QColor("#ffaaaa"))  # Light red text

        rightOnlyFormat = QTextCharFormat()
        rightOnlyFormat.setBackground(QColor("#2b4f2b"))  # Darker green
        rightOnlyFormat.setForeground(QColor("#aaffaa"))  # Light green text

        changedFormat = QTextCharFormat()
        changedFormat.setBackground(QColor("#2b2b4f"))  # Darker blue
        changedFormat.setForeground(QColor("#aaaaff"))  # Light blue text

        # Split text into lines
        leftLines = leftText.splitlines()
        rightLines = rightText.splitlines()

        # Create line-based diff
        from diff_match_patch import diff_match_patch
        dmp = diff_match_patch()

        # Track diff locations for navigation bars
        leftDiffLocations = []
        rightDiffLocations = []

        # Map each line to corresponding line in other text
        lineMap = self.computeLineMapping(leftLines, rightLines)

        # Process each line
        for leftIdx, rightIdx in lineMap:
            if leftIdx is not None and rightIdx is not None:
                # Lines exist in both texts - check for word differences
                leftLine = leftLines[leftIdx]
                rightLine = rightLines[rightIdx]

                if leftLine != rightLine:
                    # Calculate relative position for navigation bar
                    if len(leftLines) > 0:
                        leftPos = leftIdx / len(leftLines)
                        leftDiffLocations.append((leftPos, "changed"))

                    if len(rightLines) > 0:
                        rightPos = rightIdx / len(rightLines)
                        rightDiffLocations.append((rightPos, "changed"))

                    # Highlight the changed lines
                    self.highlightLine(self.leftEditor, leftIdx, changedFormat)
                    self.highlightLine(self.rightEditor, rightIdx, changedFormat)

                    # Highlight word differences within the lines
                    diffs = dmp.diff_main(leftLine, rightLine)
                    dmp.diff_cleanupSemantic(diffs)

                    leftPos = 0
                    rightPos = 0

                    for op, text in diffs:
                        if op == -1:  # Deletion (in left but not right)
                            self.highlightSection(self.leftEditor, leftIdx, leftPos,
                                                  leftPos + len(text), leftOnlyFormat)
                            leftPos += len(text)
                        elif op == 1:  # Addition (in right but not left)
                            self.highlightSection(self.rightEditor, rightIdx, rightPos,
                                                  rightPos + len(text), rightOnlyFormat)
                            rightPos += len(text)
                        else:  # No change
                            leftPos += len(text)
                            rightPos += len(text)
            elif leftIdx is not None:
                # Line exists only in left text
                if len(leftLines) > 0:
                    leftPos = leftIdx / len(leftLines)
                    leftDiffLocations.append((leftPos, "left"))

                # Highlight the left-only line
                self.highlightLine(self.leftEditor, leftIdx, leftOnlyFormat)
            elif rightIdx is not None:
                # Line exists only in right text
                if len(rightLines) > 0:
                    rightPos = rightIdx / len(rightLines)
                    rightDiffLocations.append((rightPos, "right"))

                # Highlight the right-only line
                self.highlightLine(self.rightEditor, rightIdx, rightOnlyFormat)

        # Update navigation bars
        self.leftNavBar.setDiffLocations(leftDiffLocations)
        self.rightNavBar.setDiffLocations(rightDiffLocations)

    def highlightLine(self, editor, lineIndex, format):
        """Highlight an entire line."""
        cursor = editor.textCursor()
        block = editor.document().findBlockByLineNumber(lineIndex)
        if not block.isValid():
            return
        cursor.setPosition(block.position())
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeCharFormat(format)

    def highlightSection(self, editor, lineIndex, startCol, endCol, format):
        """Highlight a section of a line."""
        cursor = editor.textCursor()
        block = editor.document().findBlockByLineNumber(lineIndex)
        if not block.isValid():
            return
        cursor.setPosition(block.position() + startCol)
        cursor.setPosition(block.position() + endCol, QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeCharFormat(format)

    def computeLineMapping(self, leftLines, rightLines):
        """Compute mapping between corresponding lines."""
        # Basic implementation - in production you'd use a better algorithm
        leftUsed = [False] * len(leftLines)
        rightUsed = [False] * len(rightLines)
        mapping = []

        # Find exact matches
        for i, leftLine in enumerate(leftLines):
            for j, rightLine in enumerate(rightLines):
                if leftLine == rightLine and not leftUsed[i] and not rightUsed[j]:
                    mapping.append((i, j))
                    leftUsed[i] = True
                    rightUsed[j] = True
                    break

        # Add unmatched lines
        for i in range(len(leftLines)):
            if not leftUsed[i]:
                mapping.append((i, None))

        for j in range(len(rightLines)):
            if not rightUsed[j]:
                mapping.append((None, j))

        # Sort by left index, then right index
        mapping.sort(key=lambda x: (x[0] if x[0] is not None else float('inf'),
                                    x[1] if x[1] is not None else float('inf')))

        return mapping

    def update_splitter_style(self):
        """Update splitter style based on theme colors"""
        self.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {self.splitter_bg};
                border: 1px solid {self.splitter_border};
            }}
            QSplitter::handle:hover {{
                background-color: {self.splitter_hover};
            }}
        """)

    def apply_theme(self, colors):
        """Apply theme colors to diff widget and its components"""
        if not colors:
            return

        # Update splitter colors
        self.splitter_bg = colors.get('secondary', '#3c3f41')
        self.splitter_border = colors.get('border', '#323232')
        self.splitter_hover = colors.get('primary', '#4b6eaf')

        # Update splitter style
        self.update_splitter_style()

        # Update editors
        self.leftEditor.apply_theme(colors)
        self.rightEditor.apply_theme(colors)

        # Update navigation bars
        self.leftNavBar.apply_theme(colors)
        self.rightNavBar.apply_theme(colors)

    def syncScroll(self, value):
        sender = self.sender()
        if sender == self.leftEditor.verticalScrollBar():
            self.rightEditor.verticalScrollBar().setValue(value)
        else:
            self.leftEditor.verticalScrollBar().setValue(value)

    def setTexts(self, leftText, rightText):
        self.leftEditor.setPlainText(leftText)
        self.rightEditor.setPlainText(rightText)

    # compareTexts method and other methods remain unchanged...


# Updated DiffToolWidget with properly cascading theme support
class DiffToolWidget(QWidget):
    """Main diff tool widget that can be integrated into the tab system"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_path_left = None
        self.file_path_right = None
        # Store the parent reference first before setup_ui is called
        self.parent_obj = parent

        # Theme-specific colors with defaults
        self.bg_color = "#2b2b2b"
        self.text_color = "#f8f8f2"
        self.primary_color = "#4b6eaf"
        self.secondary_color = "#3c3f41"
        self.border_color = "#323232"

        # Define colors for diff highlighting
        self.left_only_bg = "#4f2b2b"  # Darker red
        self.left_only_text = "#ffaaaa"  # Light red
        self.right_only_bg = "#2b4f2b"  # Darker green
        self.right_only_text = "#aaffaa"  # Light green
        self.changed_bg = "#2b2b4f"  # Darker blue
        self.changed_text = "#aaaaff"  # Light blue

        self.setup_ui()

    def setup_ui(self):
        """Initialize the UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Create toolbar
        toolbar = QToolBar()
        self.toolbar = toolbar  # Save reference for theming
        toolbar.setStyleSheet(f"""
            QToolBar {{
                background-color: {self.secondary_color};
                border: 1px solid {self.border_color};
                border-radius: 3px;
                spacing: 5px;
                padding: 3px;
            }}
        """)

        # File operations
        fileGroup = QWidget()
        fileLayout = QHBoxLayout(fileGroup)
        fileLayout.setContentsMargins(0, 0, 0, 0)
        fileLayout.setSpacing(5)

        btnOpenLeft = QPushButton('Open Left')
        btnOpenLeft.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        btnOpenLeft.clicked.connect(self.open_left_file)

        btnOpenRight = QPushButton('Open Right')
        btnOpenRight.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        btnOpenRight.clicked.connect(self.open_right_file)

        btnPasteLeft = QPushButton('Paste Left')
        btnPasteLeft.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        btnPasteLeft.clicked.connect(self.paste_to_left)

        btnPasteRight = QPushButton('Paste Right')
        btnPasteRight.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        btnPasteRight.clicked.connect(self.paste_to_right)

        fileLayout.addWidget(btnOpenLeft)
        fileLayout.addWidget(btnOpenRight)
        fileLayout.addWidget(btnPasteLeft)
        fileLayout.addWidget(btnPasteRight)

        # Compare and navigation
        navGroup = QWidget()
        navLayout = QHBoxLayout(navGroup)
        navLayout.setContentsMargins(0, 0, 0, 0)
        navLayout.setSpacing(5)

        btnCompare = QPushButton('Compare')
        self.btnCompare = btnCompare  # Save reference for theming
        btnCompare.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        btnCompare.clicked.connect(self.compare)
        btnCompare.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.primary_color};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.primary_color};
            }}
        """)

        btnPrevDiff = QToolButton()
        btnPrevDiff.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        btnPrevDiff.setToolTip("Previous Difference")
        btnPrevDiff.clicked.connect(self.navigate_to_prev_diff)

        btnNextDiff = QToolButton()
        btnNextDiff.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        btnNextDiff.setToolTip("Next Difference")
        btnNextDiff.clicked.connect(self.navigate_to_next_diff)

        navLayout.addWidget(btnCompare)
        navLayout.addWidget(btnPrevDiff)
        navLayout.addWidget(btnNextDiff)

        # Legend
        legendGroup = QWidget()
        self.legendGroup = legendGroup  # Save reference for theming
        legendLayout = QHBoxLayout(legendGroup)
        legendLayout.setContentsMargins(0, 0, 0, 0)
        legendLayout.setSpacing(5)

        legendLayout.addWidget(QLabel("Legend:"))
        self.left_only_label = self.add_legend_item(legendLayout, self.left_only_bg, self.left_only_text, "Left Only")
        self.right_only_label = self.add_legend_item(legendLayout, self.right_only_bg, self.right_only_text,
                                                     "Right Only")
        self.changed_label = self.add_legend_item(legendLayout, self.changed_bg, self.changed_text, "Changed")

        # Add groups to toolbar
        toolbar.addWidget(fileGroup)
        toolbar.addSeparator()
        toolbar.addWidget(navGroup)
        toolbar.addSeparator()
        toolbar.addWidget(legendGroup)

        # Main diff widget
        self.diff_widget = DiffWidget()

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {self.secondary_color};
                color: {self.text_color};
                border-top: 1px solid {self.border_color};
            }}
        """)
        self.status_bar.showMessage("Ready")

        # Add to main layout
        layout.addWidget(toolbar)
        layout.addWidget(self.diff_widget, 1)  # 1 = stretch factor
        layout.addWidget(self.status_bar)

        # Check if we should apply theme after UI is set up
        if self.parent_obj and hasattr(self.parent_obj, 'theme_manager') and hasattr(self.parent_obj, 'theme'):
            try:
                self.apply_theme(self.parent_obj.theme_manager, self.parent_obj.theme)
            except Exception as e:
                logger.error(f"Error applying theme: {str(e)}")

    def add_legend_item(self, layout, bg_color, text_color, text):
        label = QLabel()
        label.setText(text)
        label.setStyleSheet(f"""
            background-color: {bg_color}; 
            color: {text_color}; 
            padding: 3px 6px;
            border-radius: 2px;
        """)
        layout.addWidget(label)
        return label  # Return reference for later theme updates

    def open_left_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Left File", "", "All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.diff_widget.leftEditor.setPlainText(f.read())
                self.file_path_left = file_path
                self.status_bar.showMessage(f"Loaded: {file_path}")
            except Exception as e:
                self.status_bar.showMessage(f"Error loading file: {str(e)}")
                logger.error(f"Error loading left file: {str(e)}")

    def open_right_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Right File", "", "All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.diff_widget.rightEditor.setPlainText(f.read())
                self.file_path_right = file_path
                self.status_bar.showMessage(f"Loaded: {file_path}")
            except Exception as e:
                self.status_bar.showMessage(f"Error loading file: {str(e)}")
                logger.error(f"Error loading right file: {str(e)}")

    def paste_to_left(self):
        clipboard = QApplication.clipboard()
        self.diff_widget.leftEditor.setPlainText(clipboard.text())
        self.status_bar.showMessage("Text pasted to left editor")

    def paste_to_right(self):
        clipboard = QApplication.clipboard()
        self.diff_widget.rightEditor.setPlainText(clipboard.text())
        self.status_bar.showMessage("Text pasted to right editor")

    def compare(self):
        self.status_bar.showMessage("Comparing files...")
        try:
            # Update highlighting formats based on current theme
            self.update_diff_formats()

            self.diff_widget.compareTexts()

            # Count differences
            leftText = self.diff_widget.leftEditor.toPlainText().splitlines()
            rightText = self.diff_widget.rightEditor.toPlainText().splitlines()

            # Simple diff count for status bar
            from diff_match_patch import diff_match_patch
            dmp = diff_match_patch()
            diffs = dmp.diff_main('\n'.join(leftText), '\n'.join(rightText))

            additions = sum(len(text) for op, text in diffs if op == 1)
            deletions = sum(len(text) for op, text in diffs if op == -1)

            self.status_bar.showMessage(f"Comparison complete: {additions} additions, {deletions} deletions")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.status_bar.showMessage(f"Error during comparison: {str(e)}")
            logger.error(f"Error during comparison: {str(e)}")

    def update_diff_formats(self):
        """Update diff highlighting formats based on current theme"""

        # Get the current diff widget's editors to update formats
        leftEditor = self.diff_widget.leftEditor
        rightEditor = self.diff_widget.rightEditor

        # Left only format
        leftOnlyFormat = QTextCharFormat()
        leftOnlyFormat.setBackground(QColor(self.left_only_bg))
        leftOnlyFormat.setForeground(QColor(self.left_only_text))

        # Right only format
        rightOnlyFormat = QTextCharFormat()
        rightOnlyFormat.setBackground(QColor(self.right_only_bg))
        rightOnlyFormat.setForeground(QColor(self.right_only_text))

        # Changed format
        changedFormat = QTextCharFormat()
        changedFormat.setBackground(QColor(self.changed_bg))
        changedFormat.setForeground(QColor(self.changed_text))

        # Store these formats as instance variables for compareTexts to use
        self.diff_widget.leftOnlyFormat = leftOnlyFormat
        self.diff_widget.rightOnlyFormat = rightOnlyFormat
        self.diff_widget.changedFormat = changedFormat

    def navigate_to_prev_diff(self):
        try:
            self.diff_widget.navigateToPrevDiff()
            self.status_bar.showMessage("Navigated to previous difference")
        except Exception as e:
            self.status_bar.showMessage(f"Navigation error: {str(e)}")
            logger.error(f"Error navigating to previous difference: {str(e)}")

    def navigate_to_next_diff(self):
        try:
            self.diff_widget.navigateToNextDiff()
            self.status_bar.showMessage("Navigated to next difference")
        except Exception as e:
            self.status_bar.showMessage(f"Navigation error: {str(e)}")
            logger.error(f"Error navigating to next difference: {str(e)}")

    def apply_theme(self, theme_manager, theme_name):
        """Improved theme application that cascades to all components"""
        if not theme_manager:
            return

        # Get colors from theme manager
        try:
            # Try to get colors as a dictionary
            if hasattr(theme_manager, 'get_colors'):
                colors = theme_manager.get_colors(theme_name)
            else:
                # Fallback for older theme manager
                colors = theme_manager.get_chart_colors(theme_name)

            if not colors:
                return

            # Extract colors for diff widget
            self.bg_color = colors.get('background', '#2b2b2b')
            self.text_color = colors.get('text', '#f8f8f2')
            self.primary_color = colors.get('primary', '#4b6eaf')
            self.secondary_color = colors.get('secondary', '#3c3f41')
            self.border_color = colors.get('border', '#323232')

            # Set diff highlight colors based on theme
            # Use theme's color scheme to derive appropriate highlight colors

            # For left only (deleted content) - use error colors
            self.left_only_bg = self.darken_color(colors.get('error', '#ff5555'), 0.7)
            self.left_only_text = colors.get('error', '#ff5555')

            # For right only (added content) - use success colors
            self.right_only_bg = self.darken_color(colors.get('success', '#50fa7b'), 0.7)
            self.right_only_text = colors.get('success', '#50fa7b')

            # For changed content - use primary color
            self.changed_bg = self.darken_color(colors.get('primary', '#bd93f9'), 0.7)
            self.changed_text = colors.get('primary', '#bd93f9')

            # Update legend items
            self.left_only_label.setStyleSheet(f"""
                background-color: {self.left_only_bg}; 
                color: {self.left_only_text}; 
                padding: 3px 6px;
                border-radius: 2px;
            """)

            self.right_only_label.setStyleSheet(f"""
                background-color: {self.right_only_bg}; 
                color: {self.right_only_text}; 
                padding: 3px 6px;
                border-radius: 2px;
            """)

            self.changed_label.setStyleSheet(f"""
                background-color: {self.changed_bg}; 
                color: {self.changed_text}; 
                padding: 3px 6px;
                border-radius: 2px;
            """)

            # Apply main stylesheet for the widget
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {self.bg_color};
                    color: {self.text_color};
                }}
                QPushButton {{
                    background-color: {self.secondary_color};
                    border: 1px solid {self.border_color};
                    border-radius: 3px;
                    padding: 5px 15px;
                    color: {self.text_color};
                }}
                QPushButton:hover {{
                    background-color: {self.primary_color};
                }}
                QToolBar {{
                    background-color: {self.secondary_color};
                    border: 1px solid {self.border_color};
                    spacing: 5px;
                    padding: 3px;
                }}
                QStatusBar {{
                    background-color: {self.secondary_color};
                    color: {self.text_color};
                    border-top: 1px solid {self.border_color};
                }}
                QToolButton {{
                    background-color: {self.secondary_color};
                    border: 1px solid {self.border_color};
                    border-radius: 3px;
                    padding: 3px;
                }}
                QToolButton:hover {{
                    background-color: {self.primary_color};
                }}
            """)

            # Style the Compare button specially
            self.btnCompare.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.primary_color};
                    font-weight: bold;
                    color: {self.text_color};
                    border: 1px solid {self.border_color};
                    border-radius: 3px;
                    padding: 5px 15px;
                }}
                QPushButton:hover {{
                    background-color: {self.brighten_color(self.primary_color, 1.2)};
                }}
            """)

            # Update toolbar
            self.toolbar.setStyleSheet(f"""
                QToolBar {{
                    background-color: {self.secondary_color};
                    border: 1px solid {self.border_color};
                    border-radius: 3px;
                    spacing: 5px;
                    padding: 3px;
                }}
            """)

            # Update status bar
            self.status_bar.setStyleSheet(f"""
                QStatusBar {{
                    background-color: {self.secondary_color};
                    color: {self.text_color};
                    border-top: 1px solid {self.border_color};
                }}
            """)

            # Apply theme to the diff widget which cascades to editors and nav bars
            self.diff_widget.apply_theme(colors)

            # Update diff formats for future comparisons
            self.update_diff_formats()

        except Exception as e:
            logger.error(f"Error applying theme: {str(e)}")
            import traceback
            traceback.print_exc()

    def darken_color(self, color_hex, factor=0.7):
        """Darken a hex color by a factor (0.0-1.0)"""
        try:
            # Convert to RGB
            c = QColor(color_hex)
            r, g, b = c.red(), c.green(), c.blue()

            # Darken
            r = max(0, int(r * factor))
            g = max(0, int(g * factor))
            b = max(0, int(b * factor))

            # Convert back to hex
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return color_hex

    def brighten_color(self, color_hex, factor=1.3):
        """Brighten a hex color by a factor (>1.0)"""
        try:
            # Convert to RGB
            c = QColor(color_hex)
            r, g, b = c.red(), c.green(), c.blue()

            # Brighten
            r = min(255, int(r * factor))
            g = min(255, int(g * factor))
            b = min(255, int(b * factor))

            # Convert back to hex
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return color_hex
    def lineNumberAreaWidth(self):
        digits = max(1, len(str(self.blockCount())))
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    def cleanup(self):
        """Handle cleanup when the widget is closed."""
        try:
            # Add any specific cleanup code here if needed
            pass
        except Exception as e:
            logger.error(f"Error during diff tool cleanup: {e}")
            pass
    def updateLineNumberArea(self, rect, dy):
        if dy:
            self.lineNumberArea.scroll(0, dy)
        else:
            self.lineNumberArea.update(0, rect.y(), self.lineNumberArea.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateLineNumberAreaWidth(0)


# We need to update the compareTexts method to use the theme-defined formats
    def compareTexts(self):
        """Compare the texts in the left and right editors"""
        leftText = self.leftEditor.toPlainText()
        rightText = self.rightEditor.toPlainText()

        # Clear previous highlighting
        leftCursor = self.leftEditor.textCursor()
        leftCursor.select(QTextCursor.SelectionType.Document)
        leftCursor.setCharFormat(QTextCharFormat())

        rightCursor = self.rightEditor.textCursor()
        rightCursor.select(QTextCursor.SelectionType.Document)
        rightCursor.setCharFormat(QTextCharFormat())

        # Get formats from parent widget or use defaults
        # Check if we have formats defined by the theme
        if hasattr(self, 'leftOnlyFormat') and hasattr(self, 'rightOnlyFormat') and hasattr(self, 'changedFormat'):
            leftOnlyFormat = self.leftOnlyFormat
            rightOnlyFormat = self.rightOnlyFormat
            changedFormat = self.changedFormat
        else:
            # Use default formats if we don't have theme-defined ones
            leftOnlyFormat = QTextCharFormat()
            leftOnlyFormat.setBackground(QColor("#4f2b2b"))  # Darker red
            leftOnlyFormat.setForeground(QColor("#ffaaaa"))  # Light red text

            rightOnlyFormat = QTextCharFormat()
            rightOnlyFormat.setBackground(QColor("#2b4f2b"))  # Darker green
            rightOnlyFormat.setForeground(QColor("#aaffaa"))  # Light green text

            changedFormat = QTextCharFormat()
            changedFormat.setBackground(QColor("#2b2b4f"))  # Darker blue
            changedFormat.setForeground(QColor("#aaaaff"))  # Light blue text

        # Split text into lines
        leftLines = leftText.splitlines()
        rightLines = rightText.splitlines()

        # Create line-based diff
        from diff_match_patch import diff_match_patch
        dmp = diff_match_patch()

        # Track diff locations for navigation bars
        leftDiffLocations = []
        rightDiffLocations = []

        # Map each line to corresponding line in other text
        lineMap = self.computeLineMapping(leftLines, rightLines)

        # Process each line
        for leftIdx, rightIdx in lineMap:
            if leftIdx is not None and rightIdx is not None:
                # Lines exist in both texts - check for word differences
                leftLine = leftLines[leftIdx]
                rightLine = rightLines[rightIdx]

                if leftLine != rightLine:
                    # Calculate relative position for navigation bar
                    if len(leftLines) > 0:
                        leftPos = leftIdx / len(leftLines)
                        leftDiffLocations.append((leftPos, "changed"))

                    if len(rightLines) > 0:
                        rightPos = rightIdx / len(rightLines)
                        rightDiffLocations.append((rightPos, "changed"))

                    # Highlight the changed lines
                    self.highlightLine(self.leftEditor, leftIdx, changedFormat)
                    self.highlightLine(self.rightEditor, rightIdx, changedFormat)

                    # Highlight word differences within the lines
                    diffs = dmp.diff_main(leftLine, rightLine)
                    dmp.diff_cleanupSemantic(diffs)

                    leftPos = 0
                    rightPos = 0

                    for op, text in diffs:
                        if op == -1:  # Deletion (in left but not right)
                            self.highlightSection(self.leftEditor, leftIdx, leftPos,
                                                  leftPos + len(text), leftOnlyFormat)
                            leftPos += len(text)
                        elif op == 1:  # Addition (in right but not left)
                            self.highlightSection(self.rightEditor, rightIdx, rightPos,
                                                  rightPos + len(text), rightOnlyFormat)
                            rightPos += len(text)
                        else:  # No change
                            leftPos += len(text)
                            rightPos += len(text)
            elif leftIdx is not None:
                # Line exists only in left text
                if len(leftLines) > 0:
                    leftPos = leftIdx / len(leftLines)
                    leftDiffLocations.append((leftPos, "left"))

                # Highlight the left-only line
                self.highlightLine(self.leftEditor, leftIdx, leftOnlyFormat)
            elif rightIdx is not None:
                # Line exists only in right text
                if len(rightLines) > 0:
                    rightPos = rightIdx / len(rightLines)
                    rightDiffLocations.append((rightPos, "right"))

                # Highlight the right-only line
                self.highlightLine(self.rightEditor, rightIdx, rightOnlyFormat)

        # Update navigation bars
        self.leftNavBar.setDiffLocations(leftDiffLocations)
        self.rightNavBar.setDiffLocations(rightDiffLocations)
# ----- Standalone test for the widget -----

if __name__ == '__main__':
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setStyle("fusion")


    diff_tool = DiffToolWidget()
    diff_tool.resize(1200, 800)
    diff_tool.show()

    sys.exit(app.exec())