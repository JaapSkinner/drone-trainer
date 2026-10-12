"""Small, quick UI animations (Qt property animations — no timers to manage).

Keep them short (120–250 ms) and purely decorative: every function leaves the
widget in its final state even if the animation is skipped.
"""
from PyQt5.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QParallelAnimationGroup, QRect
from PyQt5.QtWidgets import QGraphicsOpacityEffect

FAST, NORMAL = 140, 220
_running = []   # keep animations alive until they finish


def _keep(animation):
    _running.append(animation)
    animation.finished.connect(lambda: _running.remove(animation) if animation in _running else None)
    animation.start()
    return animation


def fade_in(widget, duration=NORMAL, start=0.0):
    """Fade a widget in. The opacity effect is removed afterwards (effects cost repaints)."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(start)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    return _keep(anim)


def slide_fade_in(widget, dx=24, duration=NORMAL):
    """Fade a widget in while sliding it ``dx`` px into place (e.g. wizard pages)."""
    end = widget.pos()
    group = QParallelAnimationGroup(widget)
    move = QPropertyAnimation(widget, b"pos", widget)
    move.setDuration(duration)
    move.setStartValue(end + QPoint(dx, 0))
    move.setEndValue(end)
    move.setEasingCurve(QEasingCurve.OutCubic)
    group.addAnimation(move)
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    fade = QPropertyAnimation(effect, b"opacity", widget)
    fade.setDuration(duration)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    group.addAnimation(fade)
    group.finished.connect(lambda: (widget.setGraphicsEffect(None), widget.move(end)))
    return _keep(group)


def move_to(widget, rect: QRect, duration=NORMAL):
    """Animate a widget's geometry (e.g. a selection indicator sliding to a new item)."""
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.geometry())
    anim.setEndValue(rect)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    return _keep(anim)


def expand(widget, show: bool, duration=FAST):
    """Open/close a section by animating its maximum height."""
    target = widget.sizeHint().height() if show else 0
    if show:
        widget.setMaximumHeight(0)
        widget.setVisible(True)
    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.maximumHeight() if not show else 0)
    anim.setEndValue(target)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def done():
        widget.setMaximumHeight(16777215)
        widget.setVisible(show)
    anim.finished.connect(done)
    return _keep(anim)
