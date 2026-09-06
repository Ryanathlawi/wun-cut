"""
ما يجعل الخط الزمني يُقرأ بالنظر: شريط إطارات للفيديو، وموجة للصوت.

بلا هذين يبقى المقطع مستطيلًا ملوّنًا عليه اسم ملف، فلا يعرف المحرِّر أين
يقصّ إلا بالتشغيل والتخمين. هذا هو الفرق بين واجهة تعرض بيانات وواجهة يُحرَّر
فيها فعلًا.

الاستخلاص بطيء (ثوانٍ) فيُخزَّن في مجلد مؤقّت بمفتاح يضمّ حجم الملف ووقت
تعديله: لو استُبدل الملف بآخر بالاسم نفسه بطل المفتاح ولم تُعرض صور قديمة.
"""

from __future__ import annotations

import array
import hashlib
import os
import subprocess
import tempfile
from . import tools

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CACHE = os.path.join(tempfile.gettempdir(), "wun_cut_cache")
STRIP_H = 48                # ارتفاع الإطار الواحد في الشريط
PEAK_RATE = 4000            # يكفي للرسم: الموجة شكل لا صوت


def _key(path, *parts):
    """هوية الملف: مساره وحجمه ووقت تعديله، مع معاملات الطلب."""
    try:
        stat = os.stat(path)
        stamp = "%d-%d" % (stat.st_size, int(stat.st_mtime))
    except OSError:
        stamp = "0"
    raw = "|".join([os.path.abspath(path), stamp] + [str(p) for p in parts])
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def _run(args, capture=False):
    return subprocess.run(args, stdout=subprocess.PIPE if capture
                          else subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)


def filmstrip(path, duration, count=24, height=STRIP_H):
    """
    صورة واحدة فيها `count` إطارًا متتاليًا جنبًا إلى جنب.

    تجميعها في ملف واحد بمرشّح tile بدل استدعاء ffmpeg لكل إطار: قراءة الملف
    مرّة واحدة تكفي، والفارق عشرات المرّات على مقطع طويل.
    """
    count = max(1, min(int(count), 240))
    if duration <= 0:
        return None
    target = os.path.join(CACHE, "strip_%s.jpg"
                          % _key(path, count, height, "%.2f" % duration))
    if os.path.exists(target):
        return target

    os.makedirs(CACHE, exist_ok=True)
    rate = count / float(duration)
    result = _run([tools.ffmpeg(), "-y", "-v", "error", "-i", path,
                   "-vf", "fps=%.6f,scale=-2:%d,tile=%dx1" % (rate, height,
                                                              count),
                   "-frames:v", "1", "-q:v", "4", target])
    if result.returncode != 0 or not os.path.exists(target):
        return None
    return target


def peaks(path, buckets=1200):
    """
    ذروة الصوت لكل دلو، مقياسها 0..1 بعد التطبيع على أعلى ذروة في المقطع.

    التطبيع ضروري لا تجميلي: تسجيلات كثيرة تبلغ ذروتها 0.08 من المدى الكامل،
    فالرسم الخطّي يعطي خطًّا مسطّحًا لا يدلّ على شيء.
    """
    buckets = max(16, min(int(buckets), 20000))
    cached = os.path.join(CACHE, "peaks_%s.bin" % _key(path, buckets))
    if os.path.exists(cached):
        data = array.array("B")
        with open(cached, "rb") as handle:
            data.frombytes(handle.read())
        return [v / 255.0 for v in data]

    os.makedirs(CACHE, exist_ok=True)
    result = _run([tools.ffmpeg(), "-v", "error", "-i", path, "-map", "0:a:0",
                   "-ac", "1", "-ar", str(PEAK_RATE), "-f", "s16le", "-"],
                  capture=True)
    if result.returncode != 0 or not result.stdout:
        return []

    samples = array.array("h")
    raw = result.stdout
    samples.frombytes(raw[:len(raw) // 2 * 2])
    if not samples:
        return []

    step = max(1, len(samples) // buckets)
    out = []
    for start in range(0, len(samples), step):
        window = samples[start:start + step]
        out.append(max(max(window), -min(window)) if window else 0)

    ceiling = max(out) or 1
    scaled = array.array("B", [min(255, v * 255 // ceiling) for v in out])
    with open(cached, "wb") as handle:
        handle.write(scaled.tobytes())
    return [v / 255.0 for v in scaled]


def clear():
    """يفرغ مجلد المعاينات. للصيانة، لا يُستدعى من الواجهة."""
    if not os.path.isdir(CACHE):
        return 0
    gone = 0
    for name in os.listdir(CACHE):
        try:
            os.remove(os.path.join(CACHE, name))
            gone += 1
        except OSError:
            pass
    return gone


def demo():
    """فحص ذاتي: يحتاج ملفًا حقيقيًا في سطر الأوامر."""
    import sys

    assert _key("a.mp4", 1) != _key("a.mp4", 2), "المعاملات لا تدخل المفتاح"
    assert filmstrip("لا-يوجد.mp4", 10) is None, "ملف مفقود لم يرجع None"
    assert peaks("لا-يوجد.mp4") == [], "ملف مفقود لم يرجع قائمة فارغة"
    assert filmstrip("a.mp4", 0) is None, "مدّة صفر لم تُرفض"

    if len(sys.argv) > 1:
        source = sys.argv[1]
        sys.path.insert(0, os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        from wun_cut.core import media

        info = media.probe(source)
        strip = filmstrip(source, info.duration, 24)
        assert strip and os.path.exists(strip), "تعذّر بناء الشريط"
        size = _run([tools.ffprobe(), "-v", "error", "-select_streams", "v",
                     "-show_entries", "stream=width,height", "-of", "csv=p=0",
                     strip], capture=True).stdout.decode().strip()
        print("الشريط: %s بكسل · %.1f ك.ب" % (size, os.path.getsize(strip) / 1e3))
        assert size.endswith(str(STRIP_H)), size

        again = filmstrip(source, info.duration, 24)
        assert again == strip, "الخزن لم يُستعمل"
        print("الطلب الثاني من الخزن ✓")

        values = peaks(source, 300)
        if info.has_audio:
            assert values, "لا ذرى رغم وجود صوت"
            assert 0.99 <= max(values) <= 1.0, max(values)
            assert len(values) <= 320, len(values)
            print("الموجة: %d دلوًا · أعلى %.2f · متوسّط %.2f"
                  % (len(values), max(values),
                     sum(values) / len(values)))

    print("core/preview: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
