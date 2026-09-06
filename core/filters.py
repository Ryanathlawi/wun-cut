"""
الفلاتر البصرية: مظهر المقطع بنقرة.

جدولٌ لا شفرة، مثل الحركات: كل فلتر سطرٌ فيه قالب مرشّح FFmpeg وشدّة واحدة
تتحكّم فيه. زيادة فلتر جديد صفٌّ لا دالّة.

الشدّة تصل بقيمة 0..100 من الواجهة، ويحوّلها كل قالب إلى مدى مرشّحه: مدى
gblur غير مدى noise غير مدى vignette، والمستخدم لا يعنيه ذلك.
"""

from __future__ import annotations

# المفتاح، التسمية، دالّة تبني سلسلة المرشّحات من الشدّة 0..1
FILTERS = [
    ("", "بلا فلتر", None),
    ("blur", "ضبابية", lambda v: ["gblur=sigma=%.2f" % (0.4 + v * 11)]),
    ("sharpen", "حِدّة",
     lambda v: ["unsharp=5:5:%.2f:5:5:0" % (0.2 + v * 1.8)]),
    ("vignette", "تعتيم الأطراف",
     lambda v: ["vignette=angle=%.3f" % (0.9 - v * 0.55)]),
    ("grain", "حبيبات فيلم",
     lambda v: ["noise=alls=%d:allf=t+u" % max(1, int(4 + v * 34))]),
    ("warm", "دافئ",
     lambda v: ["colorbalance=rs=%.3f:rm=%.3f:bs=%.3f:bm=%.3f"
                % (v * 0.30, v * 0.22, -v * 0.24, -v * 0.16)]),
    ("cool", "بارد",
     lambda v: ["colorbalance=rs=%.3f:rm=%.3f:bs=%.3f:bm=%.3f"
                % (-v * 0.26, -v * 0.18, v * 0.30, v * 0.22)]),
    ("sepia", "بنّي قديم",
     lambda v: ["colorchannelmixer="
                "%.3f:%.3f:%.3f:0:%.3f:%.3f:%.3f:0:%.3f:%.3f:%.3f"
                % (1 - v * 0.607, v * 0.769, v * 0.189,
                   v * 0.349, 1 - v * 0.314, v * 0.168,
                   v * 0.272, v * 0.534, 1 - v * 0.869)]),
    ("faded", "باهت",
     lambda v: ["curves=all='0/%.3f 0.5/0.5 1/%.3f'"
                % (v * 0.22, 1 - v * 0.12)]),
    ("contrast_pop", "ألوان صارخة",
     lambda v: ["eq=saturation=%.3f:contrast=%.3f"
                % (1 + v * 0.9, 1 + v * 0.45)]),
    ("mirror", "انعكاس أفقي", lambda _v: ["hflip"]),
]

NAMES = [key for key, _label, _make in FILTERS]
LABELS = {key: label for key, label, _make in FILTERS}
_MAKERS = {key: make for key, _label, make in FILTERS}

MIN, MAX, DEFAULT = 0, 100, 60


def chain(name, amount):
    """سلسلة مرشّحات FFmpeg للفلتر بشدّته، أو قائمة فارغة بلا فلتر."""
    make = _MAKERS.get(name or "")
    if make is None:
        return []
    return make(max(0, min(100, int(amount))) / 100.0)


def demo():
    """فحص ذاتي: كل فلتر يبني سلسلة صالحة عند طرفَي الشدّة."""
    assert NAMES[0] == "" and len(NAMES) == 11
    assert chain("", 50) == [] and chain("لا-يوجد", 50) == []

    for key in NAMES[1:]:
        for amount in (0, 1, 50, 99, 100):
            built = chain(key, amount)
            assert built and isinstance(built, list), (key, amount)
            text = ",".join(built)
            assert "=" in text or text == "hflip", (key, text)
            assert "nan" not in text.lower() and "inf" not in text.lower()
            # لا أرقام هاربة: كل قيمة تُصاغ بدقّة محدودة
            assert "e-" not in text and "e+" not in text, (key, text)

    # الشدّة تُقصّ إلى مداها بدل أن تخرج عنه
    assert chain("blur", 500) == chain("blur", 100)
    assert chain("blur", -50) == chain("blur", 0)
    # وتؤثّر فعلًا: طرفا المدى لا ينتجان الشيء نفسه
    for key in NAMES[1:]:
        if key == "mirror":
            continue
        assert chain(key, 0) != chain(key, 100), "%s لا يتأثّر بالشدّة" % key

    print("core/filters: كل الفحوص سليمة (%d فلتر)" % (len(NAMES) - 1))


if __name__ == "__main__":
    demo()
