"""
منطقة المعاينة: صورة حيّة عند التوقّف، وفيديو حيّ عند التشغيل.

الصورة تُرسم بمرشّحات التصدير نفسها (core.export.still)، فما يراه المصمّم هو
ما يخرج في الملف. الطريق الآخر - أن ترسم الواجهة التأثيرات بنفسها - أسرع لكنه
يعني منطقَين للشيء الواحد ينحرف أحدهما عن الآخر بصمت.

الرسم في خيط منفصل ومؤجَّل: سحبة منزلق تبثّ عشرات التغييرات في الثانية، ولو
رسمنا لكل واحدة لاصطفّت الطلبات وتأخّرت الصورة عن اليد.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (QLabel, QProgressBar, QPushButton,
                               QStackedLayout, QVBoxLayout, QWidget)

from ..core import export
from ..i18n import t
from . import theme

DELAY = 110                 # مللي ثانية بعد آخر تغيير قبل الرسم
PREVIEW_W = 720
PROXY_W = 854        # عرض معاينة التشغيل: يكفي للحكم ولا يُبطئ الترميز


class _Render(QThread):
    """رسمة واحدة. لا تلمس الواجهة: ترجع مسار الملف بإشارة."""

    done = Signal(str, int)         # المسار، الإطار المطلوب

    def __init__(self, project, frame, target, parent=None):
        super().__init__(parent)
        self.project = project
        self.frame = frame
        self.target = target

    def run(self):
        try:
            ok = export.still(self.project, self.frame, self.target,
                              PREVIEW_W)
        except Exception:
            ok = False          # مسار نادر: ملف تالف أو ffmpeg مفقود
        if not ok:
            # الرسم الفاشل يترك ملفًّا ناقصًا: ffmpeg يفتح الخرج قبل أن
            # يعرف أنه سيفشل. من طلب الكتابة يمسحها - المستقبِل يرى مسارًا
            # فارغًا فلا يعرف ما يمسح، فتبقى الصورة في المؤقّت إلى نهاية
            # الجلسة.
            try:
                os.remove(self.target)
            except OSError:
                pass
        self.done.emit(self.target if ok else "", self.frame)


class _Proxy(QThread):
    """
    يرمّز الخط الزمني كاملًا بدقّة منخفضة ليُشغَّل بتأثيراته.

    التشغيل الحيّ بمرشّحات التصدير مستحيل: ستّون استدعاءً لـ ffmpeg في الثانية.
    والبديل - رسم التأثيرات في الواجهة - منطقٌ ثانٍ ينحرف عن الملف الناتج.
    فنرمّز مرّة ونشغّل الناتج: بطيء أوّل مرّة، وصادق دائمًا.
    """

    done = Signal(str)
    progress = Signal(int, int)

    def __init__(self, project, target, parent=None):
        super().__init__(parent)
        self.project = project
        self.target = target
        self.job = None
        self._stop = False

    def cancel(self):
        self._stop = True
        if self.job is not None:
            self.job.cancel()

    def run(self):
        project = self.project
        ratio = project.height / float(project.width or 1)
        size = (PROXY_W, max(2, int(PROXY_W * ratio) // 2 * 2))
        found = export.encoders()
        try:
            self.job = export.ExportJob(
                project, self.target, quality=35, scale=size,
                encoder=found[0][0] if found else "libx264")
        except Exception:
            self.done.emit("")
            return
        try:
            ok = self.job.run(on_progress=self._tick)
        except Exception:
            ok = False
        self.done.emit(self.target if ok and not self._stop else "")

    def _tick(self, done, total):
        self.progress.emit(done, total)
        return not self._stop


class Stage(QWidget):
    """يبدّل بين صورة المعاينة وودجت الفيديو."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self._pending = None        # آخر إطار طُلب أثناء انشغال الخيط
        self._render = None
        self._folder = os.path.join(tempfile.gettempdir(), "wun_cut_stage")

        self.stack = QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.setStackingMode(QStackedLayout.StackOne)

        self.still = QLabel(t("حرّك رأس التشغيل لتظهر المعاينة"))
        self.still.setObjectName("Hint")
        self.still.setAlignment(Qt.AlignCenter)
        self.still.setMinimumHeight(220)
        self.stack.addWidget(self.still)

        self.video = QVideoWidget()
        self.video.setMinimumHeight(220)
        self.stack.addWidget(self.video)

        # لوحة الانتظار: ترميز المعاينة يأخذ ثوانيَ، وسطرٌ صغير تحت النافذة
        # لا يُرى. من يضغط تشغيل ولا يرى شيئًا يظنّ البرنامج معطّلًا.
        self.busy = QWidget()
        busy = QVBoxLayout(self.busy)
        busy.setContentsMargins(60, 40, 60, 40)
        busy.setSpacing(12)
        busy.addStretch(1)
        self.busy_text = QLabel(t("جاري تجهيز المعاينة…"))
        self.busy_text.setObjectName("ClipName")
        self.busy_text.setAlignment(Qt.AlignCenter)
        busy.addWidget(self.busy_text)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        busy.addWidget(self.bar)
        self.busy_hint = QLabel(t("يُرمَّز مرّة واحدة، ثم يشتغل فورًا "
                                  "ما لم تعدّل شيئًا."))
        self.busy_hint.setObjectName("Hint")
        self.busy_hint.setAlignment(Qt.AlignCenter)
        busy.addWidget(self.busy_hint)
        self.btn_cancel = QPushButton(t("إلغاء"))
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.cancel_proxy)
        row = QVBoxLayout()
        row.addWidget(self.btn_cancel, 0, Qt.AlignCenter)
        busy.addLayout(row)
        busy.addStretch(1)
        self.stack.addWidget(self.busy)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(DELAY)
        self.timer.timeout.connect(self._start)
        self._pixmap = None

        self._proxy = None          # الخيط الجاري
        self._proxy_path = None     # آخر معاينة جاهزة
        self._proxy_key = None      # بصمة المشروع وقت ترميزها
        self._sweep()

    def _sweep(self):
        """
        يمسح ما خلّفته جلسةٌ سابقة.

        الصور تُحذف بعد قراءتها، لكن جلسةً انتهت بقوّة تترك آخر واحدة. بلا
        مسحٍ عند البدء يتراكم المجلّد بلا سقف.
        """
        if not os.path.isdir(self._folder):
            return
        for name in os.listdir(self._folder):
            try:
                os.remove(os.path.join(self._folder, name))
            except OSError:
                pass

    # --------------------------------------------------------------- التبديل

    def show_video(self):
        self.timer.stop()
        self.stack.setCurrentWidget(self.video)

    def show_still(self):
        self.stack.setCurrentWidget(self.still)

    def show_busy(self, done=0, total=1):
        self.bar.setMaximum(max(1, total))
        self.bar.setValue(max(0, done))
        self.stack.setCurrentWidget(self.busy)

    @property
    def live(self):
        return self.stack.currentWidget() is self.still

    # ---------------------------------------------------------------- الطلب

    def refresh(self, project, frame):
        """يطلب رسم الإطار. النداءات المتلاحقة تُدمج في واحدة."""
        self.project = project
        self._pending = int(frame)
        if not self.live:
            return
        self.timer.start()

    def _start(self):
        if self._render is not None or self.project is None:
            return                          # ينتظر انتهاء الجارية
        frame, self._pending = self._pending, None
        if frame is None:
            return
        os.makedirs(self._folder, exist_ok=True)
        target = os.path.join(self._folder, "%s.jpg" % uuid.uuid4().hex[:10])
        self._render = _Render(self.project, frame, target, self)
        self._render.done.connect(self._arrived)
        self._render.finished.connect(self._free)
        # بلا حذف: يبقى جسم QThread حيًّا تحت الأب بعد انتهائه، فتتراكم
        # مئاتُ الخيوط في الجلسة الواحدة حتى تنفد مقابض النظام ويتجمّد كلّ شيء
        self._render.finished.connect(self._render.deleteLater)
        self._render.start()

    def _arrived(self, path, _frame):
        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._pixmap = pixmap
                self._paint()
            try:
                os.remove(path)
            except OSError:
                pass
        elif self._pixmap is None:
            self.still.setText(t("لا يوجد مقطع عند رأس التشغيل"))

    def _free(self):
        self._render = None
        if self._pending is not None:
            self.timer.start()      # وصل طلب أحدث أثناء الرسم

    # ------------------------------------------------ معاينة التشغيل الكاملة

    @staticmethod
    def signature(project):
        """
        بصمة حالة المشروع.

        كل ما يدخل التصدير يدخلها: المقاطع والتأثيرات والحركات وحالة المسارات.
        فإن لم يتغيّر شيء أُعيد تشغيل المعاينة الجاهزة بلا ترميز.
        """
        raw = json.dumps(project.to_dict(), sort_keys=True,
                         ensure_ascii=False)
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()

    def proxy_ready(self, project):
        """مسار معاينة صالحة لهذا المشروع، أو None إن لزم ترميزها."""
        if (self._proxy_path and self._proxy_key == self.signature(project)
                and os.path.exists(self._proxy_path)):
            return self._proxy_path
        return None

    def build_proxy(self, project, on_progress, on_ready):
        """يرمّز معاينة التشغيل في الخلفية. يرجع False إن كانت جاهزة."""
        if self.proxy_ready(project):
            on_ready(self._proxy_path)
            return False
        if self._proxy is not None:
            return True                 # ترميزٌ جارٍ

        os.makedirs(self._folder, exist_ok=True)
        key = self.signature(project)
        target = os.path.join(self._folder, "proxy_%s.mp4" % key[:12])

        def arrived(path):
            self._proxy = None
            if path:
                self._drop_old(path)
                self._proxy_path, self._proxy_key = path, key
                on_ready(path)
            else:
                on_ready("")

        self._proxy = _Proxy(project, target, self)
        self._proxy.progress.connect(on_progress)
        self._proxy.done.connect(arrived)
        self._proxy.finished.connect(self._proxy.deleteLater)
        self._proxy.start()
        return True

    def cancel_proxy(self):
        if self._proxy is not None:
            self._proxy.cancel()

    def _drop_old(self, keep):
        """معاينةٌ لكل تعديل تملأ القرص: نبقي الأخيرة وحدها."""
        for name in os.listdir(self._folder):
            path = os.path.join(self._folder, name)
            if name.startswith("proxy_") and path != keep:
                try:
                    os.remove(path)
                except OSError:
                    pass

    def shutdown(self):
        """إغلاق النافذة: ننتظر الخيوط الجارية حتى لا يُهدم خيطٌ يعمل."""
        self.timer.stop()
        self._pending = None
        self.cancel_proxy()
        for thread in (self._render, self._proxy):
            if thread is not None:
                thread.wait(8000)

    def _paint(self):
        if self._pixmap is None:
            return
        self.still.setPixmap(self._pixmap.scaled(
            self.still.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def clear(self):
        self._pixmap = None
        self.still.setText(t("حرّك رأس التشغيل لتظهر المعاينة"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint()


def demo():
    """فحص ذاتي: الطلبات المتلاحقة تُدمج، والصورة تصل."""
    import sys

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from PySide6.QtCore import QEventLoop
    from PySide6.QtWidgets import QApplication

    from wun_cut.core import media
    from wun_cut.core.project import Clip, Editor, Project

    app = QApplication.instance() or QApplication([])
    stage = Stage()
    stage.resize(720, 405)
    stage.show()

    assert stage.live, "لا تبدأ على الصورة"
    stage.show_video()
    assert not stage.live
    stage.show_still()

    if len(sys.argv) > 1:
        info = media.probe(sys.argv[1])
        project = Project(info.fps, 1280, 720)
        editor = Editor(project)
        editor.append("video", Clip(info.path, 0, project.frames(5)))

        # عشر طلبات متلاحقة يجب ألا تولّد عشر رسمات
        started = []
        original = stage._start

        def counted():
            started.append(1)
            original()

        stage._start = counted
        for frame in range(10):
            stage.refresh(project, project.frames(1) + frame)
        assert not started, "رسم قبل انتهاء التأجيل"

        loop = QEventLoop()
        stage.timer.timeout.connect(loop.quit)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        assert len(started) == 1, "عشر طلبات ولّدت %d رسمة" % len(started)
        print("عشر طلبات متلاحقة -> رسمة واحدة ✓")

        loop = QEventLoop()
        stage._render.finished.connect(loop.quit)
        QTimer.singleShot(30000, loop.quit)
        loop.exec()
        app.processEvents()
        assert stage._pixmap is not None and not stage._pixmap.isNull(), \
            "لم تصل الصورة"
        print("الصورة وصلت: %dx%d" % (stage._pixmap.width(),
                                      stage._pixmap.height()))
        # الصور المؤقّتة تُحذف بعد قراءتها. نفحص الصور وحدها: معاينات التشغيل
        # تبقى عمدًا حتى يتغيّر المشروع.
        stills = [n for n in os.listdir(stage._folder) if n.endswith(".jpg")]
        assert not stills, "صور مؤقّتة لم تُحذف: %s" % stills[:3]
        print("الصور المؤقّتة تُنظَّف بعد قراءتها ✓")

        # --- بصمة المشروع: تتغيّر مع التعديل وحده ---
        first = stage.signature(project)
        assert stage.signature(project) == first, "البصمة غير ثابتة"
        clip = project.track("video").clips[0]
        editor.set_effect(clip, "brightness", 30)
        assert stage.signature(project) != first, "البصمة لم تتبع التأثير"
        editor.set_effect(clip, "brightness", 0)
        assert stage.signature(project) == first, "البصمة لم ترجع بالتراجع"
        assert stage.proxy_ready(project) is None, "معاينة جاهزة بلا ترميز"
        print("بصمة المشروع تتبع التعديل وحده ✓")

    print("gui/stage: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
