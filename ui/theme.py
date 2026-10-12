"""App-wide look: colour tokens, fonts, icons and the global stylesheet.

Widgets don't hard-code colours. They declare what they *are* with dynamic
properties and the stylesheet does the rest:

* buttons — ``variant``: ``primary`` | ``danger`` | ``success`` | ``subtle`` |
  ``ghost`` | ``icon`` (default = secondary), ``size``: ``lg``
* labels — ``role``: ``title`` | ``subtitle`` | ``section`` | ``hint`` |
  ``mono`` | ``value``; ``tone``: ``success`` | ``warning`` | ``danger`` |
  ``muted`` | ``accent``
* frames — ``role``: ``card`` | ``card-alt`` | ``chip`` | ``hud``

Use the helpers (``button``, ``label``, ``set_tone``…) rather than calling
``setStyleSheet`` with colours. ``theme.colour("danger")`` gives a token for
painting; ``theme.icon("plus")`` a recoloured Lucide icon. ``theme.apply()``
switches between ``light`` and ``dark`` at runtime.
"""
from __future__ import annotations

import os
import tempfile
import weakref
from dataclasses import dataclass, fields
from typing import Dict, Optional

from PyQt5.QtCore import QByteArray, QObject, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStyleFactory, QToolButton,
                             QVBoxLayout, QWidget)

from services.paths import APP_ROOT

FONT_DIR = os.path.join(APP_ROOT, "ui", "assets", "fonts")
ICON_DIR = os.path.join(APP_ROOT, "ui", "assets", "lucide")
UI_FONT = "Inter"
MONO_FONT = "JetBrains Mono"


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str               # window background
    surface: str          # panels, inputs, cards
    surface_alt: str      # subtle fills: group cards, table headers
    surface_hover: str
    surface_pressed: str
    sidebar: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_subtle: str    # selected rows, subtle buttons
    on_accent: str        # text on accent fills
    success: str
    success_subtle: str
    warning: str
    warning_subtle: str
    danger: str
    danger_hover: str
    danger_subtle: str
    solid_success: str    # filled success / danger buttons (white text on them)
    solid_success_hover: str
    solid_danger: str
    solid_danger_hover: str
    tooltip_bg: str
    tooltip_text: str
    hud_bg: str           # overlays on the 3-D view (rgba)
    viewport_top: str     # 3-D view background gradient
    viewport_bottom: str
    grid: str
    grid_major: str


LIGHT = Palette(
    name="light",
    bg="#F4F5F7", surface="#FFFFFF", surface_alt="#F8F9FB", surface_hover="#F1F3F5", surface_pressed="#E7EAEE",
    sidebar="#EEF0F3", border="#E3E6EA", border_strong="#CDD2D9",
    text="#15181D", text_secondary="#4B5260", text_muted="#8A919D",
    accent="#4F46E5", accent_hover="#4338CA", accent_pressed="#3730A3", accent_subtle="#EEEEFF",
    on_accent="#FFFFFF",
    success="#15803D", success_subtle="#E3F4E8", warning="#B45309", warning_subtle="#FDF1DE",
    danger="#DC2626", danger_hover="#C21F1F", danger_subtle="#FDE7E7",
    solid_success="#15803D", solid_success_hover="#166534", solid_danger="#DC2626", solid_danger_hover="#B91C1C",
    tooltip_bg="#1C2027", tooltip_text="#F3F4F6",
    hud_bg="rgba(255, 255, 255, 222)",
    viewport_top="#F7F9FB", viewport_bottom="#DDE3EA",
    grid="#C5CCD5", grid_major="#9AA4B1",
)

DARK = Palette(
    name="dark",
    bg="#0E1014", surface="#16191F", surface_alt="#1B1F26", surface_hover="#222731", surface_pressed="#2A303B",
    sidebar="#121419", border="#272C35", border_strong="#363C47",
    text="#E8EAED", text_secondary="#A9B0BB", text_muted="#6D7581",
    accent="#8B93FF", accent_hover="#A5ACFF", accent_pressed="#6E76F5", accent_subtle="#22244A",
    on_accent="#0B0C1F",
    success="#4ADE80", success_subtle="#13301F", warning="#FBBF24", warning_subtle="#33280F",
    danger="#F87171", danger_hover="#FB8B8B", danger_subtle="#3A1717",
    solid_success="#15803D", solid_success_hover="#16A34A", solid_danger="#C62828", solid_danger_hover="#DC2626",
    tooltip_bg="#E8EAED", tooltip_text="#15181D",
    hud_bg="rgba(22, 25, 31, 225)",
    viewport_top="#1C2129", viewport_bottom="#0C0E12",
    grid="#2C333D", grid_major="#46505D",
)

