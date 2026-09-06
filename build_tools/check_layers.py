# -*- coding: utf-8 -*-
"""
فحص الطبقات: صورة فوق الفيديو، بموضعها وحجمها وحركتها، حتى الملف الناتج.

المسار كامل: زرّ «أضف كطبقة» -> النموذج -> رسم FFmpeg -> تصدير حقيقي نتحقّق
من إطاراته. الفحص على الأمر وحده لا يكفي: رسمًا بيانيًّا يبدو سليمًا قد يرفضه
FFmpeg أو يخرج صورةً في غير موضعها.
"""
import os
import subprocess
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtCore import Qt                              # noqa: E402
from PySide6.QtWidgets import QApplication                 # noqa: E402

from wun_cut import i18n                                   # noqa: E402
from wun_cut.core import export, media                     # noqa: E402
from wun_cut.core.project import Clip                      # noqa: E402
from wun_cut.gui import theme                              # noqa: E402
from wun_cut.gui.main_window import MainWindow             # noqa: E402

VIDEO, IMAGE = sys.argv[1], sys.argv[2]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

i18n.load()
app = QApplication([])
theme.load_fonts()
theme.apply_palette(app)
app.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
app.setStyleSheet(theme.qss())

window = MainWindow()
window.resize(1500, 900)
window.show()
app.processEvents()

# --- الملء ينزّل التكبير على العرض الحقيقي لا على تخطيطٍ لم يستقرّ ---
window.open_paths([VIDEO])
project = window.editor.project
base = project.track("video").clips[0]
window.editor.trim(base, project.frames(8))
window.timeline.fit()
app.processEvents()
span = window.timeline.ppf * project.duration
assert span > (window.timeline.width() - 200) * 0.5, \
    ("الملء ترك المقطع في %d بكسل من %d متاحة"
     % (span, window.timeline.width()))
print("الملء: المقطع يشغل %d بكسل من %d ✓" % (span, window.timeline.width()))

# --- إضافة صورة كطبقة ---
window.bin.add(media.probe(IMAGE))
window.bin.list.setCurrentRow(window.bin.list.count() - 1)
window.timeline.set_playhead(project.frames(1))
before = len(project.layers)
window.add_as_layer()
assert len(project.layers) == before + 1, "لم تُنشأ طبقة"

layer = project.layers[0]
shot = layer.clips[0]
assert shot.start == project.frames(1), (shot.start, project.frames(1))
assert project.tracks.index(layer) == 0, "الطبقة الجديدة ليست في الأعلى"
print("الطبقة: %s · مقطع عند %d · مسارات %d"
      % (layer.name, shot.start, len(project.tracks)))

# --- موضعها وحجمها وحركتها ---
window.timeline.select(shot.cid)
window.timeline.clipPicked.emit(shot.cid)
assert window.effects.clip is shot
for name, value in (("layer_scale", 30), ("layer_x", 30), ("layer_y", -25)):
    window.effects.rows[name].setValue(value)
box = window.effects.anims["anim_in"]
box.setCurrentIndex(box.findData("zoom_in"))

live = project.find(shot.cid)
assert live.effect("layer_scale") == 30 and live.effect("layer_x") == 30
assert live.anim_in == "zoom_in"
print("خصائص الطبقة:", live.effects, "|", live.anim_in)

# --- الرسم البياني ---
args = export.build(project, "out.mp4")
graph = args[args.index("-filter_complex") + 1]
assert "-loop" in args, "الصورة أُدخلت بلا حلقة فتعطي إطارًا واحدًا"
assert "enable='between(t," in graph, "الطبقة بلا نافذة زمنية"
assert "format=yuva420p" in graph, "الشفافية غير مثبَّتة"
assert graph.count("overlay=") >= 1
print("الرسم البياني: حلقة الصورة ونافذتها وشفافيّتها ✓")

# --- قائمة النقر الأيمن تنفَّذ فعلًا ---
depth = len(window.editor._undo)
window._on_menu(("clip", "duplicate", shot.cid), shot.end)
assert len(layer.clips) == 2, "التكرار لم يضف مقطعًا"
window._on_menu(("clip", "copy_fx", shot.cid), 0)
plain = layer.clips[1]
window._on_menu(("clip", "paste_fx", plain.cid), 0)
assert project.find(plain.cid).effect("layer_scale") == 30, \
    "لصق التأثيرات لم يصل"
window._on_menu(("track", "visible", layer), 0)
assert not layer.visible, "إخفاء الطبقة لم يعمل"
window._on_menu(("track", "visible", layer), 0)
assert len(window.editor._undo) > depth, "أوامر القائمة لا تدخل التراجع"
print("القائمة: تكرار، نسخ ولصق التأثيرات، إظهار وإخفاء ✓")

# الطبقة المخفيّة تختفي من الرسم البياني
window._on_menu(("track", "visible", layer), 0)
hidden = export.build(project, "out.mp4")
assert "enable='between(t," not in hidden[hidden.index("-filter_complex") + 1], \
    "الطبقة المخفيّة ما زالت تُركَّب"
window._on_menu(("track", "visible", layer), 0)
print("الطبقة المخفيّة لا تدخل التصدير ✓")

# الأساس لا يُحذف
window._on_menu(("track", "remove_layer", project.track("video")), 0)
assert project.track("video") is not None, "حُذف المسار الأساس"
print("المسار الأساس محميّ من الحذف ✓")

