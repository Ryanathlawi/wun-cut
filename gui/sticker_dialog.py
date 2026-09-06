"""
مُنتقي الملصقات: شبكة يُنقر منها فيُضاف الملصق طبقةً.

الحوار لا يلمس المشروع: ينشر ما اختير، والنافذة تحوّله أمرًا على المحرّك.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QColorDialog, QDialog, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from ..i18n import t
from . import stickers, theme

CELL = 54
COLUMNS = 8


class StickerDialog(QDialog):
    """يرجع (النوع، القيمة، اللون) للملصق المختار، أو None."""

    picked = Signal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("الملصقات"))
        self.setMinimumSize(430, 520)
        self.choice = None
        self._colour = stickers.DEFAULT_COLOUR

        column = QVBoxLayout(self)
        column.setContentsMargins(16, 14, 16, 14)
        column.setSpacing(10)

        strip = QHBoxLayout()
        strip.setSpacing(6)
        caption = QLabel(t("لون الأشكال"))
        caption.setObjectName("PanelTitle")
        strip.addWidget(caption)
        self.colour = QPushButton("")
        self.colour.setFixedHeight(26)
        self.colour.setCursor(Qt.PointingHandCursor)
        self.colour.clicked.connect(self._pick_colour)
        strip.addWidget(self.colour, 1)
        column.addLayout(strip)

        body = QWidget()
        self.grid = QVBoxLayout(body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)

        self._shape_buttons = []
        self._section(t("أشكال"),
                      [("shape", key) for key in stickers.SHAPE_KEYS])
        for title, row in stickers.EMOJI:
            self._section(t(title),
                          [("emoji", glyph) for glyph in row.split()])
        self.grid.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        column.addWidget(scroll, 1)

        hint = QLabel(t("لملصق خاصّ بك، استورد صورتك واضغط «أضف كطبقة»."))
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        column.addWidget(hint)
        self._paint_colour()

    def _section(self, title, items):
        caption = QLabel(title)
        caption.setObjectName("PanelTitle")
        self.grid.addWidget(caption)

        holder = QWidget()
        cells = QGridLayout(holder)
        cells.setSpacing(4)
        cells.setContentsMargins(0, 0, 0, 0)
        for index, (kind, value) in enumerate(items):
            button = QPushButton()
            button.setProperty("kind", "ghost")
            button.setFixedSize(CELL, CELL)
            button.setIconSize(QSize(CELL - 12, CELL - 12))
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(stickers.SHAPE_LABELS.get(value, value))
            self._paint_button(button, kind, value)
            button.clicked.connect(
                lambda _=False, k=kind, v=value: self._choose(k, v))
            if kind == "shape":
                self._shape_buttons.append((button, value))
            cells.addWidget(button, index // COLUMNS, index % COLUMNS)
        self.grid.addWidget(holder)

    def _paint_button(self, button, kind, value):
        path = stickers.render(kind, value, self._colour)
        if path:
            button.setIcon(QIcon(QPixmap(path)))

    def _paint_colour(self):
        self.colour.setText(self._colour.upper())
        self.colour.setStyleSheet(
            "background:%s; color:%s; border-radius:6px; font-weight:700;"
            % (self._colour,
               "#0B1220" if QColor(self._colour).lightness() > 130
               else "#FFFFFF"))

    def _pick_colour(self):
        chosen = QColorDialog.getColor(QColor(self._colour), self,
                                       t("لون الأشكال"))
        if not chosen.isValid():
            return
        self._colour = chosen.name()
        self._paint_colour()
        for button, value in self._shape_buttons:
            self._paint_button(button, "shape", value)

    def _choose(self, kind, value):
        self.choice = (kind, value, self._colour)
        self.picked.emit(kind, value, self._colour)
        self.accept()


def demo():
    """فحص ذاتي: كل خلية تحمل أيقونة، والاختيار يرجع ثلاثيّته."""
    import os
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    dialog = StickerDialog()

    buttons = [b for b in dialog.findChildren(QPushButton)
               if b.size().width() == CELL]
    expected = len(stickers.SHAPE_KEYS) + len(stickers.all_emoji())
    assert len(buttons) == expected, "%d خلية لا %d" % (len(buttons), expected)
    blank = [b for b in buttons if b.icon().isNull()]
    assert not blank, "%d خلية بلا أيقونة" % len(blank)

    seen = []
    dialog.picked.connect(lambda k, v, c: seen.append((k, v, c)))
    dialog._choose("shape", "star")
    assert dialog.choice == ("shape", "star", stickers.DEFAULT_COLOUR)
    assert seen == [dialog.choice], seen

    dialog._colour = "#29A9E2"
    for button, value in dialog._shape_buttons[:3]:
        dialog._paint_button(button, "shape", value)
        assert not button.icon().isNull()
    print("gui/sticker_dialog: كل الفحوص سليمة (%d خلية)" % len(buttons))
    app


if __name__ == "__main__":
    demo()
