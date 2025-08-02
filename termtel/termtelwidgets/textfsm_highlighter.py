from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
import re


class TextFSMSyntaxHighlighter(QSyntaxHighlighter):
    """Simple syntax highlighter for TextFSM templates"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_highlighting_rules()

    def _setup_highlighting_rules(self):
        """Setup basic highlighting rules"""
        self.highlighting_rules = []

        # Value definitions (blue)
        value_format = QTextCharFormat()
        value_format.setForeground(QColor("#5dade2"))
        value_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((r'^Value\s+\w+', value_format))

        # Comments (gray)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#85929e"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((r'#.*', comment_format))

    def highlightBlock(self, text):
        """Apply highlighting to a block of text"""
        for pattern, format in self.highlighting_rules:
            regex = re.compile(pattern)
            for match in regex.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, format)