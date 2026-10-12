"""A QTabWidget as tall as its current page (QTabWidget sizes itself to its tallest page)."""
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QTabWidget


class CompactTabWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, _index):
        self.updateGeometry()

    def _fit(self, base: QSize, page_size: QSize) -> QSize:
        bar = self.tabBar().sizeHint().height() if self.tabBar().isVisible() or self.count() else 0
        return QSize(base.width(), bar + page_size.height() + 2)

    def sizeHint(self):
        page = self.currentWidget()
        base = super().sizeHint()
        return base if page is None else self._fit(base, page.sizeHint())

    def minimumSizeHint(self):
        page = self.currentWidget()
        base = super().minimumSizeHint()
        return base if page is None else self._fit(base, page.minimumSizeHint())
