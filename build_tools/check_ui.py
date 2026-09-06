# -*- coding: utf-8 -*-
"""
فحص الواجهة: لا نصّ مقتطع، والتأثيرات تصل من اللوحة إلى أمر التصدير.

اقتطاع النصّ العربي في الأزرار تكرّر مرّتين، فصار له فحص بدل النظر في اللقطات:
كل زرّ عرضه أقلّ من مقاسه المقترح يعني حروفًا مبتورة على الشاشة.
"""
import atexit
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtCore import Qt                              # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel,       # noqa: E402
                               QPushButton, QScrollArea, QWidget)

from wun_cut import i18n                                   # noqa: E402
from wun_cut.core import export                          # noqa: E402
from wun_cut.gui import theme                              # noqa: E402
from wun_cut.gui.export_dialog import ExportDialog         # noqa: E402
from wun_cut.gui.main_window import MainWindow             # noqa: E402

SAMPLE = sys.argv[1] if len(sys.argv) > 1 else None

# الفحص يبدّل اللغة، وهي محفوظة في إعدادات المستخدم: نعيدها كما كانت
i18n.load()
ORIGINAL = i18n.language()
atexit.register(lambda: i18n.set_language(ORIGINAL))


def build(language):
    i18n.set_language(language)
    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    theme.apply_palette(app)
    app.setFont(theme.font(10))
    app.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
    app.setStyleSheet(theme.qss())
    window = MainWindow()
    window.resize(1500, 900)
    window.show()
    app.processEvents()
    return app, window


def clipped(root):
    """الودجات التي لا يسع عرضُها نصَّها."""
    bad = []
    for button in root.findChildren(QPushButton):
        if not button.text() or button.isHidden():
            continue
        need = button.sizeHint().width()
        if button.width() < need:
            bad.append("%s: عرض %d < مطلوب %d  «%s»"
                       % (button.objectName() or "QPushButton",
                          button.width(), need, button.text()))
    for label in root.findChildren(QLabel):
        text = label.text()
        if not text or label.isHidden() or label.wordWrap():
            continue
        need = label.fontMetrics().horizontalAdvance(text)
        if label.width() < need - 1:
            bad.append("%s: عرض %d < مطلوب %d  «%s»"
                       % (label.objectName() or "QLabel", label.width(),
                          need, text[:40]))
    return bad


app, window = build("ar")

# --- كل النصوص تسع في مواضعها، بالعربية ثم بالإنجليزية ---
for language in ("ar", "en"):
    if language != "ar":
        # الإغلاق يسأل عن الحفظ بحوار مانع: الفحص بلا مستخدم يضغط، فيتجمّد
        window._quitting = True
        window.close()
        app, window = build(language)
    if SAMPLE:
        window.open_paths([SAMPLE])
        window.timeline.select(window.editor.project.track("video").clips[0].cid)
        window.timeline.clipPicked.emit(window.timeline.selected)
    app.processEvents()

    # لا عنصر مضغوط تحت أدنى مقاسه: Qt يضغط ما لا يسع بدل أن يقصّه، فتنكمش
    # القائمة إلى شريط بلا نصّ وتبدو الواجهة سليمة في القياسات الأخرى
    problems = clipped(window)
    dialog = ExportDialog(window.editor.project, window)
    dialog.resize(dialog.sizeHint())
    dialog.show()
    app.processEvents()
    problems += clipped(dialog)
    dialog.close()

    assert not problems, "نصوص مقتطعة (%s):\n  %s" % (language,
                                                      "\n  ".join(problems))
    print("%s: لا نصّ مقتطع في %d زرًّا وتسمية"
          % (language, len(window.findChildren(QPushButton))))

if not SAMPLE:
    print("\n(مرِّر ملف فيديو لفحص التأثيرات والمعاينات)")
    sys.exit(0)

# --- التأثيرات: من اللوحة إلى النموذج إلى أمر FFmpeg ---
project = window.editor.project
clip = project.track("video").clips[0]
window.timeline.select(clip.cid)
window.timeline.clipPicked.emit(clip.cid)
assert window.effects.clip is clip, "اللوحة لم تتبع التحديد"
assert not window.effects.body.isHidden(), "اللوحة بقيت في الحالة الفارغة"

depth = len(window.editor._undo)
window.effects._apply_look({"brightness": 18, "contrast": 12,
                            "saturation": 10})
assert len(window.editor._undo) - depth == 1, "النظرة الجاهزة ولّدت لقطات عدّة"
window.effects.rows["speed"].setValue(200)
window.effects.rows["volume"].setValue(40)
window.effects.rows["fade_out"].setValue(700)

live = project.find(clip.cid)
assert live.effects["brightness"] == 18 and live.speed == 2.0
print("اللوحة كتبت على النموذج:", live.effects)

