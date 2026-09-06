# -*- coding: utf-8 -*-
"""
جولة تقسية: تقود البرنامج الحقيقي على كل مسار وتبلّغ عن كل ما ينكسر.

تعمل بنافذة حقيقية لا خارج الشاشة. اللقطات خارج الشاشة لا تُظهر الأسطح
الأصليّة ولا استقرار التخطيط ولا تراكم الخيوط، وثلاثةٌ من أعطال هذا المشروع
مرّت من فحوصٍ خارج الشاشة لهذا السبب.

    python build_tools/torture.py فيديو.mov صورة.png

لا تتوقّف عند أول خطأ: تسجّله وتكمل، فتعطي قائمة الأعطال كلها في مرّة واحدة.
"""
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtCore import (QEventLoop, QtMsgType, Qt,      # noqa: E402
                            QTimer, qInstallMessageHandler)
from PySide6.QtMultimedia import QMediaPlayer               # noqa: E402
from PySide6.QtWidgets import (QApplication,                 # noqa: E402
                               QMessageBox)

from wun_cut import i18n                                    # noqa: E402
from wun_cut.core import animate, export, media             # noqa: E402
from wun_cut.gui import theme                               # noqa: E402

VIDEO = sys.argv[1]
IMAGE = sys.argv[2]

FAULTS = []             # (المرحلة، الوصف)
QT_MESSAGES = []
STAGE = ["البدء"]


def fault(what):
    FAULTS.append((STAGE[0], what))
    print("   ✗ %s" % what)


def ok(what):
    print("   ✓ %s" % what)


def phase(name):
    STAGE[0] = name
    print("\n[%s]" % name)


def handler(mode, _context, message):
    if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg,
                QtMsgType.QtFatalMsg):
        QT_MESSAGES.append(message)


qInstallMessageHandler(handler)


def excepthook(kind, value, tb):
    FAULTS.append((STAGE[0], "استثناء غير ملتقط: %s: %s" % (kind.__name__,
                                                            value)))
    traceback.print_exception(kind, value, tb)


sys.excepthook = excepthook


def pump(seconds, until=None):
    """يدير حلقة الأحداث فعليًّا. `until` دالّة تُنهي الانتظار مبكّرًا."""
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    if until is not None:
        watch = QTimer()
        watch.timeout.connect(lambda: until() and loop.quit())
        watch.start(120)
    loop.exec()


def timed(label, call, limit=20.0):
    """ينفّذ خطوةً ويبلّغ إن تجاوزت زمنها أو رمت استثناءً."""
    start = time.time()
    try:
        result = call()
    except Exception as exc:
        fault("%s رمى %s: %s" % (label, type(exc).__name__, exc))
        return None
    spent = time.time() - start
    if spent > limit:
        fault("%s استغرق %.1f ث (الحدّ %.0f)" % (label, spent, limit))
    return result


# ---------------------------------------------------------------- التشغيل

i18n.load()
LANGUAGE = i18n.language()
app = QApplication(sys.argv)
theme.load_fonts()
theme.apply_palette(app)
app.setFont(theme.font(10))
app.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
app.setStyleSheet(theme.qss())

from wun_cut.gui.main_window import MainWindow             # noqa: E402
from wun_cut.core.project import Clip                      # noqa: E402

phase("فتح النافذة")
window = MainWindow()
window.resize(1500, 920)
window.move(40, 40)
window.show()
window.raise_()
pump(1.5)
ok("النافذة ظهرت %dx%d" % (window.width(), window.height()))

if window._tour is not None if hasattr(window, "_tour") else False:
    window._tour.stop()
    pump(0.3)

# ------------------------------------------------------------- الاستيراد

phase("استيراد الوسائط")
for path in (VIDEO, IMAGE):
    try:
        window.bin.add(media.probe(path))
    except Exception as exc:
        fault("تعذّر استيراد %s: %s" % (os.path.basename(path), exc))