# --- التشغيل: الخام فورًا، والمركّب بلوحة انتظار ظاهرة ---
# ضغطُ تشغيلٍ لا يتبعه شيء مرئيّ عشر ثوانٍ يُقرأ "البرنامج معطّل"، فالانتظار
# يجب أن يُرى في مكان المعاينة لا في سطر صغير أسفل النافذة.
assert window._plain_clip() is None, "خطٌّ فيه طبقة ظاهرة عُدّ خامًا"
window.editor.set_track_flag(layer, "visible", False)
assert window._plain_clip() is not None,     "طبقة مخفيّة ألزمت بترميز، والتشغيل سينتظر بلا داعٍ"
window.editor.set_effect(base, "brightness", 20)
assert window._plain_clip() is None, "مقطع عليه تأثير عُدّ خامًا"
window.editor.set_effect(base, "brightness", 0)
window.editor.set_track_flag(layer, "visible", True)
assert window._plain_clip() is None
print("التشغيل: يميّز الخام من المركّب، والمخفيّ لا يُلزم بترميز ✓")

# --- حركة الطبقة تمشي على ساعة المقطع لا على ساعة الخط الزمني ---
#
# إزاحات الطبقات تُحسب داخل overlay، و`t` هناك زمن الخط الزمني. طبقةٌ تبدأ
# عند الثانية ١١ كانت حركةُ خروجها ترى أن عمرها انقضى، فتدفعها ١٩٢٠ بكسل
# خارج اللوحة من أوّل إطار: الملصق يختفي تمامًا والأمر يبدو سليمًا.
import re                                                   # noqa: E402
late = window.editor.add_layer("متأخّرة")
mark = Clip(IMAGE, 0, project.frames(2.2), name="علامة")
mark.set_effect("layer_scale", 20)
mark.anim_in, mark.anim_out = "slide_right", "slide_left"
mark.set_effect("anim_ms", 700)
window.editor.append(late, mark)
window.editor.move(mark, project.frames(11.4))

args = export.build(project, "out.mp4", scale=(1920, 1080))
graph = args[args.index("-filter_complex") + 1]
found = [part for part in graph.split(";")
         if "enable='between(t,11.4" in part]
assert found, "طبقة متأخّرة بلا نافذة زمنية"


def at(expr, moment):
    """
    يحسب تعبير FFmpeg عند لحظة.

    أسماء متغيّرات المرشّحات (W وH وw وh وt) صالحة أسماءَ بايثون، فتُمرَّر
    نطاقًا بدل استبدالها في النصّ: الاستبدال يصيب `w` داخل `pow` ويكسر كلّ شيء.
    """
    return eval(expr, {"pow": pow, "min": min, "max": max},
                {"W": 1920.0, "H": 1080.0, "w": 384.0, "h": 384.0,
                 "t": float(moment)})


horizontal = re.search(r"x='([^']+)'", found[0]).group(1)
middle = at(horizontal, 12.5)          # منتصف عمر الطبقة
assert -200 < middle < 1900,     ("الطبقة المتأخّرة خارج اللوحة في منتصف عمرها: x=%.0f" % middle)
assert at(horizontal, 11.45) > middle, "لم تدخل من اليمين"
assert at(horizontal, 13.55) < middle, "لم تخرج إلى اليسار"
print("حركة الطبقة على ساعة المقطع: تدخل %.0f ← تستقرّ %.0f ← تخرج %.0f ✓"
      % (at(horizontal, 11.45), middle, at(horizontal, 13.55)))
window.editor.remove_layer(late)

# --- المعاينة الحيّة تُظهر الطبقة، وإلا وضعها المصمّم وهو لا يراها ---
from PIL import Image, ImageStat                          # noqa: E402

shots = os.path.join(os.environ.get("TEMP", "."), "wuncut_still.png")
mid = shot.start + shot.duration // 2
window.editor.set_track_flag(layer, "visible", False)
assert export.still(project, mid, shots, 480), "تعذّرت المعاينة"
without = ImageStat.Stat(Image.open(shots).convert("RGB")).mean

window.editor.set_track_flag(layer, "visible", True)
assert export.still(project, mid, shots, 480), "تعذّرت المعاينة مع الطبقة"
with_layer = ImageStat.Stat(Image.open(shots).convert("RGB")).mean
gap = max(abs(a - b) for a, b in zip(without, with_layer))
print("المعاينة: بلا طبقة %s · معها %s"
      % ([round(v, 1) for v in without], [round(v, 1) for v in with_layer]))
assert gap > 0.5, "المعاينة الحيّة لا تُظهر الطبقة (فرق %.2f)" % gap
os.remove(shots)
print("المعاينة الحيّة تُظهر الطبقة ✓")

# --- تصدير حقيقي والتحقّق من الإطارات ---
out = os.path.join(os.environ.get("TEMP", "."), "wuncut_layers.mp4")
found = export.encoders()
job = export.ExportJob(project, out, encoder=found[0][0], quality=60)
assert job.run(), "فشل تصدير الطبقات"

frames = os.path.join(os.environ.get("TEMP", "."), "wuncut_frame.png")


def brightness(at):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "%.2f" % at,
                    "-i", out, "-frames:v", "1", frames],
                   capture_output=True, creationflags=NO_WINDOW)
    from PIL import Image, ImageStat
    return ImageStat.Stat(Image.open(frames).convert("L")).mean[0]


empty = brightness(0.3)                       # قبل الطبقة
covered = brightness(project.seconds(shot.start + shot.duration // 2))
print("سطوع الإطار: بلا طبقة %.1f · مع الطبقة %.1f" % (empty, covered))
assert abs(covered - empty) > 0.4, \
    "الطبقة لم تغيّر الصورة الناتجة (%.2f مقابل %.2f)" % (covered, empty)
for path in (out, frames):
    if os.path.exists(path):
        os.remove(path)

print("\nفحص الطبقات: كل الفحوص سليمة")
