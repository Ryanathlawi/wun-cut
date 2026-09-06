"""
لوحة التأثيرات: خصائص المقطع المحدَّد.

اللوحة لا تلمس المشروع. تنشر إشارة بالاسم والقيمة، والنافذة تحوّلها أمرًا على
Editor، فيبقى التراجع في مكان واحد كبقية التحرير.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ..core import animate, filters, transitions
from . import lettering, titles
from ..core.project import EFFECTS
from ..i18n import t
from . import icons, theme
from .widgets import Divider, EmptyState, SliderField, ltr

# حدّا عرض اللوحة. هنا لا في النافذة، لأن الفحص أدناه يقيس المحتوى عليهما.
#
# الأدنى كان ٢٤٠ وهو أضيق ممّا تحتاجه اللوحة أصلًا (٢٦٧ بالإنجليزية زائد
# ٣٤ للإطار وشريط التمرير)، فكانت تُقصّ حتى لو لم يلمس المستخدم الفاصل.
MIN_WIDTH = 310
MAX_WIDTH = 360

# الاسم في النموذج، التسمية، اللاحقة
ROWS = [
    ("motion_amount", "شدّة التحريك", "٪"),
    ("tilt_amount", "شدّة الميلان", "٪"),
    ("flip_amount", "شدّة الانقلاب", "٪"),
    ("text_size", "مقاس النصّ", ""),
    ("text_outline", "حدّ النصّ", "٪"),
    ("filter_amount", "شدّة الفلتر", "٪"),
    ("trans_ms", "مدّة الانتقال", t(" م.ث")),
    ("layer_scale", "حجم الطبقة", "٪"),
    ("layer_x", "الموضع الأفقي", "٪"),
    ("layer_y", "الموضع الرأسي", "٪"),
    ("brightness", "السطوع", ""),
    ("contrast", "التباين", ""),
    ("saturation", "التشبّع", ""),
    ("speed", "السرعة", "٪"),
    ("volume", "الصوت", "٪"),
    ("fade_in", "تلاشي الدخول", t(" م.ث")),
    ("fade_out", "تلاشي الخروج", t(" م.ث")),
    ("anim_ms", "مدّة الحركة", t(" م.ث")),
]

# نظرات جاهزة: قيم الألوان الثلاث دفعةً واحدة
LOOKS = [
    ("طبيعي", {"brightness": 0, "contrast": 0, "saturation": 0}),
    ("ساطع", {"brightness": 18, "contrast": 12, "saturation": 10}),
    ("سينمائي", {"brightness": -6, "contrast": 28, "saturation": -18}),
    ("أبيض وأسود", {"brightness": 4, "contrast": 15, "saturation": -100}),
]


class _Motions:
    """واجهة الجدول نفسها التي تستعملها بقيّة القوائم، لتُبنى بحلقةٍ واحدة."""

    NAMES = animate.MOTION_NAMES
    LABELS = animate.MOTION_LABELS


class _Tilts:
    NAMES = animate.TILT_NAMES
    LABELS = animate.TILT_LABELS


class _Flips:
    NAMES = animate.FLIP_NAMES
    LABELS = animate.FLIP_LABELS


class EffectsPanel(QWidget):
    """منزلقات المقطع المحدَّد، أو حالة فارغة إن لم يُحدَّد شيء."""

    changed = Signal(str, int)      # اسم التأثير، القيمة الجديدة
    animated = Signal(str, str)     # الخانة (anim_in/out)، اسم الحركة
    # النصّ، اللون، المحاذاة، أنيميشن الحروف
    textChanged = Signal(str, str, str, str)
    began = Signal()                # بداية سحبة: لقطة تراجع واحدة
    ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.clip = None
        self._loading = False       # يمنع بثّ التغيير أثناء ملء اللوحة
        self.rows = {}

        column = QVBoxLayout(self)
        column.setContentsMargins(12, 10, 12, 12)
        column.setSpacing(9)

        head = QHBoxLayout()
        head.setSpacing(7)
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap("adjust", 15, theme.TXT_DIM))
        title = QLabel(t("التأثيرات"))
        title.setObjectName("PanelTitle")
        self.reset = QPushButton(t("تصفير"))
        self.reset.setProperty("kind", "ghost")
        self.reset.setCursor(Qt.PointingHandCursor)
        self.reset.setFixedHeight(24)
        self.reset.clicked.connect(self._reset_all)
        head.addWidget(glyph)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.reset)
        column.addLayout(head)

        self.name = QLabel("")
        self.name.setObjectName("ClipName")
        self.name.setWordWrap(True)
        column.addWidget(self.name)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(11)

        # شبكة عمودين لا صفًّا واحدًا: أربع رقاقات في صفّ داخل لوحة عرضها
        # ٢٨٠ بكسل تقتطع نصّ أطولها
        looks = QGridLayout()
        looks.setSpacing(5)
        for index, (label, values) in enumerate(LOOKS):
            button = QPushButton(t(label))
            button.setProperty("kind", "chip")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(27)
            button.clicked.connect(
                lambda _=False, v=values: self._apply_look(v))
            looks.addWidget(button, index // 2, index % 2)
        body.addLayout(looks)

        # محرّر النصّ: يظهر لمقاطع النصّ وحدها
        self.text_box = QWidget()
        text = QVBoxLayout(self.text_box)
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(6)
        caption = QLabel(t("النصّ"))
        caption.setObjectName("PanelTitle")
        text.addWidget(caption)
        self.editor_text = QPlainTextEdit()
        self.editor_text.setFixedHeight(74)
        self.editor_text.textChanged.connect(self._on_text)
        text.addWidget(self.editor_text)

        # عمودان لا ثلاثة عناصر في صفّ: أطولها «بلا أنيميشن» وحده يحتاج ١٥١
        # بكسلًا، والثلاثة معًا ٣٤٥ في لوحةٍ أقصاها MAX_WIDTH. والقصّ لا يقع
        # على الصفّ وحده: اللوحة تُمدّ محتواها كلّه إلى أعرض صفٍّ فيه، فتقطع
        # يسار كلّ صفٍّ آخر معه.
        strip = QGridLayout()
        strip.setSpacing(5)
        self.colour = QPushButton("")
        self.colour.setFixedHeight(28)
        self.colour.setCursor(Qt.PointingHandCursor)
        # #FFFFFF لا FFFFFF#: الرمز لاتينيّ فيُقرأ من اليسار كالساعة
        self.colour.setLayoutDirection(Qt.LeftToRight)
        self.colour.clicked.connect(self._pick_colour)
        self._colour = "#FFFFFF"
        strip.addWidget(self.colour, 0, 0)
        self.align = QComboBox()
        self.align.setFixedHeight(28)
        for key, label in titles.ALIGNMENTS:
            self.align.addItem(t(label), key)
        self.align.currentIndexChanged.connect(lambda _i: self._on_text())
        strip.addWidget(self.align, 0, 1)

        # أنيميشن الحروف: يُرسم النصّ مقطعًا متحرّكًا بدل صورةٍ ساكنة
        self.lettering = QComboBox()
        self.lettering.setFixedHeight(28)
        for key, label, _spec in lettering.STYLES:
            self.lettering.addItem(t(label), key)
        self.lettering.currentIndexChanged.connect(lambda _i: self._on_text())
        strip.addWidget(self.lettering, 1, 0, 1, 2)
        text.addLayout(strip)
        body.addWidget(self.text_box)

        body.addWidget(Divider())

        # الحركة: قائمتان ومدّة واحدة تشتركان فيها
        motion = QGridLayout()
        motion.setSpacing(6)
        motion.setColumnStretch(1, 1)
        self.anims = {}
        rows = (("motion", "التحريك", _Motions),
                ("tilt", "الميلان", _Tilts),
                ("flip", "الانقلاب", _Flips),
                ("filter", "الفلتر", filters),
                ("trans", "الانتقال", transitions),
                ("anim_in", "حركة الدخول", animate),
                ("anim_out", "حركة الخروج", animate))
        for row, (slot, label, source) in enumerate(rows):
            caption = QLabel(t(label))
            caption.setObjectName("PanelTitle")
            box = QComboBox()
            box.setFixedHeight(30)     # وإلا ضغطه التخطيط
            box.setCursor(Qt.PointingHandCursor)
            for key in source.NAMES:
                box.addItem(t(source.LABELS[key]), key)
            box.currentIndexChanged.connect(
                lambda _index, key=slot: self._on_anim(key))
            self.anims[slot] = box
            motion.addWidget(caption, row, 0)
            motion.addWidget(box, row, 1)
        body.addLayout(motion)

        for name, label, suffix in ROWS:
            low, high, neutral = EFFECTS[name]
            row = SliderField(t(label), low, high, neutral, suffix)
            row.slider.sliderPressed.connect(self.began.emit)
            row.slider.sliderReleased.connect(self.ended.emit)
            row.valueChanged.connect(
                lambda value, key=name: self._on_change(key, value))
            self.rows[name] = row
            body.addWidget(row)

        body.addStretch(1)

        # اللوحة صارت أطول من الشاشة على النوافذ القصيرة، وQt يضغط ما لا يسع
        # بدل أن يقصّه: القوائم تنكمش إلى شريط بلا نصّ. التمرير يحفظ لكل عنصر
        # مقاسه ويترك للمستخدم الوصول إلى ما تحت.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.body)
        column.addWidget(self.scroll, 1)

        self.empty = EmptyState("select", t("لم يُحدَّد مقطع"),
                                t("انقر مقطعًا على الخط الزمني لتعديل ألوانه "
                                  "وسرعته وصوته."))
        column.addWidget(self.empty, 1)
        self.set_clip(None)

    # ---------------------------------------------------------------- العرض

    def set_clip(self, clip):
        """يملأ اللوحة من المقطع. الملء لا يُحسب تعديلًا."""
        self.clip = clip
        self.scroll.setVisible(clip is not None)
        self.body.setVisible(clip is not None)
        self.empty.setVisible(clip is None)
        self.reset.setEnabled(clip is not None and clip.touched)
        if clip is None:
            self.name.setText("")
            return

        self.name.setText(ltr(clip.name))
        self._loading = True
        self.text_box.setVisible(clip.is_text)
        for name in ("text_size", "text_outline"):
            self.rows[name].setVisible(clip.is_text)
        if clip.is_text:
            if self.editor_text.toPlainText() != clip.text:
                self.editor_text.setPlainText(clip.text)
            self._colour = clip.text_colour
            self._paint_colour()
            self.align.setCurrentIndex(
                max(0, self.align.findData(clip.text_align)))
            self.lettering.setCurrentIndex(
                max(0, self.lettering.findData(clip.text_anim)))
        for name, row in self.rows.items():
            row.setValue(clip.effect(name))
        for slot, box in self.anims.items():
            box.setCurrentIndex(max(0, box.findData(getattr(clip, slot, ""))))
        self._loading = False

    def refresh(self):
        """بعد تراجع أو إعادة: القيم تغيّرت خارج اللوحة."""
        self.set_clip(self.clip)

    # -------------------------------------------------------------- التعديل

    def _on_change(self, name, value):
        if self._loading or self.clip is None:
            return
        self.changed.emit(name, value)
        self.reset.setEnabled(self.clip.touched)

    def _on_text(self):
        if self._loading or self.clip is None or not self.clip.is_text:
            return
        self.textChanged.emit(self.editor_text.toPlainText(), self._colour,
                              self.align.currentData() or "center",
                              self.lettering.currentData() or "")

    def _paint_colour(self):
        self.colour.setText(self._colour.upper())
        self.colour.setStyleSheet(
            "background:%s; color:%s; border-radius:6px; font-weight:700;"
            % (self._colour,
               "#0B1220" if QColor(self._colour).lightness() > 130
               else "#FFFFFF"))

    def _pick_colour(self):
        chosen = QColorDialog.getColor(QColor(self._colour), self,
                                       t("لون النصّ"))
        if not chosen.isValid():
            return
        self._colour = chosen.name()
        self._paint_colour()
        self._on_text()

    def _on_anim(self, slot):
        if self._loading or self.clip is None:
            return
        self.animated.emit(slot, self.anims[slot].currentData() or "")
        self.reset.setEnabled(self.clip.touched)

    def _apply_look(self, values):
        """نظرة جاهزة: تغييرات عدّة بلقطة تراجع واحدة."""
        if self.clip is None:
            return
        self.began.emit()
        for name, value in values.items():
            self.rows[name].setValue(value)
        self.ended.emit()

    def _reset_all(self):
        if self.clip is None:
            return
        self.began.emit()
        for slot, box in self.anims.items():
            box.setCurrentIndex(0)
        for name, row in self.rows.items():
            row.setValue(EFFECTS[name][2])
        self.ended.emit()
        self.reset.setEnabled(False)


def demo():
    """فحص ذاتي: الملء لا يبثّ تغييرًا، والتعديل يبثّ."""
    import os
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtWidgets import QApplication

    from wun_cut import i18n
    from wun_cut.core.project import Clip

    app = QApplication.instance() or QApplication([])
    # بثيم البرنامج لا بلا ثيم: حشوات QSS هي ما يوسّع القوائم والأزرار،
    # ولوحةٌ بلا ثيم تقيس ٢٠٢ بكسل حيث يرى المستخدم ٣٤٥ - فيمرّ القصّ.
    i18n.load()
    theme.load_fonts()
    theme.apply_palette(app)
    app.setStyleSheet(theme.qss())
    panel = EffectsPanel()
    seen = []
    panel.changed.connect(lambda name, value: seen.append((name, value)))

    # isVisible تتبع سلسلة الآباء، والنافذة غير معروضة في الفحص
    assert not panel.empty.isHidden() and panel.body.isHidden()

    clip = Clip("a.mp4", 0, 100)
    clip.set_effect("contrast", 30)
    panel.set_clip(clip)
    assert not panel.body.isHidden() and panel.empty.isHidden()
    assert panel.rows["contrast"].value() == 30, "اللوحة لم تُملأ من المقطع"
    assert not seen, "الملء بثّ تغييرًا: %s" % seen

    panel.rows["speed"].setValue(150)
    assert seen == [("speed", 150)], seen

    seen.clear()
    panel._apply_look(dict(LOOKS[3][1]))
    names = {n for n, _ in seen}
    assert names == {"brightness", "contrast", "saturation"}, names
    assert dict(seen)["saturation"] == -100

    panel.set_clip(None)
    assert not panel.empty.isHidden() and not panel.reset.isEnabled()

    # --- لا يُقصّ شيءٌ داخل أقصى عرضٍ تعطيه النافذة ---
    #
    # الشريط الأفقيّ مطفأ عمدًا، فحين يحتاج صفٌّ أكثر ممّا يسع تمدّ اللوحة
    # محتواها كلّه إلى مقاسه وتقصّ الفائض من اليسار: صفٌّ واحدٌ عريض يقطع
    # يسار كلّ الصفوف، بلا خطأ ولا شريط. ومقطع النصّ هو الحالة الأعرض.
    # ويُقاس عند الأدنى لا الأقصى: هناك يضع المستخدمُ الفاصلَ. وباللغتين،
    # لأن الإنجليزية هنا أعرض من العربية.
    wide = Clip("a.mp4", 0, 100)
    wide.text = "نصّ"
    for lang in ("ar", "en"):
        i18n.set_language(lang)
        narrow = EffectsPanel()
        narrow.set_clip(wide)
        narrow.show()
        narrow.resize(MIN_WIDTH, 900)
        app.processEvents()
        need = narrow.body.minimumSizeHint().width()
        have = narrow.scroll.viewport().width()
        assert need <= have, (
            "%s: يُقصّ %d بكسل عند عرض %d - المحتوى %d والمتاح %d"
            % (lang, need - have, MIN_WIDTH, need, have))
        print("العرض (%s): المحتوى %d داخل %d المتاحة ✓" % (lang, need, have))
        narrow.hide()
    i18n.set_language("ar")

    # رمز اللون لاتينيّ: يُقرأ #FFFFFF لا FFFFFF#
    assert panel.colour.layoutDirection() == Qt.LeftToRight

    print("gui/effects: كل الفحوص سليمة")
    app  # يبقى حيًّا حتى نهاية الفحص


if __name__ == "__main__":
    demo()