if window.bin.list.count() != 2:
    fault("المكتبة فيها %d عنصرًا لا 2" % window.bin.list.count())
else:
    ok("ملفان في المكتبة")

window.add_to_timeline(window.bin.items[0])
pump(0.6)
project = window.editor.project
base_track = project.track("video")
if not base_track.clips:
    fault("الفيديو لم يصل الخط الزمني")
    print("\nتوقّف: بلا مقطع لا يُفحص شيء")
    sys.exit(1)
base = base_track.clips[0]
ok("الفيديو على الخط: %.1f ث · %dx%d · %.4g fps"
   % (project.seconds(project.duration), project.width, project.height,
      float(project.fps)))

# --------------------------------------------------- التشغيل الخام أوّلًا

phase("التشغيل الخام")
# قبل أي تأثير: مقطع واحد نظيف يجب أن يُشغَّل من ملفه فورًا بلا ترميز
if window._plain_clip() is None:
    fault("مقطع واحد خام عُدّ مركّبًا، فسينتظر ترميزًا بلا داعٍ")
else:
    launched = time.time()
    window.toggle_play()
    pump(12.0, until=lambda: window.player.playbackState()
         == QMediaPlayer.PlayingState)
    took = time.time() - launched
    if window.player.playbackState() != QMediaPlayer.PlayingState:
        fault("التشغيل الخام لم يبدأ بعد %.1f ث" % took)
    elif took > 5.0:
        fault("التشغيل الخام استغرق %.1f ث" % took)
    else:
        ok("التشغيل الخام بدأ في %.1f ث" % took)
        mark = window.player.position()
        pump(2.0)
        if window.player.position() <= mark:
            fault("الموضع لا يتقدّم في التشغيل الخام (%d -> %d)"
                  % (mark, window.player.position()))
        else:
            ok("الموضع يتقدّم: %d -> %d م.ث"
               % (mark, window.player.position()))
        played = os.path.basename(window.player.source().toLocalFile())
        if played != os.path.basename(VIDEO):
            fault("التشغيل الخام شغّل %s لا الملف الأصلي" % played)
    window.toggle_play()
    pump(0.6)
    window.stage.show_still()

# ------------------------------------------------------------ الخط الزمني

phase("الخط الزمني")
window.timeline.fit()
pump(0.4)
span = window.timeline.ppf * project.duration
room = window.timeline.width() - 112
if span < room * 0.6:
    fault("الملء ترك المقطع في %d بكسل من %d" % (span, room))
else:
    ok("الملء: %d بكسل من %d" % (span, room))

window.editor.trim(base, project.frames(20))
window.timeline.fit()
pump(0.3)

before = window.timeline.ppf
window.timeline.zoom(2.0)
if window.timeline.ppf <= before:
    fault("التكبير لم يغيّر شيئًا")
window.timeline.fit()
if abs(window.timeline.ppf - before) > 1e-6:
    fault("الملء بعد التكبير لم يرجع كما كان")
else:
    ok("تكبير ثم ملء يرجعان كما كانا")

# سحب وقصّ عبر الإشارات نفسها التي تستعملها الفأرة
window.timeline.select(base.cid)
window.timeline.clipPicked.emit(base.cid)
depth = len(window.editor._undo)
window.timeline.dragBegan.emit()
for frame in range(0, 90, 5):
    window.timeline.clipMoved.emit(base.cid, frame)
window.timeline.dragEnded.emit()
pump(0.4)
if len(window.editor._undo) - depth != 1:
    fault("سحبة واحدة ولّدت %d لقطة تراجع"
          % (len(window.editor._undo) - depth))
else:
    ok("السحب: لقطة تراجع واحدة")

window.timeline.dragBegan.emit()
window.timeline.clipTrimmed.emit(base.cid, project.frames(12), False)
window.timeline.dragEnded.emit()
pump(0.3)
if project.find(base.cid).duration != project.frames(12):
    fault("القصّ لم يُطبَّق")
