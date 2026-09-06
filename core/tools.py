"""
مواضع ffmpeg و ffprobe.

البرنامج يستدعيهما بالاسم المجرّد، وهذا يصحّ على جهاز المطوّر حيث هما في
PATH، ولا يصحّ على جهاز المستخدم. فتُطلبان أوّلًا من جوار البرنامج نفسه -
حيث يضعهما المثبّت - ثم من PATH، ثم يُترك الاسمُ مجرّدًا ليخرج خطأٌ مفهوم.

والبحث يُخزَّن: كل قصاصةٍ في التصدير تستدعي أحدهما، وسؤالُ نظام الملفات في
كل مرّة إبطاءٌ بلا سبب.
"""

from __future__ import annotations

import functools
import os
import shutil
import sys

FOLDER = "bin"                  # حيث يضع المثبّت الأداتين


def home():
    """
    المجلد الذي يُبحث فيه: بجوار الـ exe عند التغليف، وجذرُ المشروع عند
    التشغيل من المصدر. sys.executable داخل الحزمة هو البرنامج نفسه لا بايثون.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@functools.lru_cache(maxsize=8)
def find(name):
    """مسار الأداة: المرفقة أوّلًا، ثم ما في PATH، ثم الاسم مجرّدًا."""
    tail = ".exe" if os.name == "nt" else ""
    root = home()
    for folder in (os.path.join(root, FOLDER), root):
        candidate = os.path.join(folder, name + tail)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name) or name


def ffmpeg():
    return find("ffmpeg")


def ffprobe():
    return find("ffprobe")


def ready():
    """هل الأداتان موجودتان فعلًا؟"""
    return all(os.path.isfile(p) or shutil.which(p)
               for p in (ffmpeg(), ffprobe()))


def demo():
    """فحص ذاتي: المرفقة تسبق ما في PATH، والغائبة ترجع اسمها."""
    import io
    import tempfile

    assert ffmpeg().lower().endswith(("ffmpeg", "ffmpeg.exe")), ffmpeg()
    assert ffprobe().lower().endswith(("ffprobe", "ffprobe.exe")), ffprobe()
    print("من PATH: %s" % os.path.basename(ffmpeg()))

    # نسخةٌ مرفقة تسبق: نصنع مجلّدًا فيه أداةٌ باسمها ونوجّه البحث إليه
    shed = tempfile.mkdtemp(prefix="wun_cut_tools_")
    try:
        nest = os.path.join(shed, FOLDER)
        os.makedirs(nest)
        tail = ".exe" if os.name == "nt" else ""
        planted = os.path.join(nest, "ffmpeg" + tail)
        with open(planted, "wb") as fh:
            fh.write(b"\0")
        global home
        real_home = home
        home = lambda: shed                                  # noqa: E731
        find.cache_clear()
        assert ffmpeg() == planted, \
            "المرفقة لم تسبق ما في PATH: %s" % ffmpeg()
        # وأداةٌ غير موجودةٍ لا في المجلّد ولا في PATH ترجع اسمها المجرّد
        assert find("لا-توجد-أداة") == "لا-توجد-أداة"
        print("المرفقة تسبق: %s ✓" % os.path.basename(planted))
    finally:
        home = real_home
        find.cache_clear()
        shutil.rmtree(shed, ignore_errors=True)

    # --- لا استدعاءَ بالاسم المجرّد في الشفرة ---
    #
    # سطرٌ واحد يقول ["ffmpeg", ...] يكفي ليعمل على جهاز المطوّر ويفشل على
    # جهاز المستخدم، ولن يظهر في أي فحصٍ آخر لأن ffmpeg موجودٌ هنا في PATH.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    guilty = []
    for folder in ("core", "gui"):
        here = os.path.join(root, folder)
        for name in sorted(os.listdir(here)):
            if not name.endswith(".py") or name == "tools.py":
                continue
            body = io.open(os.path.join(here, name), encoding="utf-8").read()
            for bad in ('["ffmpeg"', '["ffprobe"', "'ffmpeg'", "'ffprobe'"):
                if bad in body:
                    guilty.append("%s/%s: %s" % (folder, name, bad))
    assert not guilty, "استدعاءٌ بالاسم المجرّد: %s" % guilty
    print("لا استدعاءَ مجرّدًا في الشفرة ✓")

    assert ready(), "ffmpeg أو ffprobe غير موجودتين على هذا الجهاز"
    print("core/tools: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
