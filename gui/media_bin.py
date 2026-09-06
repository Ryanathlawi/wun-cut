"""
مكتبة الوسائط: الملفات المستوردة قبل وضعها على الخط الزمني.

المصغّرة مقتطعة من أوّل شريط الإطارات نفسه الذي يرسمه الخط الزمني، لا من
استدعاء ffmpeg ثانٍ: الملف يُقرأ مرّة واحدة ويستفيد الاثنان.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QVBoxLayout, QWidget)

from ..core import media
from ..i18n import t
from . import icons, theme
from .widgets import EmptyState, ltr

MEDIA_ROLE = Qt.UserRole + 1
THUMB = QSize(72, 42)


def _placeholder(name):
    """مربّع بأيقونة نوع الملف: يُعرض حتى تصل المصغّرة الحقيقية."""
    pixmap = QPixmap(THUMB)
    pixmap.fill(QColor(theme.BG_CANVAS))
    p = QPainter(pixmap)
    glyph = icons.pixmap(name, 18, theme.TXT_MUTE)
    p.drawPixmap((THUMB.width() - glyph.width()) // 2,
                 (THUMB.height() - glyph.height()) // 2, glyph)
    p.end()
    return pixmap


class MediaBin(QWidget):
    """الملفات المستوردة. مصدرها منفصل عن الخط الزمني: استيراد ثم إضافة."""

    addRequested = Signal(object)       # MediaInfo

    def __init__(self, previews=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.items: list[media.MediaInfo] = []
        self.previews = previews
        if previews is not None:
            previews.ready.connect(self._on_preview)

        column = QVBoxLayout(self)
        column.setContentsMargins(12, 10, 12, 12)
        column.setSpacing(9)

        head = QHBoxLayout()
        head.setSpacing(7)
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap("import", 15, theme.TXT_DIM))
        title = QLabel(t("الوسائط"))
        title.setObjectName("PanelTitle")
        self.count = QLabel("")
        self.count.setObjectName("Hint")
        head.addWidget(glyph)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.count)
        column.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("MediaList")
        self.list.setSpacing(3)
        self.list.setIconSize(THUMB)
        self.list.setUniformItemSizes(True)
        self.list.itemDoubleClicked.connect(self._on_double)
        column.addWidget(self.list, 1)

        self.empty = EmptyState("open", t("لا توجد وسائط"),
                                t("استورد فيديو أو صوتًا أو صورة، ثم انقر "
                                  "مرّتين لإضافته إلى الخط الزمني."))
        column.addWidget(self.empty, 1)
        self.list.hide()

    # ---------------------------------------------------------------- الملء

    def add(self, info):
        if any(i.path == info.path for i in self.items):
            return
        self.items.append(info)
        item = QListWidgetItem("%s\n%s" % (ltr(info.name),
                                           ltr(info.describe())))
        item.setData(MEDIA_ROLE, info)
        item.setToolTip("%s\n%s" % (ltr(info.path), ltr(self._length(info))))
        item.setSizeHint(QSize(0, THUMB.height() + 14))
        item.setIcon(QIcon(_placeholder(
            "image" if info.has_video else "layers")))
        self.list.addItem(item)
        self.count.setText(t("%d ملف") % len(self.items))
        self.list.show()
        self.empty.hide()
        if self.previews is not None and info.has_video:
            self.previews.request(info.path)

    @staticmethod
    def _length(info):
        minutes, seconds = divmod(int(info.duration), 60)
        return "%d:%02d" % (minutes, seconds)

    def _on_preview(self, source):
        """
        وصل شريط ملف: إطار من وسطه يصير مصغّرته.

        لا أوّل إطار: المقاطع تبدأ سوداء أو بشاشة عنوان في الغالب، فتخرج
        المكتبة صفًّا من المربّعات السوداء المتشابهة.
        """
        strip = self.previews.strip(source) if self.previews else None
        if strip is None or strip.isNull():
            return
        tile_w = min(strip.height() * 16 // 9, strip.width())
        left = max(0, (strip.width() - tile_w) // 2)
        tile = strip.copy(left, 0, tile_w, strip.height())
        icon = QIcon(tile.scaled(THUMB, Qt.KeepAspectRatioByExpanding,
                                 Qt.SmoothTransformation))
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(MEDIA_ROLE).path == source:
                item.setIcon(icon)
                return

    def current(self):
        item = self.list.currentItem()
        return item.data(MEDIA_ROLE) if item else None

    def _on_double(self, item):
        self.addRequested.emit(item.data(MEDIA_ROLE))
