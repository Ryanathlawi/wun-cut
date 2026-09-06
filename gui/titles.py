"""
رسم النصوص صورةً شفّافة.

FFmpeg يرسم النصّ بـ drawtext، وهو لا يشبك الحروف العربية ولا يعكس اتجاهها في
أكثر البِنى: «مرحبا» تخرج حروفًا منفصلة مقلوبة. وQt يشبكها صحيحةً - يرسم بها
واجهة البرنامج كلّها - فنرسم النصّ صورةً بقناة شفافية ثم نضعها طبقةً.

والمكسب الثاني أكبر: النصّ يصير مقطعًا عاديًّا على طبقة، فيرث الموضع والحجم
والحركات والفلاتر بلا سطرٍ واحد جديد في التصدير.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen)

from . import theme

FOLDER = os.path.join(tempfile.gettempdir(), "wun_cut_titles")
MARGIN = 28                 # فسحة حول النصّ تسع الحدّ والظلّ
REFERENCE = 3840            # عرض الرسم المرجعيّ: أكبر مقاس تصدير
DEFAULTS = {"size": 64, "colour": "#FFFFFF", "outline": 45,
            "align": "center"}

ALIGNMENTS = [("right", "لليمين"), ("center", "في الوسط"), ("left", "لليسار")]
_FLAGS = {"right": Qt.AlignRight, "center": Qt.AlignHCenter,
          "left": Qt.AlignLeft}


def key(body, size, colour, outline, align, width):
    raw = "|".join(str(v) for v in (body, size, colour, outline, align,
                                    width))
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:14]


def render(body, canvas_width, size=None, colour=None, outline=None,
           align=None):
    """
    يرسم النصّ صورةً شفّافة ويرجع مسارها، أو None إن كان النصّ فارغًا.

    عرض الصورة عرض اللوحة كاملًا: الطبقة تُوضَع بالنسبة إلى المركز، فنصٌّ
    بعرضه الطبيعي يقفز يمينًا ويسارًا كلّما غُيّرت كلماته.
    """
    body = (body or "").strip()
    if not body:
        return None
    size = int(size or DEFAULTS["size"])
    colour = colour or DEFAULTS["colour"]
    outline = DEFAULTS["outline"] if outline is None else int(outline)
    align = align or DEFAULTS["align"]

    width = max(64, int(canvas_width))
    # النصّ يُرسم بعرضٍ مرجعيّ ثابت لا بعرض المشروع: التصدير قد يكون أكبر من
    # المشروع - مشروع 1080p يُصدَّر 1440p أو 4K - فصورةٌ بمقاس المشروع تُكبَّر
    # حينها فتلين حوافّ الحروف. كل المقادير تُضرب بالنسبة نفسها، فالتركيب
    # والحجم النسبيّ لا يتغيّران بتاتًا.
    bump = max(1.0, REFERENCE / float(width))
    if bump > 1.0:
        size = max(1, int(round(size * bump)))
        width = REFERENCE
    margin = max(1, int(round(MARGIN * bump)))

    target = os.path.join(FOLDER, "t_%s.png"
                          % key(body, size, colour, outline, align, width))
    if os.path.exists(target):
        return target
    os.makedirs(FOLDER, exist_ok=True)

    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(size)
    font.setWeight(QFont.Bold)
    metrics = QFontMetrics(font)

    inner = width - 2 * margin
    flags = _FLAGS.get(align, Qt.AlignHCenter) | Qt.TextWordWrap
    bounds = metrics.boundingRect(QRect(0, 0, inner, 4000), flags, body)
    height = bounds.height() + 2 * margin

    image = QImage(QSize(width, height), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setFont(font)

    if outline > 0:
        # الحدّ يُرسم مسارًا لا نصًّا مكرّرًا: التكرار يترك حوافّ مسنّنة
        path = QPainterPath()
        line = margin + metrics.ascent()
        for row in _wrap(metrics, body, inner):
            span = metrics.horizontalAdvance(row)
            if align == "center":
                x = (width - span) / 2
            elif align == "left":
                x = margin
            else:
                x = width - margin - span
            path.addText(x, line, font, row)
            line += metrics.lineSpacing()
        painter.setPen(QPen(QColor(0, 0, 0, 210),
                            (outline / 100.0 * 9 + 1) * bump,
                            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.fillPath(path, QColor(colour))
    else:
        painter.setPen(QColor(colour))
        painter.drawText(QRect(margin, margin, inner, height), flags,
                         body)
    painter.end()

    image.save(target, "PNG")
    return target if os.path.exists(target) else None


def _wrap(metrics, body, width):
    """يقسم النصّ أسطرًا تسع العرض. يحترم أسطر المستخدم أوّلًا."""
    lines = []
    for paragraph in body.split("\n"):
        row = ""
        for word in paragraph.split(" "):
            trial = (row + " " + word).strip()
            if row and metrics.horizontalAdvance(trial) > width:
                lines.append(row)
                row = word
            else:
                row = trial
        lines.append(row)
    return lines


def sweep():
    """يمسح صور النصوص المتروكة من جلسة سابقة."""
    if not os.path.isdir(FOLDER):
        return
    for name in os.listdir(FOLDER):
        try:
            os.remove(os.path.join(FOLDER, name))
        except OSError:
            pass


def demo():
    """فحص ذاتي: العربية تُشبك، والصورة شفّافة، والخزن يعمل."""
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    theme.load_fonts()
    sweep()

    assert render("", 1920) is None and render("   ", 1920) is None

    path = render("مرحبا بالعالم", 1280, size=72)
    assert path and os.path.exists(path), "لم تُرسم صورة"
    image = QImage(path)
    assert image.width() == REFERENCE, image.width()
    assert image.hasAlphaChannel(), "الصورة بلا قناة شفافية"

    # شفافيّة حقيقية: الأركان فارغة والوسط فيه حبر
    assert image.pixelColor(3, 3).alpha() == 0, "الركن غير شفّاف"
    ink = sum(1 for y in range(0, image.height(), 3)
              for x in range(0, image.width(), 3)
              if image.pixelColor(x, y).alpha() > 40)
    assert ink > 200, "النصّ لم يُرسم فعلًا (%d بكسل)" % ink

    # الشبك: النصّ العربي المتّصل أضيق بكثير من حروفه منفصلة
    joined = QFontMetrics(_font(72)).horizontalAdvance("مرحبا")
    apart = sum(QFontMetrics(_font(72)).horizontalAdvance(ch)
                for ch in "مرحبا")
    assert joined < apart * 0.85, \
        "الحروف لا تُشبك: متّصلة %d مقابل منفصلة %d" % (joined, apart)
    print("الشبك العربي: «مرحبا» %d بكسل متّصلة مقابل %d منفصلة ✓"
          % (joined, apart))

    again = render("مرحبا بالعالم", 1280, size=72)
    assert again == path, "الخزن لم يُستعمل"

    # العرض المرجعيّ: نصٌّ بنسبة مقاسٍ واحدة إلى العرض يخرج صورةً واحدة
    # مهما كان مقاس المشروع. لولا ذلك لَلانت الحروف كلّما صُدّر المشروع
    # أكبر من مقاسه - 1080p يُصدَّر 1440p أو 4K.
    same = {render("نصّ اختبار", w, size=s) for w, s in
            ((1280, 40), (1920, 60), (2560, 80), (3840, 120))}
    assert len(same) == 1, "نسبة المقاس نفسها أعطت %d صورًا مختلفة" % len(same)
    drawn = QImage(same.pop())
    assert drawn.width() == REFERENCE, drawn.width()
    print("العرض المرجعيّ: أربعة مقاسات مشروع صورةٌ واحدة %dx%d ✓"
          % (drawn.width(), drawn.height()))

    other = render("مرحبا بالعالم", 1280, size=40)
    assert other != path, "مقاس مختلف أعطى الملف نفسه"

    tall = render("سطر أول\\nسطر ثانٍ\\nسطر ثالث", 1280, size=48)
    assert QImage(tall).height() > QImage(other).height(), \
        "الأسطر المتعدّدة لم تزد الارتفاع"
    print("الصورة: %dx%d · %d بكسل حبر" % (image.width(), image.height(), ink))
    print("gui/titles: كل الفحوص سليمة")
    app


def _font(size):
    font = QFont(theme.FONT_FAMILY)
    font.setPixelSize(size)
    font.setWeight(QFont.Bold)
    return font


if __name__ == "__main__":
    demo()
