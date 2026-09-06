"""
توليد أيقونة وِن كَت (assets/app.ico).

    python build_tools/make_icon.py

الأيقونة مختلفة عن وِن ستوديو عمدًا: تلك دائرةٌ فيها شعار Wun، وهذه مربّعٌ
مستدير فيه مثلّث تشغيلٍ مشقوقٌ بقطع - فلا يلتبس البرنامجان على المستخدم في
قائمة ابدأ ولا على شريط المهامّ. واللون من لوحة العلامة نفسها فتبقى القرابة.

الشقّ مائلٌ لا رأسيّ: عند ستّة عشر بكسلًا يبقى المثلّث مقروءًا والشقُّ يُرى
خطًّا واحدًا، بينما الشقّ الرأسيّ يجعله مثلّثين صغيرين لا يُعرف ما هما.
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "app.ico")
# نسخةٌ PNG للنشر: المتاجر والمواقع والبوّابات تطلبها لا .ico
PNG = os.path.join(ROOT, "assets", "app_512.png")
PNG_SIZE = 512

BIG = 1024                      # يُرسم كبيرًا ثم يُصغَّر: الحواف تنعم
SIZES = (16, 24, 32, 48, 64, 128, 256)
TOP = (61, 190, 244)            # أزرق العلامة الفاتح
BOTTOM = (18, 74, 132)          # وقاعدته الغامقة
INK = (255, 255, 255)


def rounded(size, radius):
    """قناعٌ لمربّعٍ مستدير."""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                           radius=radius, fill=255)
    return mask


def gradient(size, top, bottom):
    strip = Image.new("RGB", (1, size))
    for y in range(size):
        k = y / max(1, size - 1)
        strip.putpixel((0, y), tuple(
            int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    return strip.resize((size, size))


def build():
    plate = gradient(BIG, TOP, BOTTOM).convert("RGBA")
    plate.putalpha(rounded(BIG, int(BIG * 0.22)))

    # مثلّث التشغيل
    mark = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    pen = ImageDraw.Draw(mark)
    left, right = BIG * 0.34, BIG * 0.74
    top, bottom = BIG * 0.26, BIG * 0.74
    pen.polygon([(left, top), (right, BIG * 0.5), (left, bottom)], fill=INK)

    # الشقّ: خطٌّ مائل يُمحى من المثلّث فيبدو مقصوصًا
    cut = Image.new("L", (BIG, BIG), 255)
    ImageDraw.Draw(cut).line([(BIG * 0.20, BIG * 0.70), (BIG * 0.86, BIG * 0.24)],
                             fill=0, width=int(BIG * 0.075))
    mark.putalpha(Image.composite(mark.getchannel("A"),
                                  Image.new("L", (BIG, BIG), 0), cut))

    plate.alpha_composite(mark)
    plate.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    plate.resize((PNG_SIZE, PNG_SIZE), Image.LANCZOS).save(PNG, format="PNG")
    return plate


def demo():
    """فحص ذاتي: الأيقونة تُكتب، وتختلف عن شعار وِن ستوديو."""
    plate = build()
    assert os.path.exists(OUT), "لم تُكتب الأيقونة"
    made = Image.open(OUT)
    assert made.size in [(s, s) for s in SIZES], made.size

    # الأركان شفّافة - مربّعٌ مستدير لا مربّعٌ صلب
    small = plate.resize((64, 64), Image.LANCZOS)
    assert small.getpixel((1, 1))[3] < 40, "الركن غير شفّاف"
    # وفيه حبرٌ أبيض في الوسط: المثلّث ظاهر
    middle = small.crop((18, 18, 46, 46)).convert("RGBA")
    white = sum(1 for p in middle.getdata() if p[3] > 200 and p[0] > 200)
    assert white > 60, "المثلّث لا يُرى: %d بكسل" % white
    # والشقّ يقطعه: صفٌّ في منتصف المثلّث فيه فجوة
    row = [small.getpixel((x, 32)) for x in range(20, 46)]
    lit = [1 if (p[3] > 200 and p[0] > 200) else 0 for p in row]
    gaps = sum(1 for i in range(1, len(lit)) if lit[i] != lit[i - 1])
    assert gaps >= 3, "الشقّ لا يقطع المثلّث: %s" % lit
    print("الأيقونة: %d مقاسًا · مثلّثٌ مشقوق (%d تحوّلًا في الصفّ) ✓"
          % (len(SIZES), gaps))
    shot = Image.open(PNG)
    assert shot.size == (PNG_SIZE, PNG_SIZE), shot.size
    assert shot.mode == "RGBA" and shot.getpixel((2, 2))[3] < 40,         "النسخة PNG بلا شفافية"
    print("النسخة PNG: %dx%d بشفافية ✓" % shot.size)
    print("build_tools/make_icon: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
