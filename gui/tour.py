"""
جولة التعريف: ظلٌّ على النافذة وفتحةٌ على العنصر المشروح.

الفتحة لا التلوين: تظليل ما عدا الهدف يوجّه العين إليه بلا أن يخفيه، فيبقى
المستخدم يرى الواجهة الحقيقية لا صورةً عنها.

تُعرض مرّة واحدة عند أول تشغيل، وتبقى متاحة من زرّ في شريط العنوان: من تخطّاها
أول مرّة يحتاجها بعد أسبوع.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from .. import i18n
from ..i18n import t
from . import theme

SEEN = "tour_seen"          # مفتاح الإعداد: هل رآها المستخدم؟
PAD = 8                     # فسحة حول الهدف داخل الفتحة
CARD_W = 330
GAP = 14                    # بين الفتحة والبطاقة


class Tour(QWidget):
    """
    طبقة فوق النافذة كلّها.

    ابنٌ للنافذة لا نافذةٌ مستقلّة: النافذة بلا إطار نظام، ونافذة ثانية فوقها
    تتخلّف عند التحريك وتظهر في شريط المهام.
    """

    finished = Signal()

    def __init__(self, host, steps, parent=None):
        super().__init__(parent or host)
        self.host = host                # ما تُقاس إليه إحداثيات الأهداف
        self.steps = [s for s in steps if s[0] is not None]
        self.index = 0
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMouseTracking(True)

        self.card = QWidget(self)
        self.card.setObjectName("TourCard")
        self.card.setFixedWidth(CARD_W)
        column = QVBoxLayout(self.card)
        column.setContentsMargins(16, 14, 16, 13)
        column.setSpacing(7)

        self.step_label = QLabel("")
        self.step_label.setObjectName("Hint")
        column.addWidget(self.step_label)

        self.title = QLabel("")
        self.title.setObjectName("TourTitle")
        self.title.setWordWrap(True)
        column.addWidget(self.title)

        self.body = QLabel("")
        self.body.setObjectName("TourBody")
        self.body.setWordWrap(True)
        column.addWidget(self.body)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_skip = QPushButton(t("تخطّي"))
        self.btn_skip.setProperty("kind", "ghost")
        self.btn_back = QPushButton(t("السابق"))
        self.btn_next = QPushButton(t("التالي"))
        self.btn_next.setProperty("kind", "primary")
        for button in (self.btn_skip, self.btn_back, self.btn_next):
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(30)
            button.setFocusPolicy(Qt.NoFocus)
        self.btn_skip.clicked.connect(self.stop)
        self.btn_back.clicked.connect(self.back)
        self.btn_next.clicked.connect(self.next)
        row.addWidget(self.btn_skip)
        row.addStretch(1)
        row.addWidget(self.btn_back)
        row.addWidget(self.btn_next)
        column.addLayout(row)

        self.hide()

    # --------------------------------------------------------------- التشغيل

    def start(self):
        if not self.steps:
            return False
        self.index = 0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._sync()
        return True

    def stop(self):
        i18n.put(SEEN, True)
        self.hide()
        self.finished.emit()

    def next(self):
        if self.index >= len(self.steps) - 1:
            self.stop()
            return
        self.index += 1
        self._sync()

    def back(self):
        if self.index > 0:
            self.index -= 1
            self._sync()

    # ---------------------------------------------------------------- الموضع

    def target_rect(self):
        """
        مستطيل الهدف بإحداثيات هذه الطبقة، أو مستطيل فارغ إن اختفى.

        يُقصّ عند حدود الطبقة: عنصر ملاصق للحافة تدفعه الفسحة خارجها، فيُرسم
        إطار التمييز مقطوعًا وتُحسب البطاقة على مساحة غير موجودة.
        """
        widget = self.steps[self.index][0]
        if widget is None or not widget.isVisible():
            return QRect()
        # عبر الإحداثيات العامّة: mapTo تشترط أن يكون الهدف سلفًا للعنصر،
        # وهذه الطبقة ليست سلفًا لما تشرحه بل شقيقةٌ له داخل body. تمريرها
        # إلى mapTo يجعلها تمشي حتى النافذة العليا فتزيد إزاحة الظلّ وشريط
        # العنوان على كل فتحة - ٥٣ بكسل رأسيًّا هنا - فتقع دائرة الضوء بجانب
        # ما تشرحه لا عليه.
        top_left = self.mapFromGlobal(widget.mapToGlobal(QPoint(0, 0)))
        box = QRect(top_left, widget.size()).adjusted(-PAD, -PAD, PAD, PAD)
        return box.intersected(self.rect().adjusted(1, 1, -1, -1))

    def _place_card(self, hole):
        """أسفل الهدف إن اتّسع المكان، وإلا فوقه، ثم يُقصر داخل الطبقة."""
        # التخطيط يُفعَّل قبل القياس: النصّ ملفوف على عرض ثابت، وقياسه قبل أن
        # يحسب التخطيط ارتفاعه يعطي بطاقةً أقصر مما ستكون فتُقصّ من أعلاها
        self.card.layout().activate()
        self.card.resize(CARD_W, self.card.sizeHint().height())
        size = self.card.size()
        if hole.isNull():
            self.card.move((self.width() - size.width()) // 2,
                           (self.height() - size.height()) // 2)
            return

        x = hole.center().x() - size.width() // 2
        y = hole.bottom() + GAP
        if y + size.height() > self.height() - 8:
            y = hole.top() - GAP - size.height()
        x = max(10, min(x, self.width() - size.width() - 10))
        y = max(10, min(y, self.height() - size.height() - 10))
        self.card.move(x, y)

    def _sync(self):
        _widget, title, body = self.steps[self.index]
        self.step_label.setText("%d / %d" % (self.index + 1, len(self.steps)))
        self.title.setText(title)
        self.body.setText(body)
        self.btn_back.setEnabled(self.index > 0)
        self.btn_next.setText(t("تمّ") if self.index == len(self.steps) - 1
                              else t("التالي"))
        self._place_card(self.target_rect())
        self.update()

    # ----------------------------------------------------------------- الرسم

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        scrim = QPainterPath()
        scrim.addRect(self.rect())
        hole = self.target_rect()
        if not hole.isNull():
            cut = QPainterPath()
            cut.addRoundedRect(hole, 10, 10)
            # الفرق لا التراكب: OddEvenFill يترك ثقبًا نظيفًا بلا حيل تركيب
            scrim = scrim.subtracted(cut)
        p.fillPath(scrim, QColor(4, 7, 12, 205))

        if not hole.isNull():
            p.setPen(QPen(theme.color("ACCENT"), 2))
            p.drawRoundedRect(hole, 10, 10)
        p.end()

    def resizeEvent(self, _event):
        self._place_card(self.target_rect())

    # الطبقة تبتلع الأحداث: نقرةٌ تنفذ إلى ما تحتها تُربك الشرح
    def mousePressEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.stop()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Right):
            self.next()
        elif event.key() == Qt.Key_Left:
            self.back()
        else:
            super().keyPressEvent(event)


def steps_for(window):
    """خطوات الجولة على نافذة Wun Cut. تُقرأ من أعلى الشاشة إلى أسفلها."""
    return [
        (window.bin,
         t("مكتبة الوسائط"),
         t("استورد هنا كل ما ستستعمله: فيديو أو صوت أو صورة. النقر مرّتين "
           "على ملف يضعه في نهاية الخط الزمني.")),
        (window.preview_host,
         t("المعاينة"),
         t("تعرض ما عند رأس التشغيل. مسافة للتشغيل والإيقاف، والساعة تحتها "
           "تبيّن موضعك من مدّة المشروع.")),
        (window.timeline,
         t("الخط الزمني"),
         t("قلب البرنامج. اسحب المقطع لتحريكه، واسحب حافّته لقصّه، و S "
           "تقسمه عند رأس التشغيل. الصور والموجة تحتها تريك أين تقصّ بلا "
           "تشغيل.")),
        (window.effects,
         t("التأثيرات"),
         t("انقر مقطعًا فتفتح خصائصه: الألوان والسرعة والصوت والتلاشي، أو "
           "نظرة جاهزة بنقرة. المقطع المعدَّل تظهر عليه نقطة برتقالية.")),
        (window.btn_export,
         t("التصدير"),
         t("يجمع الخط الزمني في ملف واحد بكرت الشاشة. من هنا أيضًا ترفع "
           "الدقة إلى 4K وتزيد معدّل الإطارات.")),
        (window.btn_undo,
         t("تراجع بلا خوف"),
         t("كل تعديل يُسجَّل: Ctrl+Z يرجع خطوة وCtrl+Y يعيدها. جرّب بحرّية، "
           "لا شيء يضيع.")),
    ]


def demo():
    """فحص ذاتي: التنقّل والحدود والموضع."""
    import os
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtWidgets import QApplication, QLabel as QL

    app = QApplication.instance() or QApplication([])
    # الفحص يكتب في إعدادات المستخدم الحقيقية: نعيدها كما كانت
    import atexit
    was_seen = i18n.get(SEEN)
    atexit.register(lambda: i18n.put(SEEN, was_seen))

    host = QWidget()
    host.resize(900, 600)
    marks = [QL("a", host), QL("b", host), QL("c", host)]
    for index, mark in enumerate(marks):
        mark.setGeometry(60 + index * 250, 80 + index * 160, 180, 90)
    host.show()

    tour = Tour(host, [(m, "عنوان %d" % i, "شرح %d" % i)
                       for i, m in enumerate(marks)])
    ended = []
    tour.finished.connect(lambda: ended.append(True))

    assert tour.start(), "الجولة لم تبدأ"
    assert tour.index == 0 and not tour.btn_back.isEnabled()
    assert tour.btn_next.text() != t("تمّ")

    tour.back()
    assert tour.index == 0, "السابق تجاوز أول خطوة"

    first = QRect(tour.target_rect())
    tour.next()
    assert tour.index == 1 and tour.btn_back.isEnabled()
    assert tour.target_rect() != first, "الفتحة لم تتحرّك مع الخطوة"

    tour.next()
    assert tour.index == 2, tour.index
    assert tour.btn_next.text() == t("تمّ"), "آخر خطوة لم تُعلَن"

    # البطاقة تبقى داخل الطبقة مهما كان موضع الهدف
    for _ in range(3):
        card = tour.card.geometry()
        assert tour.rect().contains(card), (card, tour.rect())
        tour.index = (tour.index + 1) % 3
        tour._sync()

    tour.index = 2
    tour.next()
    assert ended and tour.isHidden(), "تمّ لم تُنهِ الجولة"
    assert i18n.get(SEEN) is True, "لم تُسجَّل كمرئيّة"

    # هدف مخفيّ لا يكسر الرسم
    marks[0].hide()
    tour.index = 0
    assert tour.target_rect().isNull()
    tour._sync()
    print("gui/tour: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
