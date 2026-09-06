"""
حوار التصدير وخيط التشغيل.

رفع الدقة والإطارات ليسا ميزة منفصلة: كلاهما معامل في أمر FFmpeg نفسه، فمكانهما
الطبيعي هنا لا في قائمة أدوات أخرى.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)

from ..core import export
from ..i18n import t
from . import theme
from .widgets import SliderField

RESOLUTIONS = [
    (None, "مقاس المشروع"),
    ((1280, 720), "720p"),
    ((1920, 1080), "1080p"),
    ((2560, 1440), "1440p"),
    ((3840, 2160), "4K"),
]

RATES = [(None, "معدّل المشروع"), (24, "24"), (30, "30"), (60, "60")]


class ExportThread(QThread):
    """يشغّل FFmpeg خارج خيط الواجهة، وإلا تجمّدت النافذة طوال الترميز."""

    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self._stop = False

    def cancel(self):
        self._stop = True
        self.job.cancel()

    def run(self):
        try:
            ok = self.job.run(on_progress=self._tick)
        except export.ExportError as exc:
            # نصوص core عربية دائمًا: core لا يعرف لغة الواجهة، فتُترجم هنا
            self.failed.emit(t(str(exc)))
            return
        except Exception as exc:                     # مسار نادر: خلل غير متوقّع
            self.failed.emit(repr(exc))
            return
        if ok:
            self.done.emit(self.job.output)

    def _tick(self, done, total):
        self.progress.emit(done, total)
        return not self._stop


class ExportDialog(QDialog):
    """خيارات التصدير. لا يشغّل شيئًا بنفسه، يبني الإعدادات فقط."""

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle(t("تصدير الفيديو"))
        self.setMinimumWidth(460)

        column = QVBoxLayout(self)
        column.setContentsMargins(18, 16, 18, 14)
        column.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        row = QHBoxLayout()
        self.path = QLineEdit(self._suggested())
        self.path.setLayoutDirection(Qt.LeftToRight)
        browse = QPushButton(t("تصفّح…"))
        browse.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        form.addRow(t("الملف الناتج"), row)

        self.resolution = QComboBox()
        for value, label in RESOLUTIONS:
            self.resolution.addItem(
                label if value else t(label), value)
        form.addRow(t("الدقة"), self.resolution)

        self.rate = QComboBox()
        for value, label in RATES:
            self.rate.addItem(label if value else t(label), value)
        self.rate.currentIndexChanged.connect(self._refresh_hint)
        form.addRow(t("معدّل الإطارات"), self.rate)

        self.encoder = QComboBox()
        for name, label in export.encoders():
            self.encoder.addItem("%s — %s" % (label, name), name)
        form.addRow(t("المرمّز"), self.encoder)

        column.addLayout(form)

        self.quality = SliderField(t("الجودة"), 0, 100, 70, "")
        column.addWidget(self.quality)

        self.interpolate = QCheckBox(t("توليد إطارات بينيّة (أنعم حركة)"))
        self.interpolate.stateChanged.connect(self._refresh_hint)
        column.addWidget(self.interpolate)

        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        column.addWidget(self.hint)

        buttons = QDialogButtonBox()
        buttons.addButton(t("صدّر"), QDialogButtonBox.AcceptRole)
        buttons.addButton(t("إلغاء"), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        column.addWidget(buttons)

        self._refresh_hint()

    def _suggested(self):
        base = os.path.splitext(self.project.path or "")[0] or os.path.join(
            os.path.expanduser("~"), "Videos", "wun_cut")
        return base + "_export.mp4"

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(
            self, t("حفظ الفيديو"), self.path.text(), t("فيديو MP4 (*.mp4)"))
        if path:
            self.path.setText(path)

    def _refresh_hint(self):
        """
        تحذير صريح من كلفة توليد الإطارات.

        القياس على هذا الجهاز: ٥ ثوانٍ مصدر تحتاج نحو دقيقة. من يضغط الخيار
        دون أن يعرف يظنّ البرنامج معلّقًا.
        """
        seconds = self.project.seconds(self.project.duration)
        if self.interpolate.isChecked():
            self.hint.setText(
                t("توليد الإطارات بطيء جدًا: نحو %d دقيقة لهذا المشروع. "
                  "يعمل في الخلفية ويمكن إلغاؤه في أي لحظة.")
                % max(1, round(seconds * 12 / 60)))
            self.hint.setStyleSheet("color: %s;" % theme.WARN)
        else:
            self.hint.setText(t("المدّة %s · التصدير أسرع من الزمن الحقيقي "
                                "على كرت الشاشة.")
                              % self.project.timecode(self.project.duration))
            self.hint.setStyleSheet("color: %s;" % theme.TXT_MUTE)

    def settings(self):
        return {
            "output": self.path.text().strip(),
            "scale": self.resolution.currentData(),
            "fps": self.rate.currentData(),
            "encoder": self.encoder.currentData() or "libx264",
            "quality": self.quality.value(),
            "interpolate": self.interpolate.isChecked(),
        }