PALETTES = {"light": LIGHT, "dark": DARK}


class _ThemeSignals(QObject):
    changed = pyqtSignal(object)   # Palette


signals = _ThemeSignals()
_palette: Palette = LIGHT
_fonts_loaded = False
_icon_users = weakref.WeakKeyDictionary()   # widget → (icon name, tone, size)
_icon_cache = {}                            # (name, colour, size) → QIcon


def palette() -> Palette:
    return _palette


def current_name() -> str:
    """'light' or 'dark'."""
    return next((name for name, p in PALETTES.items() if p is _palette), "light")


def colour(token: str) -> str:
    return getattr(_palette, token)


def qcolour(token: str) -> QColor:
    return QColor(colour(token))


def rgba(token: str):
    """A token as an (r, g, b, a) tuple of floats, for OpenGL."""
    c = QColor(colour(token))
    return (c.redF(), c.greenF(), c.blueF(), c.alphaF())


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

def load_fonts():
    global _fonts_loaded
    if _fonts_loaded:
        return
    for name in sorted(os.listdir(FONT_DIR)):
        if name.startswith(("Inter-", "JetBrainsMono-")) and name.endswith(".ttf"):
            QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, name))
    _fonts_loaded = True


def mono_font(point_size: float = 10.0) -> QFont:
    font = QFont(MONO_FONT)
    font.setPointSizeF(point_size)
    font.setStyleHint(QFont.Monospace)
    return font


# ---------------------------------------------------------------------------
# Icons (Lucide, recoloured per theme)
# ---------------------------------------------------------------------------

def _icon_colour(tone: Optional[str]) -> str:
    if tone and tone.startswith("#"):
        return tone
    return colour({None: "text_secondary", "accent": "accent", "on_accent": "on_accent", "danger": "danger",
                   "success": "success", "warning": "warning", "muted": "text_muted",
                   "text": "text"}.get(tone, tone or "text_secondary"))


def _svg_bytes(name: str, colour_hex: str, stroke: Optional[float] = None) -> bytes:
    with open(os.path.join(ICON_DIR, f"{name}.svg"), "r", encoding="utf-8") as fh:
        svg = fh.read()
    svg = svg.replace("currentColor", colour_hex)
    if stroke is not None:
        svg = svg.replace('stroke-width="2"', f'stroke-width="{stroke}"')
    return svg.encode("utf-8")


def icon(name: str, tone: Optional[str] = None, size: int = 18) -> QIcon:
    """A Lucide icon drawn in a theme colour (``tone``: a token, a tone name or '#RRGGBB')."""
    key = (name, _icon_colour(tone), size, colour("text_muted"))
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    from PyQt5.QtSvg import QSvgRenderer
    result = QIcon()
    for mode, colour_hex in ((QIcon.Normal, key[1]), (QIcon.Disabled, colour("text_muted"))):
        renderer = QSvgRenderer(QByteArray(_svg_bytes(name, colour_hex)))
        for scale in (1, 2):
            pixmap = QPixmap(size * scale, size * scale)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(scale)
            result.addPixmap(pixmap, mode)
    _icon_cache[key] = result
    return result


def set_icon(widget, name: str, tone: Optional[str] = None, size: int = 18):
    """Give a button an icon that is re-coloured when the theme changes."""
    widget.setIcon(icon(name, tone, size))
    widget.setIconSize(QSize(size, size))
    _icon_users[widget] = (name, tone, size)


def _refresh_icons():
    for widget, (name, tone, size) in list(_icon_users.items()):
        try:
            widget.setIcon(icon(name, tone, size))
        except RuntimeError:   # C++ object already deleted
            _icon_users.pop(widget, None)


