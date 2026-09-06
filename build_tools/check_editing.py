# -*- coding: utf-8 -*-
"""
فحص تكامل للمرحلة ٢: يقود النافذة عبر إشاراتها كما تفعل الفأرة.

بلا نقر حقيقي: أتمتة الفأرة هشّة على ويندوز، وإشارات الودجت هي نفس المدخل
الذي تستعمله. ما يُختبر هنا هو الربط بين الخط الزمني والمحرّك.
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import QApplication            # noqa: E402

from wun_cut.core import media                        # noqa: E402
from wun_cut.core.project import Clip                 # noqa: E402
from wun_cut.gui import theme                         # noqa: E402
from wun_cut.gui.main_window import MainWindow        # noqa: E402

SAMPLE = sys.argv[1] if len(sys.argv) > 1 else None

app = QApplication([])
theme.load_fonts()
app.setStyleSheet(theme.qss())
window = MainWindow()
editor = window.editor
project = editor.project
line = window.timeline

if SAMPLE:
    window.add_to_timeline(media.probe(SAMPLE))
else:
    editor.append("video", Clip("a.mp4", 0, 300, name="a.mp4"))
    line.set_project(project)

def clips():
    """يُقرأ المسار من جديد دائمًا: التراجع يستبدل أجسام المسارات."""
    return project.track("video").clips


clip = clips()[0]
print("مقطع: %s  %d..%d" % (clip.name, clip.start, clip.end))

# --- سحبة كاملة = لقطة تراجع واحدة ---
depth = len(editor._undo)
line.select(clip.cid)
line.dragBegan.emit()
for frame in range(0, 120, 4):
    line.clipMoved.emit(clip.cid, frame)
line.dragEnded.emit()
moved = project.find(clip.cid)
print("بعد السحب: البداية %d | لقطات جديدة %d"
      % (moved.start, len(editor._undo) - depth))
assert len(editor._undo) - depth == 1, "السحب ولّد أكثر من لقطة تراجع"
assert moved.start > 0

editor.undo()
assert project.find(clip.cid).start == 0, "التراجع لم يرجع السحب"
print("التراجع أعاد البداية إلى 0 ✓")

# --- القصّ من الطرفين ---
before = project.find(clip.cid).duration
line.dragBegan.emit()
line.clipTrimmed.emit(clip.cid, before - 60, False)
line.dragEnded.emit()
assert project.find(clip.cid).duration == before - 60
line.dragBegan.emit()
line.clipTrimmed.emit(clip.cid, 100, True)
line.dragEnded.emit()
trimmed = project.find(clip.cid)
assert trimmed.duration == 100 and trimmed.offset > 0
print("القصّ: مدّة %d، إزاحة داخل المصدر %d ✓"
      % (trimmed.duration, trimmed.offset))

# --- التقسيم عند رأس التشغيل ---
count = len(clips())
line.set_playhead(trimmed.start + 40)
line.select(trimmed.cid)
window.split_at_playhead()
print("بعد التقسيم: %d مقطع" % len(clips()))
assert len(clips()) == count + 1

# --- منع التداخل ---
second = clips()[1]
line.dragBegan.emit()
line.clipMoved.emit(second.cid, clips()[0].start)
line.dragEnded.emit()
a, b = sorted(clips(), key=lambda c: c.start)[:2]
assert not a.overlaps(b), "المقاطع تداخلت: %d..%d و %d..%d" % (
    a.start, a.end, b.start, b.end)
print("منع التداخل: %d..%d ثم %d..%d ✓" % (a.start, a.end, b.start, b.end))

# --- الحذف والتراجع عنه ---
target = clips()[-1]
line.select(target.cid)
window.delete_selected()
assert project.find(target.cid) is None
editor.undo()
assert project.find(target.cid) is not None, "التراجع لم يُرجع المحذوف"
print("الحذف والتراجع عنه ✓")

# --- التحديد المعلّق بعد التراجع ---
line.select(target.cid)
window.delete_selected()
window.undo()
print("التحديد بعد التراجع: %s" % (line.selected or "أُسقط"))

print("\nفحص المرحلة ٢: كل الفحوص سليمة")
