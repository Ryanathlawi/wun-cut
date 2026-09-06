# -*- coding: utf-8 -*-
"""فحص المرحلة ٣: حوار التصدير وخيطه، لا النواة وحدها."""
import json
import os
import subprocess
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtCore import QEventLoop, QTimer                 # noqa: E402
from PySide6.QtWidgets import QApplication                    # noqa: E402

from wun_cut.core import export, media                        # noqa: E402
from wun_cut.gui import theme                                 # noqa: E402
from wun_cut.gui.export_dialog import ExportDialog, ExportThread  # noqa: E402
from wun_cut.gui.main_window import MainWindow                # noqa: E402

SAMPLE = sys.argv[1]

app = QApplication([])
theme.load_fonts()
app.setStyleSheet(theme.qss())

window = MainWindow()
info = media.probe(SAMPLE)
window.add_to_timeline(info)
project = window.editor.project

# نقصّه إلى ثانيتين حتى يبقى الفحص سريعًا
clip = project.track("video").clips[0]
window.editor.trim(clip, project.frames(2))
print("المشروع: %s · %dx%d · %.4g fps"
      % (project.timecode(project.duration), project.width, project.height,
         float(project.fps)))
assert window.btn_export.isEnabled(), "زر التصدير معطّل رغم وجود محتوى"

dialog = ExportDialog(project, window)
out = os.path.join(tempfile.gettempdir(), "wuncut_gui_export.mp4")
dialog.path.setText(out)
dialog.resolution.setCurrentIndex(1)          # 720p
dialog.quality.setValue(55)
settings = dialog.settings()
print("الإعدادات:", {k: v for k, v in settings.items() if k != "output"})
assert settings["scale"] == (1280, 720)
assert settings["encoder"], "لم يُختر مرمّز"

# التحذير يتغيّر عند تفعيل توليد الإطارات
plain = dialog.hint.text()
dialog.interpolate.setChecked(True)
assert dialog.hint.text() != plain and "بطيء" in dialog.hint.text()
dialog.interpolate.setChecked(False)
print("تحذير توليد الإطارات يظهر ويختفي ✓")

settings.pop("output")
job = export.ExportJob(project, out, **settings)
thread = ExportThread(job)
seen, result = [], {}
thread.progress.connect(lambda d, t: seen.append(d))
thread.done.connect(lambda p: result.update(path=p))
thread.failed.connect(lambda m: result.update(error=m))

loop = QEventLoop()
thread.finished.connect(loop.quit)
QTimer.singleShot(180000, loop.quit)
thread.start()
loop.exec()

assert "error" not in result, result["error"]
assert result.get("path") == out, result
data = json.loads(subprocess.run(
    ["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
     "-show_streams", out], capture_output=True,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
).stdout.decode("utf-8", "replace"))

duration = float(data["format"]["duration"])
video = next(s for s in data["streams"] if s["codec_type"] == "video")
expected = project.seconds(project.duration)
print("الناتج: %.2f ث (المتوقّع %.2f) · %sx%s · %.1f م.ب · تقدّم %d مرة"
      % (duration, expected, video["width"], video["height"],
         os.path.getsize(out) / 1e6, len(seen)))
assert abs(duration - expected) < 0.35, (duration, expected)
assert (video["width"], video["height"]) == (1280, 720)
assert seen, "لم يصل أي تقدّم"
os.remove(out)

# --- الإلغاء ينظّف الملف الناقص ---
job2 = export.ExportJob(project, out, **settings)
thread2 = ExportThread(job2)
thread2.progress.connect(lambda d, t: thread2.cancel())
loop2 = QEventLoop()
thread2.finished.connect(loop2.quit)
QTimer.singleShot(60000, loop2.quit)
thread2.start()
loop2.exec()
print("بعد الإلغاء: الملف موجود؟", os.path.exists(out))
assert not os.path.exists(out), "الإلغاء ترك ملفًا ناقصًا"

print("\nفحص المرحلة ٣: كل الفحوص سليمة")