def _qss_image(name: str, colour_hex: str, stroke: float = 2.5) -> str:
    """Path of a recoloured SVG for use in ``image: url(...)`` (cached on disk)."""
    folder = os.path.join(tempfile.gettempdir(), "drone_trainer_icons")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}_{colour_hex.strip('#')}_{stroke}.svg")
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(_svg_bytes(name, colour_hex, stroke))
    return path.replace("\\", "/")


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

def stylesheet(p: Palette = None) -> str:
    p = p or _palette
    check = _qss_image("check", p.on_accent, 3)
    down = _qss_image("chevron-down", p.text_secondary)
    up = _qss_image("chevron-up", p.text_secondary)
    down_muted = _qss_image("chevron-down", p.text_muted)
    up_muted = _qss_image("chevron-up", p.text_muted)
    eye = _qss_image("eye", p.text_secondary, 2)
    dock_close = _qss_image("x", p.text_secondary, 2)
    dock_float = _qss_image("layers", p.text_secondary, 2)
    eye_off = _qss_image("eye-off", p.text_muted, 2)
    return f"""
* {{ font-family: "{UI_FONT}"; font-size: 13px; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QWidget {{ color: {p.text}; }}
QDockWidget {{ background: {p.bg}; border: none; }}
QDockWidget#applicationConsoleDock {{ titlebar-close-icon: url({dock_close}); titlebar-normal-icon: url({dock_float}); }}
QDockWidget#applicationConsoleDock::title {{ background: {p.surface}; border-top: 1px solid {p.border};
    padding: 7px 12px; text-align: left; }}
QDockWidget#applicationConsoleDock::close-button, QDockWidget#applicationConsoleDock::float-button {{
    border: none; background: transparent; padding: 2px; border-radius: 5px; }}
QDockWidget#applicationConsoleDock::close-button:hover, QDockWidget#applicationConsoleDock::float-button:hover {{
    background: {p.surface_hover}; }}
QDockWidget > QWidget {{ background: {p.bg}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QStackedWidget {{ background: transparent; }}

/* ---- text roles --------------------------------------------------------- */
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 19px; font-weight: 700; color: {p.text}; padding: 2px 0 6px 0; }}
QLabel[role="display"] {{ font-size: 24px; font-weight: 700; color: {p.text}; }}
QLabel[role="subtitle"] {{ font-size: 15px; font-weight: 600; color: {p.text}; }}
QLabel[role="section"] {{ font-size: 11px; font-weight: 600; color: {p.text_muted}; padding-top: 6px; }}
QLabel[role="option-title"] {{ font-weight: 600; }}
QLabel[role="metric"] {{ font-size: 20px; font-weight: 700; color: {p.text}; }}
QLabel[role="pill"] {{ border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600;
                       background: {p.surface_alt}; color: {p.text_secondary}; }}
QLabel[role="pill"][tone="success"] {{ background: {p.success_subtle}; color: {p.success}; }}
QLabel[role="pill"][tone="warning"] {{ background: {p.warning_subtle}; color: {p.warning}; }}
QLabel[role="pill"][tone="danger"] {{ background: {p.danger_subtle}; color: {p.danger}; }}
QLabel[role="pill"][tone="accent"] {{ background: {p.accent_subtle}; color: {p.accent}; }}
QLabel[role="banner"] {{ border-radius: 8px; padding: 8px 12px; }}
QLabel[role="banner"][tone="danger"] {{ background: {p.danger_subtle}; color: {p.danger}; }}
QLabel[role="banner"][tone="warning"] {{ background: {p.warning_subtle}; color: {p.warning}; }}
QLabel[role="banner"][tone="success"] {{ background: {p.success_subtle}; color: {p.success}; }}
QLabel[role="banner"][tone="accent"] {{ background: {p.accent_subtle}; color: {p.accent}; }}
QLabel[role="hint"] {{ color: {p.text_muted}; font-size: 12px; }}
QLabel[role="mono"], QLabel[role="value"] {{ font-family: "{MONO_FONT}"; font-size: 12px; }}
QLabel[role="value"] {{ color: {p.text}; }}
QLabel[tone="success"] {{ color: {p.success}; }}
QLabel[tone="warning"] {{ color: {p.warning}; }}
QLabel[tone="danger"] {{ color: {p.danger}; }}
QLabel[tone="muted"] {{ color: {p.text_muted}; }}
QLabel[tone="accent"] {{ color: {p.accent}; }}

/* ---- cards / group boxes ---------------------------------------------- */
QGroupBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px;
             margin-top: 22px; padding: 12px 10px 10px 10px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 4px; top: 2px;
                    padding: 0 4px; color: {p.text_secondary}; font-size: 12px; font-weight: 600; }}
QFrame[role="card"] {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame[role="card-alt"] {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 10px; }}
QFrame[role="chip"] {{ background: {p.surface_alt}; border: 1px solid {p.border}; border-radius: 8px; }}
QFrame[role="hud"] {{ background: {p.hud_bg}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame[role="card"][selected="true"] {{ border: 1px solid {p.accent}; }}
QFrame[role="card"] QGroupBox {{ background: transparent; border: none; border-top: 1px solid {p.border};
    border-radius: 0; margin-top: 20px; padding: 10px 0 0 0; }}
QFrame[role="card"] QGroupBox::title {{ left: 0; top: 2px; padding: 0; }}
QFrame[role="divider"] {{ background: {p.border}; max-height: 1px; min-height: 1px; border: none; }}

/* ---- buttons ---------------------------------------------------------- */
QPushButton {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong};
               border-radius: 8px; padding: 6px 14px; min-height: 18px; font-weight: 500; }}
QPushButton:hover {{ background: {p.surface_hover}; }}
QPushButton:pressed {{ background: {p.surface_pressed}; }}
QPushButton:focus {{ border: 1px solid {p.accent}; }}
QPushButton:disabled {{ color: {p.text_muted}; background: {p.surface_alt}; border-color: {p.border}; }}
QPushButton:checked {{ background: {p.accent_subtle}; border-color: {p.accent}; color: {p.accent}; }}
QPushButton[variant="primary"] {{ background: {p.accent}; color: {p.on_accent}; border: 1px solid {p.accent};
                                  font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton[variant="primary"]:pressed {{ background: {p.accent_pressed}; }}
QPushButton[variant="danger"] {{ background: {p.solid_danger}; color: #FFFFFF; border: 1px solid {p.solid_danger};
                                 font-weight: 600; }}
QPushButton[variant="danger"]:hover {{ background: {p.solid_danger_hover}; border-color: {p.solid_danger_hover}; }}
QPushButton[variant="success"] {{ background: {p.solid_success}; color: #FFFFFF;
                                  border: 1px solid {p.solid_success}; font-weight: 600; }}
QPushButton[variant="success"]:hover {{ background: {p.solid_success_hover};
                                        border-color: {p.solid_success_hover}; }}
QPushButton[variant="subtle"] {{ background: {p.accent_subtle}; color: {p.accent}; border: 1px solid transparent;
                                 font-weight: 600; }}
QPushButton[variant="subtle"]:hover {{ border-color: {p.accent}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {p.text_secondary}; }}
QPushButton[variant="ghost"]:hover {{ background: {p.surface_hover}; color: {p.text}; }}
QPushButton[variant="ghost"]:disabled {{ color: {p.text_muted}; background: transparent; }}
QPushButton[variant="primary"]:disabled, QPushButton[variant="danger"]:disabled,
QPushButton[variant="success"]:disabled, QPushButton[variant="subtle"]:disabled {{
    background: {p.surface_alt}; color: {p.text_muted}; border-color: {p.border}; }}
QPushButton[segment="first"] {{ border-top-right-radius: 0; border-bottom-right-radius: 0; }}
QPushButton[segment="last"] {{ border-top-left-radius: 0; border-bottom-left-radius: 0; border-left: none; }}
QPushButton[segment="last"]:checked {{ border-left: 1px solid {p.accent}; }}
QPushButton[size="lg"] {{ min-height: 26px; padding: 9px 18px; font-size: 14px; border-radius: 10px; }}
QPushButton[size="sm"] {{ padding: 3px 10px; font-size: 12px; border-radius: 7px; }}

QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 4px;
               color: {p.text_secondary}; }}
QToolButton:hover {{ background: {p.surface_hover}; color: {p.text}; }}
QToolButton:pressed {{ background: {p.surface_pressed}; }}
QToolButton[variant="outline"] {{ border: 1px solid {p.border_strong}; padding: 5px 10px; background: {p.surface}; }}
QToolButton[variant="square"] {{ border: 1px solid {p.border_strong}; padding: 0; background: {p.surface};
    border-radius: 8px; }}
QToolButton[variant="outline"]:hover, QToolButton[variant="square"]:hover {{ border-color: {p.accent};
    background: {p.surface}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#SectionHeader {{ border: none; border-radius: 12px; padding: 12px 14px 4px 14px; text-align: left;
    font-size: 14px; font-weight: 600; color: {p.text}; background: transparent; }}
QToolButton#SectionHeader:hover {{ background: transparent; color: {p.accent}; }}

/* ---- inputs ----------------------------------------------------------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {p.surface}; color: {p.text}; border: 1px solid {p.border_strong}; border-radius: 8px;
    padding: 5px 9px; selection-background-color: {p.accent}; selection-color: {p.on_accent}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ min-height: 20px; }}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {p.text_muted}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {p.accent}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background: {p.surface_alt}; color: {p.text_muted}; border-color: {p.border}; }}
QPlainTextEdit[role="console"], QLineEdit[role="console"], QTextEdit[role="console"] {{
    font-family: "{MONO_FONT}"; font-size: 12px; }}
QPlainTextEdit[role="console"], QTextEdit[role="console"] {{ background: {p.surface_alt}; }}
QLineEdit[frame="false"] {{ border: 1px solid transparent; background: transparent; padding: 3px 4px; }}
QLineEdit[frame="false"]:hover {{ border-color: {p.border}; }}
QLineEdit[frame="false"]:focus {{ border-color: {p.accent}; background: {p.surface}; }}
QLineEdit[role="card-title"] {{ font-weight: 600; font-size: 14px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 22px; }}
QSpinBox[compact="true"], QDoubleSpinBox[compact="true"] {{ padding-right: 8px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border: none; border-top-right-radius: 8px; background: transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border: none; border-bottom-right-radius: 8px; background: transparent; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {p.surface_hover}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({up}); width: 11px; height: 11px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({down}); width: 11px; height: 11px; }}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {{ image: url({up_muted}); }}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{ image: url({down_muted}); }}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; }}
QComboBox::down-arrow {{ image: url({down}); width: 13px; height: 13px; }}
QComboBox::down-arrow:disabled {{ image: url({down_muted}); }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px;
    padding: 4px; outline: none; selection-background-color: {p.accent_subtle}; selection-color: {p.text}; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QRadioButton::indicator {{ width: 14px; height: 14px; }}   /* 18 px with the border, checked or not */
QCheckBox::indicator {{ border: 1.5px solid {p.border_strong}; border-radius: 5px; background: {p.surface}; }}
QCheckBox::indicator:hover {{ border-color: {p.accent}; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({check}); }}
QCheckBox::indicator:disabled {{ background: {p.surface_alt}; border-color: {p.border}; }}
QCheckBox::indicator:checked:disabled {{ background: {p.text_muted}; border-color: {p.text_muted}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {p.text_muted}; }}
QCheckBox[tone="warning"] {{ color: {p.warning}; }}
QRadioButton::indicator {{ border: 2px solid {p.border_strong}; border-radius: 8px; background: {p.surface}; }}
QRadioButton::indicator:hover {{ border-color: {p.accent}; }}
QRadioButton::indicator:checked {{ border: 5px solid {p.accent}; background: {p.on_accent}; width: 8px;
    height: 8px; border-radius: 9px; }}
QCheckBox[variant="eye"]::indicator {{ border: none; background: transparent; width: 18px; height: 18px;
    image: url({eye_off}); }}
QCheckBox[variant="eye"]::indicator:checked {{ image: url({eye}); }}
QRadioButton[variant="card"] {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px;
    padding-left: 14px; }}
QRadioButton[variant="card"]:hover {{ border-color: {p.border_strong}; }}
QRadioButton[variant="card"]:checked {{ background: {p.accent_subtle}; border: 1px solid {p.accent}; }}
QRadioButton[variant="card"]:disabled {{ background: {p.surface_alt}; }}

QSlider::groove:horizontal {{ height: 4px; background: {p.border}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {p.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -7px 0; border-radius: 9px;
                              background: {p.surface}; border: 2px solid {p.accent}; }}
QSlider::handle:horizontal:hover {{ background: {p.accent_subtle}; }}
QSlider::tick-mark {{ background: transparent; }}

QProgressBar {{ background: {p.border}; border: none; border-radius: 3px; max-height: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {p.accent}; border-radius: 3px; }}

/* ---- tabs -------------------------------------------------------------- */
QTabWidget::pane {{ border: none; border-top: 1px solid {p.border}; top: -1px; background: transparent; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {p.text_secondary}; padding: 8px 12px; margin-right: 2px;
                border: none; border-bottom: 2px solid transparent; font-weight: 500; }}
QTabBar::tab:hover {{ color: {p.text}; }}
QTabBar::tab:selected {{ color: {p.accent}; border-bottom: 2px solid {p.accent}; font-weight: 600; }}

/* ---- lists & tables ---------------------------------------------------- */
QListWidget, QListView, QTableWidget, QTableView, QTreeView {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; outline: none;
    gridline-color: {p.border}; alternate-background-color: {p.surface_alt}; }}
QListWidget::item, QListView::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget::item:hover, QListView::item:hover, QTableView::item:hover {{ background: {p.surface_hover}; }}
QListWidget::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {p.accent_subtle}; color: {p.text}; }}
QTableView::item {{ padding: 4px 6px; border: none; }}
QHeaderView::section {{ background: {p.surface_alt}; color: {p.text_secondary}; border: none;
    border-bottom: 1px solid {p.border}; padding: 6px 8px; font-weight: 600; font-size: 12px; }}
QTableCornerButton::section {{ background: {p.surface_alt}; border: none; }}

/* ---- scrollbars -------------------------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border_strong}; border-radius: 3px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {p.text_muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border_strong}; border-radius: 3px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ---- menus, tooltips, splitter ---------------------------------------- */
QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 7px 14px; border-radius: 6px; color: {p.text}; }}
QMenu::item:selected {{ background: {p.accent_subtle}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 6px; }}
QToolTip {{ background: {p.tooltip_bg}; color: {p.tooltip_text}; border: none; border-radius: 6px;
            padding: 6px 8px; font-size: 12px; }}
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:hover {{ background: {p.accent}; }}

/* ---- navigation sidebar ---------------------------------------------- */
QWidget#SideNavbar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
QWidget#SideNavbar QPushButton {{ background: transparent; border: none; border-radius: 9px; text-align: left;
    padding: 9px 12px; color: {p.text_secondary}; font-size: 14px; font-weight: 500; }}
QWidget#SideNavbar QPushButton:hover {{ color: {p.text}; background: {p.surface_hover}; }}
QWidget#SideNavbar QPushButton:checked {{ color: {p.text}; background: transparent; font-weight: 600; }}
QWidget#SideNavbar QPushButton:focus {{ border: none; }}
QFrame#NavIndicator {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 9px; }}
QLabel#NavbarTitleText {{ font-size: 13px; font-weight: 700; letter-spacing: 1.2px; color: {p.text}; }}
QFrame#ProfileBlock {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
QFrame#ProfileBlock:hover {{ border-color: {p.accent}; }}
QLabel#ProfileName {{ font-weight: 600; }}
QLabel#Avatar {{ background: {p.accent}; color: {p.on_accent}; border-radius: 16px; font-weight: 700; }}

/* ---- overlays on the 3-D view ----------------------------------------- */
QFrame#StatusPanel {{ background: {p.hud_bg}; border: 1px solid {p.border}; border-radius: 12px; }}
QLabel#ViewportHud {{ background: {p.hud_bg}; color: {p.text_secondary}; border: 1px solid {p.border};
    border-radius: 8px; padding: 4px 9px; font-family: "{MONO_FONT}"; font-size: 11px; }}
QLabel#GameHud {{ background: {p.hud_bg}; color: {p.text}; border: 1px solid {p.border}; border-radius: 14px;
    padding: 10px 20px; font-size: 18px; font-weight: 700; }}
QWidget#ToastFrame {{ background: {p.tooltip_bg}; border-radius: 16px; }}
QLabel#ToastText {{ color: {p.tooltip_text}; font-weight: 500; }}
QPushButton#ConsoleToggle {{ background: {p.hud_bg}; border: 1px solid {p.border}; border-radius: 15px;
    padding: 6px 12px; color: {p.text_secondary}; }}
QPushButton#ConsoleToggle:hover {{ color: {p.text}; border-color: {p.accent}; }}

/* ---- home tiles -------------------------------------------------------- */
QPushButton[variant="tile"], QPushButton[variant="tile-primary"] {{ background: {p.surface};
    border: 1px solid {p.border}; border-radius: 12px; padding: 0; text-align: left; }}
QPushButton[variant="tile"]:hover, QPushButton[variant="tile-primary"]:hover {{ border-color: {p.accent};
    background: {p.surface}; }}
QPushButton[variant="tile"]:pressed, QPushButton[variant="tile-primary"]:pressed {{ background: {p.surface_hover}; }}
QPushButton[variant="tile-primary"] {{ border-color: {p.accent}; background: {p.accent_subtle}; }}
QLabel#TileIcon {{ background: {p.accent_subtle}; border-radius: 10px; }}
QLabel#TileIconPrimary, QLabel#HomeMark {{ background: {p.accent}; border-radius: 10px; }}
QLabel#HomeMark {{ border-radius: 14px; }}
QLabel#EmptyIcon {{ background: {p.accent_subtle}; border-radius: 22px; }}
QLabel#AppMark {{ background: {p.accent}; border-radius: 9px; }}

/* ---- wizard ------------------------------------------------------------ */
QFrame#WizardHeader, QFrame#DialogHeader {{ background: {p.surface}; border: none;
    border-bottom: 1px solid {p.border}; }}
QFrame#WizardFooter, QFrame#DialogFooter {{ background: {p.surface}; border: none;
    border-top: 1px solid {p.border}; }}
QLabel[role="step"] {{ color: {p.text_muted}; font-weight: 500; font-size: 12px; }}
QLabel[role="step"][state="current"] {{ color: {p.accent}; font-weight: 700; }}
QLabel[role="step"][state="done"] {{ color: {p.text_secondary}; }}
"""


