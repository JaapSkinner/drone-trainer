"""What a list shows when there is nothing in it yet: an icon, a short title and what to do next."""
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui import theme


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str = "", parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 22, 16, 22)
        column.setSpacing(6)
        column.setAlignment(Qt.AlignCenter)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("EmptyIcon")
        self.icon_label.setFixedSize(44, 44)
        self.icon_label.setAlignment(Qt.AlignCenter)
        column.addWidget(self.icon_label, 0, Qt.AlignHCenter)
        column.addSpacing(4)
        self.title_label = theme.label(title, "option-title")
        self.title_label.setAlignment(Qt.AlignCenter)
        column.addWidget(self.title_label)
        self.text_label = theme.label(text, "hint", wrap=True)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setVisible(bool(text))
        column.addWidget(self.text_label)
        theme.signals.changed.connect(self._on_theme_changed)
        self._on_theme_changed()

    @pyqtSlot(object)
    def _on_theme_changed(self, _palette=None):
        self.icon_label.setPixmap(theme.icon(self._icon_name, "accent", 22).pixmap(22, 22))

    def set_content(self, title: str = None, text: str = None, icon_name: str = None):
        if title is not None:
            self.title_label.setText(title)
        if text is not None:
            self.text_label.setText(text)
            self.text_label.setVisible(bool(text))
        if icon_name is not None and icon_name != self._icon_name:
            self._icon_name = icon_name
            self._on_theme_changed()

    def text(self) -> str:
        return f"{self.title_label.text()} {self.text_label.text()}".strip()