else:
    ok("القصّ من الطرف")

window.timeline.set_playhead(project.find(base.cid).start
                             + project.frames(5))
timed("التقسيم", window.split_at_playhead)
pump(0.4)
if len(base_track.clips) != 2:
    fault("التقسيم أنتج %d مقطعًا لا 2" % len(base_track.clips))
else:
    ok("التقسيم: مقطعان")

# ------------------------------------------------------------- التأثيرات

phase("التأثيرات والمعاينة الحيّة")
first = base_track.clips[0]
window.timeline.select(first.cid)
window.timeline.clipPicked.emit(first.cid)
window.seek(first.start + first.duration // 2)
pump(3.0, until=lambda: window.stage._pixmap is not None)
if window.stage._pixmap is None:
    fault("المعاينة الحيّة لم تظهر أصلًا")
else:
    ok("المعاينة الحيّة ظهرت")


def frame_mean():
    px = window.stage._pixmap
    if px is None:
        return None
    image = px.toImage()
    total = count = 0
    for y in range(0, image.height(), 9):
        for x in range(0, image.width(), 9):
            colour = image.pixelColor(x, y)
            total += colour.red() + colour.green() + colour.blue()
            count += 3
    return total / max(1, count)


def settled(tries=60):
    """
    ينتظر حتى تفرغ اللوحة من الرسم، ثم يقرأ.

    القياس بثبات البكسلات يكذب: قراءتان متتاليتان قد تلتقطان الإطارَ القديم
    نفسه قبل أن يصل الجديد، فيُحسب مستقرًّا وهو لم يبدأ. الحالةُ نفسها هي
    الإشارة الصحيحة - لا خيطُ رسمٍ جارٍ ولا طلبٌ معلّق - ثم مهلةٌ للرسم.
    """
    for _ in range(tries):
        pump(0.2)
        if window.stage._render is None and window.stage._pending is None:
            pump(0.4)
            if window.stage._render is None:
                return frame_mean()
    return frame_mean()


plain = settled()
window.effects.rows["brightness"].setValue(70)
pump(6.0, until=lambda: frame_mean() is not None
     and abs((frame_mean() or 0) - (plain or 0)) > 10)
lit = frame_mean()
if plain is None or lit is None or lit - plain < 10:
    fault("المعاينة لم تتبع السطوع (%s -> %s)" % (plain, lit))
else:
    ok("المعاينة تتبع السطوع: %.1f -> %.1f" % (plain, lit))
window.effects.rows["brightness"].setValue(0)
pump(1.5)

for name, value in (("contrast", 30), ("saturation", -60), ("speed", 150),
                    ("volume", 50), ("fade_in", 500), ("fade_out", 500),
                    ("anim_ms", 800)):
    window.effects.rows[name].setValue(value)
    pump(0.15)
live = project.find(first.cid)
missing = [n for n, v in (("contrast", 30), ("saturation", -60),
                          ("speed", 150), ("volume", 50))
           if live.effect(n) != v]
if missing:
    fault("تأثيرات لم تُسجَّل: %s" % missing)
else:
    ok("كل المنزلقات تصل النموذج")

for slot, value in (("anim_in", "zoom_in"), ("anim_out", "slide_left")):
    box = window.effects.anims[slot]
    box.setCurrentIndex(box.findData(value))
    pump(0.2)
if (live.anim_in, live.anim_out) != ("zoom_in", "slide_left"):
    fault("الحركات لم تُسجَّل: %s" % ((live.anim_in, live.anim_out),))
else:
    ok("حركتا الدخول والخروج")

window.effects._apply_look({"brightness": 18, "contrast": 12,
                            "saturation": 10})
pump(0.3)
if live.effect("contrast") != 12:
    fault("النظرة الجاهزة لم تُطبَّق")
else:
    ok("النظرات الجاهزة")

# --------------------------------------------------------------- الطبقات

phase("الصور والطبقات")
window.bin.list.setCurrentRow(1)
window.timeline.set_playhead(project.frames(2))
timed("إضافة طبقة", window.add_as_layer)
pump(0.6)
if len(project.layers) != 2:
    fault("عدد الطبقات %d لا 2" % len(project.layers))
    picture = None
else:
    picture = project.layers[0].clips[0]
    ok("الصورة على طبقة: %s" % picture.name)

if picture is not None:
    for name, value in (("layer_scale", 30), ("layer_x", 30),
                        ("layer_y", -25)):
        window.effects.rows[name].setValue(value)
        pump(0.15)
    pump(4.0)
    shown = project.find(picture.cid)
    if shown.effect("layer_scale") != 30:
        fault("حجم الطبقة لم يُسجَّل")
    else:
        ok("حجم الطبقة وموضعها")

    layer = project.layers[0]
    window._on_menu(("track", "visible", layer), 0)
    if layer.visible:
        fault("إخفاء الطبقة من القائمة لم يعمل")
    window._on_menu(("track", "visible", layer), 0)
    window._on_menu(("clip", "duplicate", picture.cid), picture.end)
    pump(0.4)
    if len(layer.clips) != 2:
        fault("تكرار المقطع لم يعمل")
    else:
        ok("قائمة النقر الأيمن: إخفاء وتكرار")
    window._on_menu(("clip", "delete", layer.clips[1].cid), 0)
    pump(0.3)

# ------------------------------------------------------ الفلاتر والانتقالات

phase("الفلاتر والانتقالات")
from wun_cut.core import filters, transitions                # noqa: E402

window.timeline.select(first.cid)
window.timeline.clipPicked.emit(first.cid)
box = window.effects.anims["filter"]
missed = []
for key in filters.NAMES[1:]:
    box.setCurrentIndex(box.findData(key))
    pump(0.05)
    if project.find(first.cid).filter != key:
        missed.append(key)
if missed:
    fault("فلاتر لم تُسجَّل: %s" % missed)
else:
    ok("العشرة فلاتر كلّها تصل النموذج")
box.setCurrentIndex(box.findData("warm"))
window.effects.rows["filter_amount"].setValue(75)
pump(2.5)

second = base_track.clips[1]
window.timeline.select(second.cid)
window.timeline.clipPicked.emit(second.cid)
box = window.effects.anims["trans"]
missed = []
for key in transitions.NAMES[1:]:
    box.setCurrentIndex(box.findData(key))
    pump(0.05)
    if project.find(second.cid).trans != key:
        missed.append(key)
if missed:
    fault("انتقالات لم تُسجَّل: %s" % missed)
else:
    ok("الخمسة عشر انتقالًا كلّها تصل النموذج")
box.setCurrentIndex(box.findData("fade"))
window.effects.rows["trans_ms"].setValue(700)
pump(0.3)

before_len = project.seconds(project.duration)
graph_args = export.build(project, "x.mp4")
graph_text = graph_args[graph_args.index("-filter_complex") + 1]
if "xfade" not in graph_text:
    fault("الانتقال لم يصل أمر التصدير")
elif "colorbalance" not in graph_text:
    fault("الفلتر لم يصل أمر التصدير")
else:
    ok("الفلتر والانتقال في أمر التصدير")

# ---------------------------------------------------------------- النصوص

phase("النصوص")
window.timeline.set_playhead(project.frames(1))
layers_before = len(project.layers)
timed("إضافة نصّ", window.add_text)
pump(0.6)
if len(project.layers) != layers_before + 1:
    fault("لم تُنشأ طبقة نصّ")
    caption = None
else:
    caption = project.layers[0].clips[0]
    if not caption.is_text:
        fault("المقطع الجديد ليس نصًّا")
    elif not os.path.exists(caption.source):
        fault("صورة النصّ غير موجودة: %s" % caption.source)
    else:
        ok("نصّ على طبقة: %s" % os.path.basename(caption.source))

if caption is not None and caption.is_text:
    window.timeline.select(caption.cid)
    window.timeline.clipPicked.emit(caption.cid)
    if window.effects.text_box.isHidden():
        fault("محرّر النصّ لم يظهر للمقطع النصّي")
    old = caption.source
    window._on_text("وِن كَت · تجربة", "#FFD24A", "center")
    pump(0.4)
    if caption.text != "وِن كَت · تجربة":
        fault("النصّ لم يُحدَّث في النموذج")
    elif caption.source == old:
        fault("صورة النصّ لم يُعَد رسمها بعد التعديل")
    elif not os.path.exists(caption.source):
        fault("الصورة الجديدة غير موجودة")
    else:
        ok("تعديل النصّ يعيد رسم صورته")

    old = caption.source
    window.effects.rows["text_size"].setValue(96)
    pump(0.4)
    if caption.source == old:
        fault("مقاس النصّ لم يُعِد الرسم")
    else:
        ok("مقاس النصّ يعيد الرسم")

    # المقطع غير النصّي لا يُظهر محرّر النصّ
    window.timeline.select(first.cid)
    window.timeline.clipPicked.emit(first.cid)
    if not window.effects.text_box.isHidden():
        fault("محرّر النصّ ظهر لمقطع فيديو")
    else:
        ok("محرّر النصّ يظهر للنصوص وحدها")

# --------------------------------------------------------- التراجع والإعادة

phase("التراجع والإعادة")
snapshot = project.to_dict()
for _ in range(12):
    window.undo()
    pump(0.05)
for _ in range(12):
    window.redo()
    pump(0.05)
pump(0.5)
if project.to_dict() != snapshot:
    fault("١٢ تراجعًا ثم ١٢ إعادة لم ترجع المشروع كما كان")
else:
    ok("١٢ تراجعًا وإعادة ترجع الحالة تمامًا")

# ---------------------------------------------------------------- الملصقات

phase("الملصقات")
from wun_cut.gui import stickers                            # noqa: E402
from PySide6.QtGui import QRawFont                          # noqa: E402

absent = [g for g in stickers.all_emoji()
          if not QRawFont.fromFont(stickers.emoji_font(64))
          .supportsCharacter(ord(g[0]))]
if absent:
    fault("إيموجي لا يحمله الخطّ فيُرسم مربّعًا: %s" % absent)
else:
    ok("خطّ النظام يحمل الـ%d إيموجي كلّها" % len(stickers.all_emoji()))

drawn = [(k, stickers.render("shape", k)) for k in stickers.SHAPE_KEYS]
missing = [k for k, path in drawn if not path or not os.path.exists(path)]
if missing:
    fault("أشكال لم تُرسم: %s" % missing)
else:
    ok("الـ%d أشكال كلّها تُرسم" % len(drawn))

layers_before = len(project.layers)
sticker_path = stickers.render("emoji", "🔥")
sticker_layer = window.editor.add_layer("ملصق")
badge = Clip(sticker_path, 0, project.frames(2), name="🔥")
badge.set_effect("layer_scale", 25)
badge.set_effect("layer_x", -30)
window.editor.append(sticker_layer, badge)
window.editor.move(badge, project.frames(1))
window.timeline.set_project(project)
pump(0.4)
if len(project.layers) != layers_before + 1:
    fault("طبقة الملصق لم تُنشأ")
else:
    graph_args = export.build(project, "x.mp4")
    graph_text = graph_args[graph_args.index("-filter_complex") + 1]
    if "format=yuva420p" not in graph_text:
        fault("الملصق بلا شفافية في أمر التصدير")
    else:
        ok("الملصق طبقةٌ شفّافة في التصدير")

# ------------------------------------------------------ التحريك المستمرّ

phase("التحريك المستمرّ")
window.timeline.select(first.cid)
window.timeline.clipPicked.emit(first.cid)
box = window.effects.anims["motion"]
missed = []
for key in animate.MOTION_NAMES[1:]:
    box.setCurrentIndex(box.findData(key))
    pump(0.05)
    if project.find(first.cid).motion != key:
        missed.append(key)
if missed:
    fault("تحريكات لم تُسجَّل: %s" % missed)
else:
    ok("السبعة تحريكات كلّها تصل النموذج")

box.setCurrentIndex(box.findData("zoom_pan"))
window.effects.rows["motion_amount"].setValue(80)
pump(0.3)
live = project.find(first.cid)
seconds = project.seconds(live.duration)
canvas = (project.width, project.height)
# التحريك المستمرّ وحده، لا مجتمعًا مع حركتَي الدخول والخروج: هاتان
# يُفترض بهما الخروج عن اللوحة - فذاك معنى "ينزلق من خارج الشاشة" - فقياس
# المجموع بقاعدة "لا سواد" يخلط شيئين مختلفين.
edges = []
for at in (0.0, seconds / 2, seconds):
    zoom, dx, dy = animate.sample("", "", seconds, 0.6, at, canvas,
                                  live.motion, live.effect("motion_amount"))
    if zoom < 1.0 or abs(dx) > (zoom - 1) / 2 * canvas[0] + 1             or abs(dy) > (zoom - 1) / 2 * canvas[1] + 1:
        edges.append((at, round(zoom, 3), round(dx, 1)))
if edges:
    fault("التحريك ينزلق خارج اللوحة: %s" % edges[:2])
else:
    ok("التحريك لا يتجاوز الفائض عند أي لحظة")

graph_args = export.build(project, "x.mp4")
if "eval=frame" not in graph_args[graph_args.index("-filter_complex") + 1]:
    fault("التحريك لم يصل أمر التصدير")
else:
    ok("التحريك في أمر التصدير")
box.setCurrentIndex(0)

# ------------------------------------------------------- اللوحة والحفظ

phase("اللوحة")
for index, (ratio, label) in enumerate(
        [(None, ""), ((16, 9), "16:9"), ((9, 16), "9:16"), ((1, 1), "1:1")]):
    if not ratio:
        continue
    window.shape.setCurrentIndex(index)
    pump(0.2)
    got = project.width / max(1, project.height)
    if abs(got - ratio[0] / ratio[1]) > 0.02:
        fault("النسبة %s أعطت %dx%d" % (label, project.width, project.height))
    elif min(project.width, project.height) not in range(480, 1441):
        fault("مقاس غير مألوف لـ %s: %dx%d"
              % (label, project.width, project.height))
else:
    ok("النسب الثلاث تعطي مقاسات قياسية")
window.shape.setCurrentIndex(1)
window.fill.setCurrentIndex(1)
pump(0.3)
if project.fill != "blur":
    fault("الخلفية الضبابية لم تُسجَّل")
else:
    graph_args = export.build(project, "x.mp4")
    if "gblur" not in graph_args[graph_args.index("-filter_complex") + 1]:
        fault("الخلفية الضبابية لم تصل أمر التصدير")
    else:
        ok("الخلفية الضبابية تصل التصدير")
window.fill.setCurrentIndex(0)
window._sync_canvas()
if window.fill.currentData() != "black":
    fault("القائمة لا تعكس حالة المشروع")

phase("حفظ المشروع وفتحه")
import json as _json                                        # noqa: E402
saved = os.path.join(os.environ.get("TEMP", "."), "torture.wcut")
snapshot = _json.dumps(project.to_dict(), sort_keys=True, ensure_ascii=False)
if not window._write(saved):
    fault("تعذّر الحفظ")
elif window.editor.dirty:
    fault("المشروع بقي متّسخًا بعد الحفظ")
else:
    ok("حُفظ %.1f ك.ب" % (os.path.getsize(saved) / 1e3))
    reopened = _json.dumps(
        __import__("wun_cut.core.project", fromlist=["Project"])
        .Project.load(saved).to_dict(), sort_keys=True, ensure_ascii=False)
    if reopened != snapshot:
        fault("المشروع بعد الفتح لا يطابق المحفوظ")
    else:
        ok("الفتح يطابق الحفظ حرفًا بحرف")
    os.remove(saved)

# --------------------------------------------------------------- التشغيل

phase("التشغيل")
window.timeline.set_playhead(0)
# ترميز المعاينة مقيسٌ لا مقدَّر: ١٢ قراءة على هذا المشروع نفسه وقعت كلّها
# بين ٢٫٣ و٢٫٩ ث. فثلاثون ثانية عشرة أضعاف الأسوأ - سعةٌ لجهازٍ مشغول، وضيقٌ
# يكفي ليُكشف تباطؤٌ حقيقيّ. وأربعون ومئة تخفيان التباطؤ ولا تمنعان عطلًا.
PREVIEW_LIMIT = 30.0

start = time.time()
timed("ضغط تشغيل", window.toggle_play, limit=60.0)
pump(PREVIEW_LIMIT, until=lambda: window.btn_play.isEnabled()
     and window.player.playbackState() == QMediaPlayer.PlayingState)
waited = time.time() - start
if window.player.playbackState() != QMediaPlayer.PlayingState:
    # «موقوف» وحدها لا تفرّق بين ترميزٍ لم ينتهِ ومشغّلٍ عَلِق: الزرّ معطّل
    # أثناء الترميز، والمصدر يبقى على الملف الخام ما لم تصل المعاينة.
    fault("لم يبدأ التشغيل بعد %.1f ث (الحالة %s · الزرّ %s · الوسيط %s · "
          "المصدر %s)"
          % (waited, window.player.playbackState(),
             "مفعّل" if window.btn_play.isEnabled() else "معطّل - ترميزٌ جارٍ",
             window.player.mediaStatus(),
             os.path.basename(window.player.source().toLocalFile() or "-")))
else:
    ok("بدأ التشغيل بعد %.1f ث من %s"
       % (waited, os.path.basename(window.player.source().toLocalFile())))

    was = window.player.position()
    pump(2.5)
    now = window.player.position()
    if now <= was:
        fault("الموضع لا يتقدّم أثناء التشغيل (%d -> %d)" % (was, now))
    else:
        ok("الموضع يتقدّم: %d -> %d م.ث" % (was, now))
    if window.stage.stack.currentWidget() is not window.stage.video:
        fault("المسرح لم ينتقل إلى ودجت الفيديو أثناء التشغيل")

    window.toggle_play()
    pump(0.8)
    if window.player.playbackState() == QMediaPlayer.PlayingState:
        fault("الضغطة الثانية لم توقف التشغيل")
    else:
        ok("الإيقاف يعمل")

    second = time.time()
    window.toggle_play()
    pump(8.0, until=lambda: window.player.playbackState()
         == QMediaPlayer.PlayingState)
    again = time.time() - second
    if again > 4.0:
        fault("التشغيل الثاني استغرق %.1f ث رغم أن شيئًا لم يتغيّر" % again)
    else:
        ok("التشغيل الثاني فوري: %.1f ث" % again)
    window.player.pause()
    pump(0.5)

# --------------------------------------------------------------- التصدير

phase("التصدير")
target = os.path.join(os.environ.get("TEMP", "."), "torture_out.mp4")
try:
    options = {"encoder": (export.encoders() or [("libx264", "")])[0][0],
               "quality": 55, "scale": (854, 480), "fps": None,
               "interpolate": False}
    job = export.ExportJob(project, target, **options)
    seen = []
    done = job.run(on_progress=lambda d, t: seen.append(d) or True)
    if not done or not os.path.exists(target):
        fault("التصدير لم ينتج ملفًا")
    else:
        size = os.path.getsize(target) / 1e6
        if not seen:
            fault("التصدير لم يبلّغ عن أي تقدّم")
        ok("صُدِّر %.1f م.ب · %d تحديث تقدّم" % (size, len(seen)))
        os.remove(target)
except Exception as exc:
    fault("التصدير رمى %s: %s" % (type(exc).__name__, exc))
    dump = os.path.join(os.environ.get("TEMP", "."), "torture_cmd.txt")
    try:
        io_args = export.build(project, target, **options)
        with open(dump, "w", encoding="utf-8") as handle:
            handle.write(chr(10).join(io_args))
        import json as _json
        with open(dump + ".json", "w", encoding="utf-8") as handle:
            _json.dump(project.to_dict(), handle, ensure_ascii=False, indent=1)
        print("      (الأمر في %s)" % dump)
    except Exception as inner:
        print("      تعذّر حفظ الأمر:", inner)

# ------------------------------------------------------------- التسرّبات

phase("التسرّبات")
# الرسمُ الجاري يكتب ملفّه قبل أن يُقرأ ويُحذف، فعدُّ المجلّد في أثنائه
# يعدّ عملًا قائمًا تسرّبًا. ننتظر هدوء اللوحة أوّلًا.
pump(6.0, until=lambda: window.stage._render is None)
folder = window.stage._folder
leftovers = [n for n in os.listdir(folder) if n.endswith(".jpg")] \
    if os.path.isdir(folder) else []
if leftovers:
    fault("صور معاينة لم تُحذف: %d" % len(leftovers))
else:
    ok("لا صور معاينة متروكة")

import threading                                            # noqa: E402
alive = threading.active_count()
if alive > 8:
    fault("خيوط حيّة كثيرة: %d" % alive)
else:
    ok("خيوط حيّة: %d" % alive)

if QT_MESSAGES:
    seen = {}
    for message in QT_MESSAGES:
        seen[message] = seen.get(message, 0) + 1
    for message, count in sorted(seen.items(), key=lambda p: -p[1])[:6]:
        fault("تحذير Qt (×%d): %s" % (count, message[:110]))
else:
    ok("لا تحذيرات من Qt")

# --------------------------------------------------------------- الإغلاق

phase("الإغلاق")
# مشروع متّسخ يجب أن يسأل قبل أن يُغلق: نُظهر السؤال ونضغط "تجاهل" بمؤقّت،
# فإن لم يظهر أصلًا فذاك عملٌ يضيع بنقرة.
window.editor.dirty = True
asked = []


def dismiss():
    for widget in app.topLevelWidgets():
        if isinstance(widget, QMessageBox) and widget.isVisible():
            asked.append(True)
            widget.button(QMessageBox.Discard).click()
            return


QTimer.singleShot(900, dismiss)
QTimer.singleShot(6000, lambda: [w.close() for w in app.topLevelWidgets()
                                 if isinstance(w, QMessageBox)])
window.close()
if not asked:
    fault("الإغلاق لم يسأل عن حفظ عملٍ غير محفوظ")
else:
    ok("الإغلاق يسأل عن الحفظ قبل أن يفقد العمل")

i18n.set_language(LANGUAGE)
closed = time.time()
window._quitting = True
window.close()
pump(3.0)
if time.time() - closed > 9.0:
    fault("الإغلاق استغرق %.1f ث" % (time.time() - closed))
else:
    ok("أُغلق في %.1f ث" % (time.time() - closed))

print("\n" + "=" * 62)
if FAULTS:
    print("وُجد %d عطلًا:" % len(FAULTS))
    for where, what in FAULTS:
        print("  [%s] %s" % (where, what))
else:
    print("جولة التقسية: لم يُعثر على أي عطل")
print("=" * 62)
sys.exit(1 if FAULTS else 0)
