"""
الانتقالات بين مقطعين متجاورين.

المصيدة في xfade: يبتلع مدّة الانتقال من الطول الكلّي، فيخرج الملف أقصر ممّا
يعرضه الخط الزمني. الحلّ أن يُمَدّ المقطع الخارج بمقدار الانتقال من ذيل ملفه
المصدر - وهو موجود غالبًا لأن المستخدم قصّه - فيصير:

    (d1 + D) + d2 - D = d1 + d2

أي أن المدّة تُحفظ تمامًا. وإن نفد المصدر يُستنسخ آخر إطار (tpad) فلا ينقص
شيء في كل الأحوال.
"""

from __future__ import annotations

import os
from . import tools

# المفتاح، التسمية، اسم الانتقال في xfade
TRANSITIONS = [
    ("", "بلا انتقال", None),
    ("fade", "تلاشٍ", "fade"),
    ("fadeblack", "تلاشٍ عبر الأسود", "fadeblack"),
    ("fadewhite", "تلاشٍ عبر الأبيض", "fadewhite"),
    ("dissolve", "ذوبان", "dissolve"),
    ("slideleft", "انزلاق لليسار", "slideleft"),
    ("slideright", "انزلاق لليمين", "slideright"),
    ("slideup", "انزلاق للأعلى", "slideup"),
    ("slidedown", "انزلاق للأسفل", "slidedown"),
    ("wipeleft", "مسح لليسار", "wipeleft"),
    ("wiperight", "مسح لليمين", "wiperight"),
    ("circleopen", "دائرة تتّسع", "circleopen"),
    ("circleclose", "دائرة تنغلق", "circleclose"),
    ("radial", "دوران", "radial"),
    ("pixelize", "تبقّع", "pixelize"),
    ("smoothleft", "انسياب لليسار", "smoothleft"),

    # بقيّةُ ما يعطيه xfade. كانت الأداة تعرض خمسة عشر من ثمانيةٍ وخمسين،
    # والباقي مجّانًا: منها عائلةُ التغطية والكشف، وهي أقربُ ما في المرشّح
    # إلى إحساس العمق، ومنها العصرُ والاندفاع.
    ("wipeup", "مسح للأعلى", "wipeup"),
    ("wipedown", "مسح للأسفل", "wipedown"),
    ("circlecrop", "قصٌّ دائري", "circlecrop"),
    ("rectcrop", "قصٌّ مستطيل", "rectcrop"),
    ("distance", "تباعد", "distance"),
    ("smoothright", "انسياب لليمين", "smoothright"),
    ("smoothup", "انسياب للأعلى", "smoothup"),
    ("smoothdown", "انسياب للأسفل", "smoothdown"),
    ("vertopen", "فتحٌ رأسي", "vertopen"),
    ("vertclose", "إغلاقٌ رأسي", "vertclose"),
    ("horzopen", "فتحٌ أفقي", "horzopen"),
    ("horzclose", "إغلاقٌ أفقي", "horzclose"),
    ("diagtl", "قطريّ من أعلى اليسار", "diagtl"),
    ("diagtr", "قطريّ من أعلى اليمين", "diagtr"),
    ("diagbl", "قطريّ من أسفل اليسار", "diagbl"),
    ("diagbr", "قطريّ من أسفل اليمين", "diagbr"),
    ("hlslice", "شرائح لليسار", "hlslice"),
    ("hrslice", "شرائح لليمين", "hrslice"),
    ("vuslice", "شرائح للأعلى", "vuslice"),
    ("vdslice", "شرائح للأسفل", "vdslice"),
    ("hblur", "ضبابٌ أفقي", "hblur"),
    ("fadegrays", "تلاشٍ عبر الرمادي", "fadegrays"),
    ("wipetl", "مسح من أعلى اليسار", "wipetl"),
    ("wipetr", "مسح من أعلى اليمين", "wipetr"),
    ("wipebl", "مسح من أسفل اليسار", "wipebl"),
    ("wipebr", "مسح من أسفل اليمين", "wipebr"),
    ("squeezeh", "عصرٌ أفقي", "squeezeh"),
    ("squeezev", "عصرٌ رأسي", "squeezev"),
    ("zoomin", "اندفاعٌ للداخل", "zoomin"),
    ("fadefast", "تلاشٍ سريع", "fadefast"),
    ("fadeslow", "تلاشٍ بطيء", "fadeslow"),
    ("hlwind", "ريحٌ لليسار", "hlwind"),
    ("hrwind", "ريحٌ لليمين", "hrwind"),
    ("vuwind", "ريحٌ للأعلى", "vuwind"),
    ("vdwind", "ريحٌ للأسفل", "vdwind"),
    ("coverleft", "تغطيةٌ لليسار", "coverleft"),
    ("coverright", "تغطيةٌ لليمين", "coverright"),
    ("coverup", "تغطيةٌ للأعلى", "coverup"),
    ("coverdown", "تغطيةٌ للأسفل", "coverdown"),
    ("revealleft", "كشفٌ لليسار", "revealleft"),
    ("revealright", "كشفٌ لليمين", "revealright"),
    ("revealup", "كشفٌ للأعلى", "revealup"),
    ("revealdown", "كشفٌ للأسفل", "revealdown"),
]

