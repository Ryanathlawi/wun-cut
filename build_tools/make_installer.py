"""
بناء مثبّت وِن كَت كاملًا في خطوة واحدة.

    .venv\\Scripts\\python.exe build_tools/make_installer.py

يبني نسخة المجلد، يحزمها في payload.zip، ثم يبني ملف المثبّت الواحد.
النتيجة في dist_setup/Wun Cut Setup.exe
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "dist_dir", "Wun Cut")
PAYLOAD = os.path.join(ROOT, "build", "payload.zip")
PYTHON = sys.executable


def run(args, env=None):
    merged = dict(os.environ)
    if env:
        merged.update(env)
    result = subprocess.run(args, cwd=ROOT, env=merged)
    if result.returncode != 0:
        raise SystemExit("فشل: %s" % " ".join(args))


def build_app():
    print("[١/٤] بناء نسخة المجلد…")
    run([PYTHON, "-m", "PyInstaller", "build_tools/app.spec", "--noconfirm",
         "--distpath", "dist_dir", "--workpath", "build_dir"],
        {"WUN_ONEDIR": "1"})


def bundle_tools():
    """
    ينسخ ffmpeg و ffprobe إلى bin بجوار البرنامج.

    البرنامج كلّه قائمٌ عليهما: بلا إرفاقهما يعمل على جهاز المطوّر وحده،
    ويسقط على جهاز المستخدم عند أوّل استيراد. وهما يرفعان الحجم كثيرًا،
    لكن هذا ثمنُ «يعمل بلا إنترنت وبلا تثبيتِ شيءٍ آخر».
    """
    print("[٢/٤] إرفاق ffmpeg و ffprobe…")
    nest = os.path.join(APP_DIR, "bin")
    os.makedirs(nest, exist_ok=True)
    for name in ("ffmpeg", "ffprobe"):
        found = shutil.which(name)
        if not found:
            raise SystemExit("لم يُعثر على %s في PATH" % name)
        target = os.path.join(nest, os.path.basename(found))
        if not os.path.exists(target) or                 os.path.getsize(target) != os.path.getsize(found):
            shutil.copy2(found, target)
        print("      %s · %.0f م.ب" % (os.path.basename(target),
                                       os.path.getsize(target) / 1e6))


def pack_payload():
    print("[٣/٤] حزم البرنامج في payload.zip…")
    if not os.path.isdir(APP_DIR):
        raise SystemExit("لم يُعثر على %s" % APP_DIR)
    os.makedirs(os.path.dirname(PAYLOAD), exist_ok=True)
    if os.path.exists(PAYLOAD):
        os.remove(PAYLOAD)

    started = time.time()
    count = 0
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for folder, _dirs, files in os.walk(APP_DIR):
            for name in files:
                full = os.path.join(folder, name)
                archive.write(full, os.path.relpath(full, APP_DIR))
                count += 1
    size = os.path.getsize(PAYLOAD)
    raw = sum(os.path.getsize(os.path.join(f, n))
              for f, _d, files in os.walk(APP_DIR) for n in files)
    print("      %d ملف · %.0f م.ب -> %.0f م.ب · %.0f ثانية"
          % (count, raw / 1e6, size / 1e6, time.time() - started))


def build_installer():
    print("[٤/٤] بناء ملف المثبّت…")
    run([PYTHON, "-m", "PyInstaller", "build_tools/installer.spec",
         "--noconfirm", "--distpath", "dist_setup",
         "--workpath", "build_setup"])
    out = os.path.join(ROOT, "dist_setup", "Wun Cut Setup.exe")
    if os.path.exists(out):
        print("\nجاهز: %s  (%.0f م.ب)" % (out, os.path.getsize(out) / 1e6))


def main():
    steps = sys.argv[1:] or ["app", "tools", "payload", "installer"]
    if "app" in steps:
        build_app()
    if "tools" in steps:
        bundle_tools()
    if "payload" in steps:
        pack_payload()
    if "installer" in steps:
        build_installer()


if __name__ == "__main__":
    main()