def _qpalette(p: Palette) -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.Window: p.bg, QPalette.WindowText: p.text, QPalette.Base: p.surface,
        QPalette.AlternateBase: p.surface_alt, QPalette.Text: p.text, QPalette.Button: p.surface,
        QPalette.ButtonText: p.text, QPalette.Highlight: p.accent, QPalette.HighlightedText: p.on_accent,
        QPalette.ToolTipBase: p.tooltip_bg, QPalette.ToolTipText: p.tooltip_text, QPalette.Link: p.accent,
        QPalette.PlaceholderText: p.text_muted, QPalette.Mid: p.border, QPalette.Dark: p.border_strong,
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(p.text_muted))
    return pal


_applied = None   # (app, palette) last applied, so re-applying the same theme is free


def apply(name: str = "light", app: QApplication = None):
    """Apply a theme ('light' or 'dark') to the whole application."""
    global _palette, _applied
    app = app or QApplication.instance()
    _palette = PALETTES.get(name, LIGHT)
    load_fonts()
    if app is not None and _applied != (id(app), _palette.name):
        # Each of these re-polishes every widget, so do each only when needed.
        if _applied is None or _applied[0] != id(app):
            app.setStyle(QStyleFactory.create("Fusion"))
            font = QFont(UI_FONT)
            font.setPointSizeF(10)
            app.setFont(font)
        app.setPalette(_qpalette(_palette))
        app.setStyleSheet(stylesheet(_palette))
        _applied = (id(app), _palette.name)
        _refresh_icons()
        signals.changed.emit(_palette)
    return _palette


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------

