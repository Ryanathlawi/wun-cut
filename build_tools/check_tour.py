# -*- coding: utf-8 -*-
"""
فحص الجولة وتبديل اللغة.

الاثنان لا يظهران في لقطة: الجولة تعتمد على أنها لم تُعرض من قبل، وتبديل
اللغة يعتمد على أن أمر إعادة التشغيل يشتغل فعلًا لا أن يبدو صحيحًا.
"""
import atexit
import os
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtCore import QPoint, QRect, Qt              # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel,      # noqa: E402
                               QPushButton)

from wun_cut import i18n                               # noqa: E402

i18n.load()
WAS_LANG, WAS_SEEN = i18n.language(), i18n.get("tour_seen")
atexit.register(lambda: (i18n.set_language(WAS_LANG),
                         i18n.put("tour_seen", WAS_SEEN)))

from wun_cut.gui import theme                          # noqa: E402
from wun_cut.gui.main_window import MainWindow         # noqa: E402
from wun_cut.gui.tour import SEEN                      # noqa: E402

app = QApplication([])
theme.load_fonts()
theme.apply_palette(app)
app.setStyleSheet(theme.qss())

# --- أول تشغيل: تُعرض. بعده: لا تُعرض ---
i18n.put(SEEN, None)
window = MainWindow()
window.resize(1400, 860)
window.show()
app.processEvents()

assert window.show_tour(force=False), "الجولة لم تُعرض في أول تشغيل"
tour = window._tour
assert not tour.isHidden() and tour.index == 0
print("أول تشغيل: عُرضت، %d خطوات" % len(tour.steps))

# كل خطوة تشير إلى عنصر حقيقي ظاهر، وبطاقتها داخل الطبقة.
#
# الفحص على الإحداثيات العامّة لا على "داخل النافذة": إزاحةٌ مقدارها ٥٣ بكسل
# أوقعت كل فتحة بجانب هدفها ومرّت من فحصٍ يكتفي بأنها غير فارغة وداخل الحدود.
for step in range(len(tour.steps)):
    tour.index = step
    tour._sync()
    app.processEvents()
    hole = tour.target_rect()
    widget, title, body = tour.steps[step]
    assert not hole.isNull(), "الخطوة %d تشير إلى عنصر مخفيّ" % (step + 1)
    assert tour.rect().contains(hole), \
        "فتحة الخطوة %d خارج النافذة: %s" % (step + 1, hole)

    target = QRect(widget.mapToGlobal(QPoint(0, 0)), widget.size())
    lit = QRect(tour.mapToGlobal(hole.topLeft()), hole.size())
    assert target.contains(lit.center()), \
        ("فتحة الخطوة %d ليست على هدفها: الهدف %s والمضاء %s"
         % (step + 1, target, lit))
    off = max(abs(lit.center().x() - target.center().x()),
              abs(lit.center().y() - target.center().y()))
    assert off <= 3, "فتحة الخطوة %d منزاحة %d بكسل عن مركز هدفها" % (
        step + 1, off)

    assert tour.rect().contains(tour.card.geometry()), \
        "بطاقة الخطوة %d خرجت عن النافذة: %s" % (step + 1,
                                                 tour.card.geometry())
    # أبناء البطاقة داخلها فعلًا: sizeHint لا يحسب لفّ النصّ، فمقارنتها بنفسها
    # تمرّ دائمًا مهما قُصّ المحتوى
    for child in (tour.card.findChildren(QLabel)
                  + tour.card.findChildren(QPushButton)):
        assert tour.card.rect().contains(child.geometry()), \
            ("محتوى بطاقة الخطوة %d خارجها: %s «%s»"
             % (step + 1, child.geometry(), child.text()[:30]))

    assert not hole.intersects(tour.card.geometry()), \
        "بطاقة الخطوة %d تغطّي ما تشرحه" % (step + 1)

    # سطح المعاينة نافذةٌ أصليّة يرسمها النظام فوق ودجات Qt الشقيقة: ما يقع
    # تحته من البطاقة يُبتلع ولا يظهر للمستخدم أبدًا، ولا يبين في w.grab().
    if not window.video.isHidden():
        preview = QRect(window.video.mapToGlobal(QPoint(0, 0)),
                        window.video.size())
        card_global = QRect(tour.card.mapToGlobal(QPoint(0, 0)),
                            tour.card.size())
        hidden = preview.intersected(card_global)
        assert hidden.isEmpty(), \
            ("بطاقة الخطوة %d تقع تحت سطح المعاينة: %d بكسل منها لن تظهر"
             % (step + 1, hidden.height()))

    assert title and body, "الخطوة %d بلا نصّ" % (step + 1)
print("الخطوات الستّ: كلّ فتحة على مركز هدفها، والبطاقات كاملة ولا تحجبها ✓")

tour.stop()
assert i18n.get(SEEN) is True
assert not window.show_tour(force=False), "عُرضت مرّةً ثانية بعد التخطّي"
assert window.show_tour(force=True), "زرّ الجولة لم يفتحها"
window._tour.stop()
print("تُعرض مرّة واحدة تلقائيًا، وتفتح يدويًا دائمًا ✓")

# --- الترجمة: لا مفتاح ناقص ولا نصّ بقي عربيًّا في الإنجليزية ---
i18n.set_language("en")
arabic = set("ابتثجحخدذرزسشصضطظعغفقكلمنهوي")
leaked = []
for key, value in i18n.EN_MAP.items():
    if arabic & set(value):
        leaked.append(key)
assert not leaked, "ترجمات بقيت عربية: %s" % leaked[:5]
assert "&" not in "".join(i18n.EN_MAP.values()), \
    "علامة & في نصّ إنجليزي: Qt تقرأها اختصار لوحة مفاتيح فتبتلع الحرف بعدها"
print("EN_MAP: %d مفتاحًا، بلا تسرّب عربي ولا & ✓" % len(i18n.EN_MAP))

# --- إعادة التشغيل: نشغّل الأمر نفسه ونتحقّق أنّ العملية تعيش ---
# لا يكفي أن يُستورد الملف: إعادة التشغيل تفشل عند خطأ في المسار أو مجلد
# العمل، وكلاهما لا يظهر إلا بتشغيل فعليّ.
main = os.path.abspath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "main.py"))
assert os.path.exists(main), main

child = subprocess.Popen([sys.executable, main], cwd=os.path.dirname(main),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
try:
    out, err = child.communicate(timeout=12)
    raise AssertionError("العملية ماتت بعد %d: %s"
                         % (child.returncode,
                            err.decode("utf-8", "replace")[-600:]))
except subprocess.TimeoutExpired:
    pass                    # ما زالت حيّة بعد ١٢ ثانية: النافذة قامت
finally:
    child.kill()
print("إعادة التشغيل: العملية قامت وعاشت ١٢ ثانية ✓")

print("\nفحص الجولة واللغة: كل الفحوص سليمة")
