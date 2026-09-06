"""
قراءة الوسائط: الوحدة الوحيدة التي تعرف أن FFmpeg موجود.

نستدعي `ffmpeg` و`ffprobe` كأمرين خارجيين لا كمكتبات مربوطة. الربط بـ
libavcodec أسرع نظريًا، لكنه يجرّ بناءً أصليًا وتوافق إصدارات، والفرق لا
يظهر في أداة تحرير: الوقت كله في الترميز لا في نداء الدالة.

كل دالة هنا تُرجع قيمة أو ترفع MediaError. لا صناديق حوار ولا Qt.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from fractions import Fraction
from . import tools

# على ويندوز يفتح subprocess نافذة سوداء لكل استدعاء ما لم يُمنع صراحةً
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".flv")
AUDIO_EXT = (".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac", ".opus")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif")


class MediaError(Exception):
    pass


def _run(args, timeout=120):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout,
                                creationflags=NO_WINDOW)
    except FileNotFoundError:
        raise MediaError("FFmpeg غير مثبّت أو غير موجود في PATH")
    except subprocess.TimeoutExpired:
        raise MediaError("انتهت مهلة FFmpeg")
    return result


def available():
    """هل FFmpeg و ffprobe موجودان؟"""
    return tools.ready()


def kind(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    return ""


class MediaInfo:

    def __init__(self, path, duration=0.0, fps=Fraction(0), width=0, height=0,
                 has_video=False, has_audio=False, vcodec="", acodec="",
                 size=0):
        self.path = path
        self.name = os.path.basename(path)
        self.duration = duration
        self.fps = fps
        self.width = width
        self.height = height
        self.has_video = has_video
        self.has_audio = has_audio
        self.vcodec = vcodec
        self.acodec = acodec
        self.size = size

    @property
    def resolution(self):
        return "%d×%d" % (self.width, self.height) if self.width else ""

    def describe(self):
        bits = []
        if self.has_video:
            bits.append(self.resolution)
            if self.fps:
                bits.append("%.4g fps" % float(self.fps))
        if self.has_audio:
            bits.append(self.acodec.upper() if self.acodec else "صوت")
        return " · ".join(b for b in bits if b)

    def __repr__(self):
        return "<MediaInfo %s %.2fs>" % (self.name, self.duration)


def probe(path):
    """بيانات ملف وسائط. يرفع MediaError إن تعذّرت القراءة."""
    if not os.path.isfile(path):
        raise MediaError("الملف غير موجود: %s" % path)

    result = _run([tools.ffprobe(), "-v", "error", "-print_format", "json",
                   "-show_format", "-show_streams", path])
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise MediaError(detail.splitlines()[-1] if detail else "ملف غير مقروء")

    try:
        data = json.loads(result.stdout.decode("utf-8", "replace"))
    except ValueError:
        raise MediaError("مخرجات ffprobe غير مفهومة")

    fmt = data.get("format", {})
    info = MediaInfo(path)
    info.size = int(fmt.get("size") or 0)
    try:
        info.duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        info.duration = 0.0

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and not info.has_video:
            # الصور الثابتة تظهر كتيّار فيديو، ونميّزها بالامتداد لا بالتيّار
            info.has_video = True
            info.width = int(stream.get("width") or 0)
            info.height = int(stream.get("height") or 0)
            info.vcodec = stream.get("codec_name") or ""
            info.fps = _rate(stream.get("avg_frame_rate")
                             or stream.get("r_frame_rate"))
        elif codec_type == "audio" and not info.has_audio:
            info.has_audio = True
            info.acodec = stream.get("codec_name") or ""

    if not info.has_video and not info.has_audio:
        raise MediaError("لا يحتوي الملف على صوت ولا صورة")
    return info


def _rate(text):
    """يحوّل «30000/1001» إلى كسر. القسمة على صفر تعني معدّلًا غير معلوم."""
    if not text:
        return Fraction(0)
    try:
        num, _, den = str(text).partition("/")
        den = den or "1"
        if int(den) == 0:
            return Fraction(0)
        return Fraction(int(num), int(den))
    except (TypeError, ValueError):
        return Fraction(0)


def thumbnail(path, target, at=0.0, width=320):
    """يستخرج إطارًا واحدًا إلى ملف. الوضع قبل -i يجعل القفز سريعًا."""
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    result = _run([tools.ffmpeg(), "-y", "-v", "error",
                   "-ss", "%.3f" % max(0.0, at), "-i", path,
                   "-frames:v", "1", "-vf", "scale=%d:-2" % width,
                   target], timeout=60)
    if result.returncode != 0 or not os.path.exists(target):
        raise MediaError("تعذّر استخراج إطار من %s" % os.path.basename(path))
    return target


def demo():
    """فحص ذاتي على ملف حقيقي يُمرَّر في سطر الأوامر."""
    import sys
    import tempfile

    assert available(), "FFmpeg غير موجود"
    assert kind("a.MP4") == "video" and kind("a.wav") == "audio"
    assert kind("a.png") == "image" and kind("a.txt") == ""
    assert _rate("30000/1001") == Fraction(30000, 1001)
    assert _rate("0/0") == 0 and _rate(None) == 0 and _rate("bad") == 0

    try:
        probe(os.path.join(tempfile.gettempdir(), "لا-يوجد-أبدًا.mp4"))
    except MediaError:
        pass
    else:
        raise AssertionError("ملف مفقود لم يرفع خطأ")

    if len(sys.argv) > 1:
        info = probe(sys.argv[1])
        print("  %s | %.2f ث | %s" % (info.name, info.duration,
                                      info.describe()))
        assert info.duration > 0 and info.has_video
        out = os.path.join(tempfile.gettempdir(), "wuncut_thumb.jpg")
        thumbnail(info.path, out, at=min(1.0, info.duration / 2))
        assert os.path.getsize(out) > 500
        print("  مصغّرة: %d بايت" % os.path.getsize(out))
        os.remove(out)

    print("core/media: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