def repolish(widget: QWidget):
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_props(widget: QWidget, **props):
    for key, value in props.items():
        widget.setProperty(key, value)
    repolish(widget)
    return widget


def set_tone(label: QWidget, tone: Optional[str]):
    """Colour a label by meaning: 'success' | 'warning' | 'danger' | 'muted' | 'accent' | None."""
    if label.property("tone") != (tone or ""):
        label.setProperty("tone", tone or "")
        repolish(label)


def label(text: str = "", role: Optional[str] = None, tone: Optional[str] = None, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    if tone:
        widget.setProperty("tone", tone)
    if role == "pill":
        widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    widget.setWordWrap(wrap)
    return widget


def page_header(text: str, subtitle: str = "") -> QWidget:
    """The title block at the top of a dock panel."""
    box = QWidget()
    column = QVBoxLayout(box)
    column.setContentsMargins(2, 4, 2, 10)
    column.setSpacing(2)
    column.addWidget(label(text, "title"))
    if subtitle:
        column.addWidget(label(subtitle, "hint", wrap=True))
    return box


def title(text: str) -> QLabel:
    return label(text, "title")


def hint(text: str) -> QLabel:
    return label(text, "hint", wrap=True)


def section(text: str) -> QLabel:
    """A small upper-case heading over a group of fields."""
    widget = label(text.upper(), "section")
    font = widget.font()
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
    widget.setFont(font)
    return widget


def decorate(widget, variant: Optional[str] = None, icon_name: Optional[str] = None, size: Optional[str] = None,
             tooltip: str = ""):
    """Give an existing button a variant, size and/or icon (icon tinted to suit the variant)."""
    set_props(widget, variant=variant or "", size=size or "")
    if icon_name:
        tone = {"primary": "on_accent", "danger": "#FFFFFF", "success": "#FFFFFF",
                "subtle": "accent", "ghost": "muted"}.get(variant)
        set_icon(widget, icon_name, tone, 16)
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setCursor(Qt.PointingHandCursor)
    return widget


def button(text: str = "", variant: Optional[str] = None, icon_name: Optional[str] = None,
           size: Optional[str] = None, tooltip: str = "") -> QPushButton:
    return decorate(QPushButton(text), variant, icon_name, size, tooltip)


def tool_button(icon_name: str, tooltip: str = "", tone: Optional[str] = None, size: int = 16) -> QToolButton:
    widget = QToolButton()
    set_icon(widget, icon_name, tone, size)
    widget.setToolTip(tooltip)
    widget.setCursor(Qt.PointingHandCursor)
    widget.setAutoRaise(True)
    return widget


TONE_FOR_STATE = {"ok": "success", "warn": "warning", "bad": "danger", "off": "muted"}
ICON_FOR_STATE = {"ok": "circle-check", "warn": "triangle-alert", "bad": "circle-x", "off": "circle-dot"}
_TOKEN_FOR_STATE = {"ok": "success", "warn": "warning", "bad": "danger", "off": "text_muted"}


def state_pixmap(state: str, size: int = 16) -> QPixmap:
    """The readiness icon ('ok' | 'warn' | 'bad' | 'off') in its colour."""
    return icon(ICON_FOR_STATE.get(state, "circle-dot"), _TOKEN_FOR_STATE.get(state, "text_muted"), size).pixmap(
        size, size)


class StatusLine(QWidget):
    """An icon and a line of text showing a readiness state (re-coloured with the theme)."""

    def __init__(self, text: str = "", state: str = "off", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 18)
        self.icon_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        row.addWidget(self.icon_label, 0, Qt.AlignTop)
        self.text_label = QLabel()
        self.text_label.setWordWrap(True)
        row.addWidget(self.text_label, 1)
        self.state = None
        signals.changed.connect(self._refresh_icon)
        self.set_state(state, text)

    def set_state(self, state: str, text: str):
        self.text_label.setText(text)
        if state != self.state:
            self.state = state
            set_tone(self.text_label, {"bad": "danger", "off": "muted"}.get(state))
            self._refresh_icon()

    def _refresh_icon(self, *_):
        self.icon_label.setPixmap(state_pixmap(self.state, 16))

    def text(self) -> str:
        return self.text_label.text()
