"""
الملصقات: إيموجي النظام وأشكال مرسومة.

لا مكتبة ملصقات جاهزة: صور الملصقات المتداولة مملوكة لأصحابها، وشحنها مع
البرنامج تعدٍّ على حقوقهم. فالمصدران هنا نظيفان قانونيًّا - إيموجي يونيكود
يرسمه خطّ النظام، وأشكالٌ مرسومة في هذا الملف - ومن أراد ملصقًا خاصًّا
يستورده صورةً بزرّ «أضف كطبقة».

كل ملصق يُرسم صورةً شفّافة فيصير مقطعًا على طبقة، فيرث الموضع والحجم والحركة
والتحريك والفلاتر بلا سطرٍ جديد في التصدير - كما فعلت النصوص تمامًا.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QImage, QPainter,
                           QPainterPath, QPen)

FOLDER = os.path.join(tempfile.gettempdir(), "wun_cut_stickers")
EMOJI_FONT = "C:/Windows/Fonts/seguiemj.ttf"
SIZE = 512                  # مقاس الرسم؛ الطبقة تصغّره بحجمها

EMOJI = [
    ("تفاعلات", "😂 😭 😍 🥰 😱 😳 🤯 🥺 😎 🤔 😴 🤮"),
    ("إشارات", "🔥 💯 ✨ ⭐ 💥 ⚡ 🎯 👀 ❗ ❓ 🚨 ⏰"),
    ("أيادٍ", "👍 👎 👏 🙏 💪 👌 ✌️ 🤝 🤙 🤘"),
    ("ألعاب", "🎮 🏆 🥇 💀 ☠️ 🎧 🕹️ 🧠 💣 🎬"),
    ("قلوب", "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 💔 💖"),
]

SHAPES = [
    ("arrow_right", "سهم لليمين"),
    ("arrow_left", "سهم لليسار"),
    ("arrow_up", "سهم للأعلى"),
    ("arrow_down", "سهم للأسفل"),
    ("circle", "دائرة تمييز"),
    ("box", "مربّع تمييز"),
    ("bubble", "فقاعة كلام"),
    ("star", "نجمة"),
    ("tick", "علامة صحّ"),
    ("cross", "علامة خطأ"),
    ("burst", "انفجار"),
    ("underline", "خطّ تحته"),
]

SHAPE_KEYS = [key for key, _label in SHAPES]
SHAPE_LABELS = {key: label for key, label in SHAPES}
DEFAULT_COLOUR = "#FFD24A"

_emoji_family = None


def emoji_font(pixels):
    """
    خطّ الإيموجي الملوّن.

    يُحمَّل من ملفه صراحةً: قاعدة خطوط Qt لا تُدرجه في هذه البيئة، فرسمُه
    باسمه وحده يخرج أحاديّ اللون أو فارغًا.
    """
    global _emoji_family
    if _emoji_family is None:
        _emoji_family = "Segoe UI Emoji"
        if os.path.exists(EMOJI_FONT):
            fid = QFontDatabase.addApplicationFont(EMOJI_FONT)
            families = QFontDatabase.applicationFontFamilies(fid) \
                if fid != -1 else []
            if families:
                _emoji_family = families[0]
    font = QFont(_emoji_family)
    font.setPixelSize(int(pixels))
    return font


def all_emoji():
    """كل الإيموجي مسطّحًا، بترتيب أقسامه."""
    out = []
    for _title, row in EMOJI:
        out += row.split()
    return out


def _key(*parts):
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:14]


def render(kind, value, colour=DEFAULT_COLOUR):
    """يرسم ملصقًا صورةً شفّافة ويرجع مسارها، أو None عند الفشل."""
    target = os.path.join(FOLDER, "s_%s.png" % _key(kind, value, colour))
    if os.path.exists(target):
        return target
    os.makedirs(FOLDER, exist_ok=True)

    image = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)

    if kind == "emoji":
        painter.setFont(emoji_font(SIZE * 0.78))
        painter.drawText(QRectF(0, 0, SIZE, SIZE), Qt.AlignCenter, value)
    else:
        _draw_shape(painter, value, QColor(colour))
    painter.end()

    image.save(target, "PNG")
    return target if os.path.exists(target) else None


def _draw_shape(painter, name, colour):
    """
    الأشكال مرسومة لا مستوردة: خطٌّ داكن حول لونٍ ممتلئ، فتُقرأ على أي خلفية.

    الفيديو خلفيّة لا يملكها المصمّم: شكلٌ بلون واحد يذوب في مشهدٍ بلونه.
    """
    edge = QPen(QColor(0, 0, 0, 200), SIZE * 0.035, Qt.SolidLine, Qt.RoundCap,
                Qt.RoundJoin)
    path = QPainterPath()
    half = SIZE / 2.0
    span = SIZE * 0.36

    if name.startswith("arrow_"):
        path.moveTo(half - span, half - span * 0.34)
        path.lineTo(half + span * 0.18, half - span * 0.34)
        path.lineTo(half + span * 0.18, half - span * 0.72)
        path.lineTo(half + span, half)
        path.lineTo(half + span * 0.18, half + span * 0.72)
        path.lineTo(half + span * 0.18, half + span * 0.34)
        path.lineTo(half - span, half + span * 0.34)
        path.closeSubpath()
        turns = {"arrow_right": 0, "arrow_down": 90, "arrow_left": 180,
                 "arrow_up": 270}
        painter.translate(half, half)
        painter.rotate(turns.get(name, 0))
        painter.translate(-half, -half)
    elif name == "circle":
        path.addEllipse(QPointF(half, half), span, span)
        painter.setPen(QPen(colour, SIZE * 0.055, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        return
    elif name == "box":
        path.addRoundedRect(QRectF(half - span, half - span * 0.72,
                                   span * 2, span * 1.44), 18, 18)
        painter.setPen(QPen(colour, SIZE * 0.055, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        return
    elif name == "bubble":
        path.addRoundedRect(QRectF(half - span, half - span * 0.78,
                                   span * 2, span * 1.32), 40, 40)
        tail = QPainterPath()
        tail.moveTo(half - span * 0.34, half + span * 0.52)
        tail.lineTo(half - span * 0.10, half + span * 0.96)
        tail.lineTo(half + span * 0.10, half + span * 0.52)
        tail.closeSubpath()
        path = path.united(tail)
    elif name == "star":
        import math
        for step in range(10):
            radius = span if step % 2 == 0 else span * 0.44
            angle = math.pi / 5 * step - math.pi / 2
            point = QPointF(half + radius * math.cos(angle),
                            half + radius * math.sin(angle))
            path.lineTo(point) if step else path.moveTo(point)
        path.closeSubpath()
    elif name == "tick":
        painter.setPen(QPen(colour, SIZE * 0.09, Qt.SolidLine, Qt.RoundCap,
                            Qt.RoundJoin))
        painter.drawPolyline([QPointF(half - span * 0.8, half),
                              QPointF(half - span * 0.2, half + span * 0.6),
                              QPointF(half + span * 0.85, half - span * 0.6)])
        return
    elif name == "cross":
        painter.setPen(QPen(colour, SIZE * 0.09, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(half - span * 0.7, half - span * 0.7),
                         QPointF(half + span * 0.7, half + span * 0.7))
        painter.drawLine(QPointF(half + span * 0.7, half - span * 0.7),
                         QPointF(half - span * 0.7, half + span * 0.7))
        return
    elif name == "burst":
        import math
        for step in range(16):
            radius = span if step % 2 == 0 else span * 0.52
            angle = math.pi / 8 * step
            point = QPointF(half + radius * math.cos(angle),
                            half + radius * math.sin(angle))
            path.lineTo(point) if step else path.moveTo(point)
        path.closeSubpath()
    elif name == "underline":
        painter.setPen(QPen(colour, SIZE * 0.10, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(half - span, half + span * 0.3),
                         QPointF(half + span, half + span * 0.3))
        return
    else:
        return

    painter.setPen(edge)
    painter.setBrush(colour)
    painter.drawPath(path)


def sweep():
    if not os.path.isdir(FOLDER):
        return
    for name in os.listdir(FOLDER):
        try:
            os.remove(os.path.join(FOLDER, name))
        except OSError:
            pass


def demo():
    """فحص ذاتي: كل ملصق يُرسم، شفّافًا، وله حبر."""
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    sweep()

    def ink_and_colours(path):
        image = QImage(path)
        ink, seen = 0, set()
        for y in range(0, image.height(), 4):
            for x in range(0, image.width(), 4):
                pixel = image.pixelColor(x, y)
                if pixel.alpha() > 60:
                    ink += 1
                    seen.add((pixel.red() // 45, pixel.green() // 45,
                              pixel.blue() // 45))
        return image, ink, len(seen)

    # نسأل الخطّ مباشرةً: الرمز الذي لا يحمله يُرسم مربّعًا فارغًا، وفيه حبرٌ
    # يكفي لاجتياز فحص الحبر. وعدّ الألوان لا يصلح بديلًا: ⚡ صحيحٌ ولونه
    # واحد تقريبًا، فيسقط ظلمًا.
    from PySide6.QtGui import QRawFont

    raw = QRawFont.fromFont(emoji_font(64))
    absent = [g for g in all_emoji() if not raw.supportsCharacter(ord(g[0]))]
    assert not absent, "رموز لا يحملها خطّ النظام: %s" % absent

    for glyph in all_emoji():
        path = render("emoji", glyph)
        assert path, "تعذّر رسم %s" % glyph
        image, ink, _colours = ink_and_colours(path)
        assert image.hasAlphaChannel() and image.pixelColor(2, 2).alpha() == 0
        assert ink >= 120, "%s بلا حبر كافٍ (%d)" % (glyph, ink)

    # وملوّن: خطٌّ أحاديّ يجعل كل الملصقات ظِلالًا
    assert ink_and_colours(render("emoji", "🔥"))[2] >= 4,         "الإيموجي يُرسم أحاديّ اللون"

    for key in SHAPE_KEYS:
        path = render("shape", key)
        assert path, key
        image, ink, _c = ink_and_colours(path)
        assert image.pixelColor(2, 2).alpha() == 0, "%s بلا شفافية" % key
        assert ink > 120, "%s بلا حبر كافٍ (%d)" % (key, ink)

    # اللون يغيّر الملف والنتيجة
    gold = render("shape", "star", "#FFD24A")
    blue = render("shape", "star", "#29A9E2")
    assert gold != blue, "اللون لم يدخل مفتاح الخزن"
    assert render("shape", "star", "#FFD24A") == gold, "الخزن لم يُستعمل"
    assert render("shape", "لا-يوجد") and \
        ink_and_colours(render("shape", "لا-يوجد"))[1] == 0, \
        "شكل مجهول رسم شيئًا"

    print("gui/stickers: كل الفحوص سليمة (%d إيموجي · %d شكلًا)"
          % (len(all_emoji()), len(SHAPE_KEYS)))
    app


if __name__ == "__main__":
    demo()
