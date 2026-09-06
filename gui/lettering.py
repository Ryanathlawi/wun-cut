"""
أنيميشن النصّ حرفًا حرفًا.

النصّ في هذه الأداة صورةٌ تُوضع طبقةً، فتتحرّك كتلةً واحدة. وأن يدخل الحرفُ
بعد الحرف يحتاج أن يكون لكل حرفٍ زمنُه، وهذا لا يتأتّى بصورةٍ ساكنة.

فيُرسم النصّ مقطعًا شفّافًا قصيرًا: كل إطارٍ يُرسم فيه كلُّ حرفٍ بحالته عند
تلك اللحظة، ثم تُرمَّز الإطارات VP9 بقناة شفافية. الناتج مقطعٌ عاديّ على
طبقة، يرث الموضع والحجم والفلاتر بلا سطرٍ واحدٍ جديد في التصدير.

والعربية تُشبَك أوّلًا ثم تُقطَّع: QTextLayout يُخرج الرسمات بعد الشبك،
وpathForGlyph يعطي مسارَ كلٍّ منها. فلو قُطّع النصّ حروفًا قبل الشبك
لانفصلت الحروف - وهذا أوّل ما يفسد النصّ العربي.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen, QTextLayout, QTransform)

from . import theme
from ..core import tools

FOLDER = os.path.join(tempfile.gettempdir(), "wun_cut_lettering")
FPS = 30                    # الحركة لا تحتاج ستّين، والتصدير يعيد التوقيت
ENTER = 0.42                # نصيبُ الحرف الواحد من زمن الدخول
SPREAD = 0.52               # كم يتأخّر آخرُ حرفٍ عن أوّله، من زمن الدخول
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# المفتاح، التسمية، (إزاحة أفقية، إزاحة رأسية، تكبير، دوران) عند u=0
#
# u تقدّمُ الحرف: صفرٌ أوّلَ دخوله وواحدٌ حين يستقرّ. كل قيمةٍ هنا حالتُه
# عند الصفر، ويُستوفى ما بينهما بتسارعٍ خارج. صفٌّ واحد يكفي لحركةٍ جديدة.
STYLES = [
    ("", "بلا أنيميشن", None),
    ("letters_right", "حرفًا حرفًا من اليمين", (1.0, 0.0, 1.0, 0.0)),
    ("letters_left", "حرفًا حرفًا من اليسار", (-1.0, 0.0, 1.0, 0.0)),
    ("letters_up", "حرفًا حرفًا من الأسفل", (0.0, 1.0, 1.0, 0.0)),
    ("letters_drop", "سقوط الحروف", (0.0, -1.2, 1.0, 0.0)),
    ("letters_pop", "تكبير حرفًا حرفًا", (0.0, 0.0, 0.25, 0.0)),
    ("letters_spin", "دوران الحروف", (0.0, 0.0, 0.35, -95.0)),
    ("letters_fade", "ظهورٌ متتابع", (0.0, 0.0, 1.0, 0.0)),
]

NAMES = [key for key, _label, _spec in STYLES]
LABELS = {key: label for key, label, _spec in STYLES}
_SPECS = {key: spec for key, _label, spec in STYLES}

MARGIN = 30
DEFAULTS = {"size": 64, "colour": "#FFFFFF", "outline": 45,
            "align": "center"}


def _ease(u):
    """تسارعٌ خارج تكعيبيّ: سريعٌ أوّله يهدأ آخره."""
    return 1.0 - (1.0 - u) ** 3


def _shaped(body, font):
    """
    الرسمات بعد الشبك: (المسار، س، ع) لكلٍّ منها، بترتيب القراءة.

    QTextLayout قد يُخرج أكثر من مقطعِ رسمٍ حين يختلط اتجاهان، فتُجمع كلّها.
    """
    layout = QTextLayout(body, font)
    layout.beginLayout()
    line = layout.createLine()
    if not line.isValid():
        layout.endLayout()
        return []
    line.setLineWidth(1 << 20)
    layout.endLayout()

    out = []
    for run in layout.glyphRuns():
        raw = run.rawFont()
        for index, spot in zip(run.glyphIndexes(), run.positions()):
            path = QPainterPath()
            path.addPath(raw.pathForGlyph(index))
            if path.isEmpty():
                continue            # فراغٌ أو رسمةٌ بلا حبر
            out.append((path, spot.x(), spot.y()))
    return out


def key(*parts):
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:14]


def render(body, canvas_width, seconds, style, size=None, colour=None,
           outline=None, align=None, enter=1.3):
    """
    يرسم النصّ مقطعًا شفّافًا بحركةٍ حرفًا حرفًا. يرجع مساره أو None.

    `seconds` مدّة المقطع كلّه: تدخل الحروف في `enter` ثم تثبت البقيّة.
    إطارات الثبات متطابقة، فتنكمش عند الترميز إلى لا شيء تقريبًا.
    """
    body = (body or "").strip()
    spec = _SPECS.get(style or "")
    if not body or spec is None:
        return None

    size = int(size or DEFAULTS["size"])
    colour = colour or DEFAULTS["colour"]
    outline = DEFAULTS["outline"] if outline is None else int(outline)
    align = align or DEFAULTS["align"]
    width = max(64, int(canvas_width))
    seconds = max(0.2, float(seconds))
    enter = max(0.2, min(float(enter), seconds))

    target = os.path.join(FOLDER, "l_%s.webm" % key(
        body, width, seconds, style, size, colour, outline, align, enter))
    if os.path.exists(target):
        return target
    os.makedirs(FOLDER, exist_ok=True)

    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(size)
    font.setWeight(QFont.Bold)
    glyphs = _shaped(body, font)
    if not glyphs:
        return None

    metrics = QFontMetrics(font)
    spread = max(x for _p, x, _y in glyphs) - min(x for _p, x, _y in glyphs)
    span = spread + metrics.averageCharWidth() * 1.4
    if align == "center":
        origin = (width - span) / 2.0
    elif align == "left":
        origin = MARGIN
    else:
        origin = width - MARGIN - span
    origin -= min(x for _p, x, _y in glyphs)

    reach = max(size * 2.2, width * 0.16)       # مدى الدخول بالبكسل
    height = int(metrics.height() + size * 1.4 + 2 * MARGIN)
    base = metrics.ascent() + MARGIN + size * 0.7
    pen = QPen(QColor(0, 0, 0, 210), outline / 100.0 * (size / 9.0) + 1,
               Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    ink = QColor(colour)

    frames = max(2, int(round(seconds * FPS)))
    step = 1.0 / FPS
    settle = enter * (1.0 - SPREAD) or step
    stage = os.path.join(FOLDER, "stage_%d" % os.getpid())
    os.makedirs(stage, exist_ok=True)
    try:
        last = None
        for number in range(frames):
            now = number * step
            if last is not None and now > enter:
                # كلّ الحروف استقرّت: الإطار نفسه يتكرّر
                last.save(os.path.join(stage, "f%05d.png" % number))
                continue
            image = QImage(QSize(width, height),
                           QImage.Format_ARGB32_Premultiplied)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(Qt.NoBrush)
            for order, (path, x, y) in enumerate(glyphs):
                begin = (enter * SPREAD) * (order / max(1, len(glyphs) - 1))
                u = _ease(max(0.0, min(1.0, (now - begin) / settle)))
                if u <= 0.0:
                    continue
                dx, dy, grow, turn = spec
                moved = QTransform()
                moved.translate(origin + x + dx * reach * (1 - u),
                                base + y + dy * reach * (1 - u))
                if grow != 1.0 or turn:
                    moved.rotate(turn * (1 - u))
                    scale = grow + (1.0 - grow) * u
                    moved.scale(scale, scale)
                shown = moved.map(path)
                alpha = int(255 * min(1.0, u * 1.6))
                if outline > 0:
                    pen.setColor(QColor(0, 0, 0, int(210 * alpha / 255)))
                    painter.setPen(pen)
                    painter.drawPath(shown)
                painter.fillPath(shown, QColor(ink.red(), ink.green(),
                                               ink.blue(), alpha))
            painter.end()
            image.save(os.path.join(stage, "f%05d.png" % number))
            last = image

        done = subprocess.run(
            [tools.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
             "-framerate", str(FPS), "-i", os.path.join(stage, "f%05d.png"),
             "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "3M",
             "-an", target],
            capture_output=True, creationflags=NO_WINDOW)
        if done.returncode != 0 or not os.path.exists(target):
            return None
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return target


def sweep():
    """يمسح ما خلّفته جلسةٌ سابقة."""
    if os.path.isdir(FOLDER):
        shutil.rmtree(FOLDER, ignore_errors=True)


def demo():
    """فحص ذاتي: الشبك محفوظ، والحروف تدخل واحدًا بعد واحد."""
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    sweep()

    assert NAMES[0] == "" and len(NAMES) == 8
    assert render("مرحبا", 1280, 2.0, "") is None, "بلا نمطٍ أنتج مقطعًا"
    assert render("", 1280, 2.0, "letters_right") is None

    # --- الشبك: العربية تُقطَّع بعد الشبك لا قبله ---
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(96)
    font.setWeight(QFont.Bold)
    shaped = _shaped("مرحبا", font)
    assert len(shaped) >= 4, "لم تُشبك: %d رسمة" % len(shaped)
    # الترتيب من اليمين لليسار: أوّل رسمةٍ أقصى يمينًا
    xs = [x for _p, x, _y in shaped]
    assert xs[0] > xs[-1], "ترتيب الرسمات ليس بترتيب القراءة: %s" % xs
    print("الشبك: «مرحبا» %d رسمة، من %.0f إلى %.0f (يمين ← يسار) ✓"
          % (len(shaped), xs[0], xs[-1]))

    path = render("حرفٌ حرفًا", 1280, 1.8, "letters_right", size=90)
    assert path and os.path.exists(path), "لم يُرسم المقطع"

    # --- الحروف تدخل تباعًا: الحبر يزداد ولا يظهر دفعةً واحدة ---
    # الحروف تدخل تباعًا. القياس بتركيب المقطع على لونٍ صلب - وهو ما يفعله
    # التصدير بالضبط - لا باستخراج PNG منه: مفكّك VP9 الافتراضي يُسقط قناة
    # الشفافية عند الاستخراج، فيقرأ الفحصُ مساحةَ الصورة كلَّها حبرًا.
    probe = os.path.join(FOLDER, "probe")
    os.makedirs(probe, exist_ok=True)
    subprocess.run(
        [tools.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=0x102030:s=1280x360:d=2",
         "-c:v", "libvpx-vp9", "-i", path,
         "-filter_complex",
         "[1:v]format=yuva420p[t];[0:v][t]overlay=(W-w)/2:(H-h)/2,"
         "fps=10[o]",
         "-map", "[o]", os.path.join(probe, "p%03d.png")],
        capture_output=True, creationflags=NO_WINDOW)
    shots = sorted(os.listdir(probe))
    assert len(shots) >= 6, "إطارات قليلة: %d" % len(shots)

    def ink_of(name):
        """بكسلاتٌ غطّت لونَ الخلفية: هذا هو الحبر الظاهر فعلًا."""
        image = QImage(os.path.join(probe, name))
        seen = 0
        for y in range(0, image.height(), 3):
            for x in range(0, image.width(), 3):
                colour = image.pixelColor(x, y)
                if abs(colour.red() - 16) + abs(colour.green() - 32) +                         abs(colour.blue() - 48) > 40:
                    seen += 1
        return seen

    counts = [ink_of(name) for name in shots]
    assert counts[0] < counts[len(counts) // 2] < counts[-1],         "الحبر لا يتزايد: %s" % counts[:6]
    assert counts[0] * 3 < counts[-1],         "الحروف ظهرت دفعةً واحدة: %d ← %d" % (counts[0], counts[-1])
    assert abs(counts[-1] - counts[-2]) <= max(4, counts[-1] * 0.04),         "لم يستقرّ: %d ثم %d" % (counts[-2], counts[-1])
    print("التتابع: الحبر %d ← %d ← %d ثم يثبت ✓"
          % (counts[0], counts[len(counts) // 2], counts[-1]))

    # --- الشفافية باقية: الخلفية تظهر من حول الحروف ---
    settled = QImage(os.path.join(probe, shots[-1]))
    corner = settled.pixelColor(4, 4)
    # التقريب في تحويل YUV يزيح القيمة درجةً أو درجتين، فيُقاس بهامش
    drift = (abs(corner.red() - 16) + abs(corner.green() - 32)
             + abs(corner.blue() - 48))
    assert drift <= 9,         "الركن ليس لون الخلفية: %s - المقطع غطّى اللوحة" % (corner.getRgb(),)
    assert counts[-1] < (settled.width() // 3) * (settled.height() // 3) * 0.6,         "الحبر غطّى أكثر من نصف اللوحة: الشفافية ضائعة"

    # --- الاتجاهان يختلفان فعلًا ---
    other = render("حرفٌ حرفًا", 1280, 1.8, "letters_left", size=90)
    assert other and other != path, "الاتجاهان أعطيا الملفّ نفسه"
    again = render("حرفٌ حرفًا", 1280, 1.8, "letters_right", size=90)
    assert again == path, "الخزن لم يُستعمل"

    shutil.rmtree(probe, ignore_errors=True)
    print("gui/lettering: كل الفحوص سليمة (%d نمطًا)" % (len(NAMES) - 1))
    app


if __name__ == "__main__":
    demo()
