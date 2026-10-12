"""A row of numbered steps joined by a progress line (wizard header).

Done steps show a tick, the current one is filled with the accent colour and
haloed; moving between steps slides the halo and progress line across.
"""
from PyQt5.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, pyqtProperty
from PyQt5.QtGui import QFont, QPainter, QPen
from PyQt5.QtWidgets import QSizePolicy, QWidget

from ui import theme


class StepIndicator(QWidget):
    RADIUS = 12
    HALO = 17
    TOP = 22          # y of the circles' centres

    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self.steps = list(steps)
        self.current = 0
        self._position = 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(280)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self.setMinimumHeight(66)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        theme.signals.changed.connect(self.update)

    def _get_position(self):
        return self._position

    def _set_position(self, value):
        self._position = value
        self.update()

    position = pyqtProperty(float, _get_position, _set_position)

    def set_current(self, index, animate=True):
        self.current = index
        self._animation.stop()
        if animate and self.isVisible():
            self._animation.setStartValue(self._position)
            self._animation.setEndValue(float(index))
            self._animation.start()
        else:
            self._set_position(float(index))

    def _x(self, i):
        n = len(self.steps)
        margin = 44
        if n == 1:
            return self.width() / 2
        return margin + i * (self.width() - 2 * margin) / (n - 1)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        y = self.TOP
        last = len(self.steps) - 1
        x_at = self._x(0) + (self._x(last) - self._x(0)) * (self._position / max(1, last))

        # Track and progress
        painter.setPen(QPen(theme.qcolour("border"), 2, cap=Qt.RoundCap))
        painter.drawLine(QPointF(self._x(0), y), QPointF(self._x(last), y))
        painter.setPen(QPen(theme.qcolour("accent"), 2, cap=Qt.RoundCap))
        painter.drawLine(QPointF(self._x(0), y), QPointF(x_at, y))

        # Halo travelling with the current step
        halo = theme.qcolour("accent")
        halo.setAlpha(46)
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(x_at, y), self.HALO, self.HALO)

        number_font = QFont(theme.UI_FONT)
        number_font.setPixelSize(12)
        number_font.setWeight(QFont.DemiBold)
        label_font = QFont(theme.UI_FONT)
        label_font.setPixelSize(12)
        tick = theme.icon("check", "on_accent", 14).pixmap(14, 14)
        for i, name in enumerate(self.steps):
            centre = QPointF(self._x(i), y)
            done, current = i < self.current, i == self.current
            if done or current:
                painter.setPen(Qt.NoPen)
                painter.setBrush(theme.qcolour("accent"))
            else:
                painter.setPen(QPen(theme.qcolour("border_strong"), 1.5))
                painter.setBrush(theme.qcolour("surface"))
            painter.drawEllipse(centre, self.RADIUS, self.RADIUS)
            circle = QRectF(centre.x() - self.RADIUS, y - self.RADIUS, 2 * self.RADIUS, 2 * self.RADIUS)
            if done:
                painter.drawPixmap(int(centre.x() - 7), int(y - 7), tick)
            else:
                painter.setFont(number_font)
                painter.setPen(theme.qcolour("on_accent" if current else "text_muted"))
                painter.drawText(circle, Qt.AlignCenter, str(i + 1))

            label_font.setWeight(QFont.DemiBold if current else QFont.Medium)
            painter.setFont(label_font)
            painter.setPen(theme.qcolour("accent" if current else "text_secondary" if done else "text_muted"))
            painter.drawText(QRectF(centre.x() - 60, y + self.HALO + 4, 120, 18), Qt.AlignHCenter | Qt.AlignTop,
                             name)
        painter.end()