args = export.build(project, "out.mp4")
graph = args[args.index("-filter_complex") + 1]
for needle in ("eq=brightness", "setpts=PTS/2", "atempo", "volume=0.4000",
               "fade=t=out", "afade=t=out"):
    assert needle in graph, "%s لم يصل إلى أمر التصدير" % needle
print("وصلت كلّها إلى أمر FFmpeg ✓")

# --- التراجع يرجع التأثيرات ويحدّث اللوحة ---
window.undo()
assert project.find(clip.cid).effect("fade_out") == 0, "التراجع لم يُلغِ التلاشي"
assert window.effects.rows["fade_out"].value() == 0, "اللوحة لم تتبع التراجع"
window.redo()
assert window.effects.rows["fade_out"].value() == 700, "الإعادة لم تصل اللوحة"
print("التراجع والإعادة يحرّكان اللوحة معهما ✓")

# --- الحركة: من القائمة إلى النموذج إلى الرسم البياني ---
assert not project.find(clip.cid).animated
box = window.effects.anims["anim_in"]
box.setCurrentIndex(box.findData("zoom_in"))
window.effects.anims["anim_out"].setCurrentIndex(
    window.effects.anims["anim_out"].findData("slide_left"))
live = project.find(clip.cid)
assert (live.anim_in, live.anim_out) == ("zoom_in", "slide_left"),     (live.anim_in, live.anim_out)
assert live.animated and live.touched

moving = export.build(project, "out.mp4")
graph = moving[moving.index("-filter_complex") + 1]
for needle in ("eval=frame", "overlay=x=", "color=c=black", "pow(1-min(t/"):
    assert needle in graph, "%s غائب عن رسم الحركة" % needle
print("الحركة تصل إلى الرسم البياني: تكبير عند الدخول وانزلاق عند الخروج ✓")

# الحركة تدخل التراجع مثل بقيّة التحرير
window.undo()
assert project.find(clip.cid).anim_out == "", "التراجع لم يُلغِ الحركة"
assert window.effects.anims["anim_out"].currentData() == "",     "اللوحة لم تتبع تراجع الحركة"
window.redo()
assert project.find(clip.cid).anim_out == "slide_left"
print("تراجع الحركة وإعادتها يحرّكان القائمة معهما ✓")

# --- اللوحة أطول من النافذة: يجب أن تمرّر لا أن تُضغط ---
# Qt يضغط ما لا يسع بدل أن يقصّه، فانكمشت قوائم الحركة إلى شريط بلا نصّ.
# الضغط نفسه لا يتكرّر خارج الشاشة - التخطيط يستقرّ هناك على غير ما يستقرّ
# عليه في نافذة حقيقية - فنفحص الآليّة المانعة لا العرَض: محتوى اللوحة داخل
# منطقة تمرير، وارتفاع القوائم مثبَّت.
window.resize(window.minimumWidth(), window.minimumHeight())
for _ in range(5):
    app.processEvents()

panel = window.effects
assert isinstance(panel.scroll, QScrollArea), "اللوحة بلا منطقة تمرير"
assert panel.scroll.widget() is panel.body, "المحتوى ليس داخل منطقة التمرير"
assert panel.scroll.widgetResizable(), "منطقة التمرير لا تمدّد المحتوى"
assert panel.body.height() >= panel.body.sizeHint().height() - 1,     ("محتوى اللوحة مضغوط: %d بدل %d"
     % (panel.body.height(), panel.body.sizeHint().height()))
for slot, box in panel.anims.items():
    assert box.minimumHeight() == box.maximumHeight() >= 28,         ("قائمة %s بلا ارتفاع مثبَّت (%d..%d) فيضغطها التخطيط"
         % (slot, box.minimumHeight(), box.maximumHeight()))
print("عند %dx%d: المحتوى %d داخل لوحة %d عبر التمرير، والقوائم مثبَّتة ✓"
      % (window.width(), window.height(), panel.body.height(),
         panel.height()))

# --- المعاينات تصل وتُقتطع لكل مقطع على حدة ---
window.timeline.previews.wait(90000)
app.processEvents()
strip = window.timeline.previews.strip(clip.source)
assert strip is not None and not strip.isNull(), "الشريط لم يصل"
assert window.timeline.previews.wave(clip.source), "الموجة لم تصل"

window.timeline.set_playhead(clip.start + clip.duration // 2)
tail = window.editor.split(clip, window.timeline.playhead)
box_head = window.timeline._source_rect(strip, clip, 0.0, 1.0)
box_tail = window.timeline._source_rect(strip, tail, 0.0, 1.0)
assert box_head.left() < box_tail.left(), "نصفا المقطع يعرضان الإطارات نفسها"
print("الشريط يقتطع لكل قصاصة موضعها: %d ثم %d"
      % (box_head.left(), box_tail.left()))

print("المصغّرة في المكتبة:",
      "موجودة" if window.bin.list.item(0).icon().availableSizes() else "غائبة")

print("\nفحص الواجهة: كل الفحوص سليمة")
