"""
مخزن معاينات الخط الزمني: شريط الإطارات وموجة الصوت لكل ملف مصدر.

الاستخلاص يستغرق ثوانيَ، فلا يجوز أن يقع في خيط الواجهة: نافذة تتجمّد أربع
ثوانٍ عند إفلات ملف تبدو معطّلة. الطلب يذهب إلى مجمّع خيوط، والرسم يستعمل ما
وصل ويُعاد عند وصول الباقي.

البيانات محفوظة بالمصدر لا بالمقطع: عشرة مقاطع مقصوصة من ملف واحد تتشارك
شريطًا واحدًا، ويقتطع كلٌّ منها ما يخصّه عند الرسم.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QPixmap

from ..core import media, preview

STRIP_TILES = 60            # عدد الإطارات في شريط الملف الواحد
WAVE_BUCKETS = 1500
MAX_JOBS = 2                # استدعاءا ffmpeg متزامنان يكفيان ولا يخنقان القرص


class _Signals(QObject):
    done = Signal(str, object, object, float)   # مصدر، شريط، موجة، مدّة


class _Job(QRunnable):
    """يقرأ ملفًا واحدًا: مدّته وشريطه وموجته."""

    def __init__(self, source, signals):
        super().__init__()
        self.source = source
        self.signals = signals

    def run(self):
        strip = wave = None
        duration = 0.0
        try:
            info = media.probe(self.source)
            duration = info.duration
            if info.has_video and duration > 0:
                strip = preview.filmstrip(self.source, duration, STRIP_TILES)
            if info.has_audio:
                wave = preview.peaks(self.source, WAVE_BUCKETS) or None
        except Exception:
            # ملف تالف أو محذوف: الخط الزمني يرسم المقطع سادةً ويستمر
            pass
        self.signals.done.emit(self.source, strip, wave, duration)


class PreviewStore(QObject):
    """يُسأل عند الرسم، ويجيب بما عنده الآن."""

    ready = Signal(str)         # المصدر الذي وصلت معاينته

    def __init__(self, parent=None):
        super().__init__(parent)
        self._strips = {}       # مصدر -> QPixmap أو None
        self._waves = {}        # مصدر -> list[float] أو None
        self._spans = {}        # مصدر -> مدّة الملف بالثواني
        self._asked = set()
        self._signals = _Signals()
        self._signals.done.connect(self._store)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(MAX_JOBS)

    def request(self, source):
        """يطلب معاينة ملف مرّة واحدة فقط."""
        if source in self._asked:
            return
        self._asked.add(source)
        self._pool.start(_Job(source, self._signals))

    def _store(self, source, strip, wave, duration):
        self._strips[source] = QPixmap(strip) if strip else None
        self._waves[source] = wave
        self._spans[source] = duration
        self.ready.emit(source)

    # ما يستعمله الرسم: يطلب ضمنًا ثم يرجع ما توفّر

    def strip(self, source):
        self.request(source)
        return self._strips.get(source)

    def wave(self, source):
        self.request(source)
        return self._waves.get(source)

    def span(self, source):
        """مدّة الملف بالثواني، أو 0 إن لم تصل بعد."""
        self.request(source)
        return self._spans.get(source, 0.0)

    def forget(self, source):
        for store in (self._strips, self._waves, self._spans):
            store.pop(source, None)
        self._asked.discard(source)

    def wait(self, ms=60000):
        """للفحوص وحدها: ينتظر انتهاء كل الطلبات."""
        return self._pool.waitForDone(ms)


def demo():
    """فحص ذاتي: يحتاج ملفًا حقيقيًا في سطر الأوامر."""
    import os
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    store = PreviewStore()

    assert store.strip("لا-يوجد.mp4") is None
    store.wait(20000)
    app.processEvents()
    assert "لا-يوجد.mp4" in store._spans, "الملف المفقود لم يُسجَّل كمنتهٍ"
    assert store.span("لا-يوجد.mp4") == 0.0

    if len(sys.argv) > 1:
        source = sys.argv[1]
        assert store.strip(source) is None, "أجاب فورًا بدل أن يطلب"
        store.wait(60000)
        app.processEvents()

        strip = store.strip(source)
        assert strip is not None and not strip.isNull(), "لم يصل الشريط"
        assert strip.height() == preview.STRIP_H, strip.height()
        print("الشريط: %dx%d · %d إطارًا"
              % (strip.width(), strip.height(),
                 round(strip.width() / (strip.height() * 16 / 9))))
        assert store.span(source) > 0, "المدّة لم تصل"

        wave = store.wave(source)
        if wave:
            print("الموجة: %d دلوًا · أعلى %.2f" % (len(wave), max(wave)))
            assert max(wave) <= 1.0

        before = len(store._asked)
        store.strip(source)
        assert len(store._asked) == before, "طلب المصدر مرّتين"
        print("الطلب لا يتكرّر ✓")

    print("gui/previews: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