NAMES = [key for key, _label, _mode in TRANSITIONS]
LABELS = {key: label for key, label, _mode in TRANSITIONS}
_MODES = {key: mode for key, _label, mode in TRANSITIONS}

MIN_MS, MAX_MS, DEFAULT_MS = 100, 3000, 600


def mode(name):
    """اسم الانتقال في xfade، أو None إن لم يكن انتقالًا معروفًا."""
    return _MODES.get(name or "")


def window(clip, seconds, following):
    """
    مدّة الانتقال بالثواني، مقصوصةً حتى لا تبتلع مقطعًا كاملًا.

    انتقالٌ أطول من أقصر المقطعين يجعل xfade يرفض الرسم البياني كلّه، فنقصّه
    إلى نصف الأقصر منهما.
    """
    if not mode(clip.trans):
        return 0.0
    wanted = clip.effect("trans_ms") / 1000.0
    return max(0.04, min(wanted, seconds * 0.5, following * 0.5))


def demo():
    """فحص ذاتي: الأسماء والقصّ."""
    class Fake:
        def __init__(self, name, ms):
            self.trans = name
            self._ms = ms

        def effect(self, _name):
            return self._ms

    assert NAMES[0] == "" and len(NAMES) == 59
    assert mode("") is None and mode("لا-يوجد") is None
    assert mode("fade") == "fade" and mode("circleopen") == "circleopen"

    assert window(Fake("", 600), 5, 5) == 0.0, "بلا انتقال أنتج مدّة"
    assert abs(window(Fake("fade", 600), 5, 5) - 0.6) < 1e-9

    # أطول من المقطع: يُقصّ إلى نصف الأقصر
    assert abs(window(Fake("fade", 3000), 1.0, 8) - 0.5) < 1e-9
    assert abs(window(Fake("fade", 3000), 8, 0.8) - 0.4) < 1e-9
    # ولا ينزل إلى الصفر فيُنتج مرشّحًا بمدّة صفرية
    assert window(Fake("fade", 3000), 0.0, 5) >= 0.04

    # --- كل اسمٍ نعرضه يقبله xfade فعلًا ---
    #
    # الجدول يُكتب باليد، وحرفٌ واحدٌ خطأ يجعل FFmpeg يرفض الرسم البياني
    # كلَّه عند التصدير - لا عند الاختيار. فتُقرأ قائمةُ المرشّح نفسه.
    import re
    import subprocess
    listing = subprocess.run(
        [tools.ffmpeg(), "-hide_banner", "-h", "filter=xfade"],
        capture_output=True, text=True,
        creationflags=0x08000000 if os.name == "nt" else 0).stdout
    real = set(re.findall(r"^     ([a-z]+)\s", listing, re.M))
    assert len(real) > 40, "لم تُقرأ قائمة xfade: %d" % len(real)
    unknown = {mode for mode in _MODES.values() if mode} - real
    assert not unknown, "أسماءٌ لا يعرفها xfade: %s" % sorted(unknown)
    print("كل الأسماء يقبلها xfade: %d من %d متاحًا ✓"
          % (len(NAMES) - 1, len(real) - 1))

    print("core/transitions: كل الفحوص سليمة (%d انتقالًا)" % (len(NAMES) - 1))


if __name__ == "__main__":
    demo()
