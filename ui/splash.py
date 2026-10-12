"""The start-up splash, drawn in code from the theme (no image asset to keep in sync)."""
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPixmap

from ui import theme

SPONSOR = "Drone Technology Research Group"
WIDTH, HEIGHT = 520, 300


def splash_pixmap(scale: float = 1.0) -> QPixmap:
    theme.load_fonts()
    pixmap = QPixmap(int(WIDTH * scale), int(HEIGHT * scale))
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.transparent)
    dark = theme.PALETTES["dark"]

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)

    # Rounded dark card with a faint accent glow from the top-left
    card = QPainterPath()
    card.addRoundedRect(QRectF(0, 0, WIDTH, HEIGHT), 18, 18)
    gradient = QLinearGradient(0, 0, WIDTH, HEIGHT)
    gradient.setColorAt(0.0, QColor("#1B1D3A"))
    gradient.setColorAt(0.55, QColor(dark.bg))
    gradient.setColorAt(1.0, QColor(dark.bg))
    painter.fillPath(card, gradient)

    # App mark: drone glyph on an accent tile
    tile = QRectF(40, 52, 64, 64)
    tile_path = QPainterPath()
    tile_path.addRoundedRect(tile, 18, 18)
    painter.fillPath(tile_path, QColor(theme.LIGHT.accent))
    side = int(40 * max(1.0, scale))   # render the glyph at device resolution
    icon = theme.icon("drone", "#FFFFFF", side).pixmap(side, side)
    painter.drawPixmap(QRectF(tile.x() + 12, tile.y() + 12, 40, 40), icon, QRectF(0, 0, side, side))

    title = QFont(theme.UI_FONT)
    title.setPixelSize(36)
    title.setWeight(QFont.Bold)
    painter.setFont(title)
    painter.setPen(QColor(dark.text))
    painter.drawText(QRectF(40, 136, WIDTH - 80, 46), Qt.AlignLeft | Qt.AlignVCenter, "Drone Trainer")

    tagline = QFont(theme.UI_FONT)
    tagline.setPixelSize(15)
    painter.setFont(tagline)
    painter.setPen(QColor(dark.text_secondary))
    painter.drawText(QRectF(40, 182, WIDTH - 80, 24), Qt.AlignLeft | Qt.AlignVCenter,
                     "Track, fly and train indoor drones")

    small = QFont(theme.UI_FONT)
    small.setPixelSize(11)
    painter.setFont(small)
    painter.setPen(QColor(dark.text_muted))
    painter.drawText(QRectF(40, HEIGHT - 44, WIDTH - 80, 20), Qt.AlignLeft | Qt.AlignVCenter,
                     f"Sponsored by the {SPONSOR}")
    painter.drawText(QRectF(40, HEIGHT - 44, WIDTH - 80, 20), Qt.AlignRight | Qt.AlignVCenter, "Starting…")
    painter.end()
    return pixmap
