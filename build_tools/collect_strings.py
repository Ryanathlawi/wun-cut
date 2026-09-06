"""
جمع كل النصوص المارّة بدالة الترجمة t() في ملف واحد.

    python build_tools/collect_strings.py

يقرأ شجرة الكود لا الرموز، فيلتقط النصوص المتلاصقة مجموعةً واحدة كما تصل
إلى t() تمامًا. المخرجات هي مفاتيح EN_MAP الفعلية.
"""

from __future__ import annotations

import ast
import glob
import io
import os
import re
import sys

ARABIC = re.compile(r"[؀-ۿ]")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# مفاتيح تصل t() عبر متغيّر - جداول الثوابت ورسائل core - فلا تلتقطها شجرة
# الكود. تُذكر هنا حتى لا يبلّغ التقرير عنها كترجمات ميّتة كل مرّة.
DYNAMIC = {
    "السطوع", "التباين", "التشبّع", "السرعة", "الصوت", "تلاشي الدخول",
    "تلاشي الخروج", "طبيعي", "ساطع", "سينمائي", "أبيض وأسود",
    "مقاس المشروع", "معدّل المشروع", "مدّة الحركة",
    "حركة الدخول", "حركة الخروج", "حجم الطبقة",
    "الموضع الأفقي", "الموضع الرأسي", "الفلتر", "شدّة الفلتر",
    "الانتقال", "مدّة الانتقال", "التحريك", "شدّة التحريك",
    "الميلان", "شدّة الميلان", "الانقلاب", "شدّة الانقلاب",
    "بلا انقلاب", "انقلاب من اليمين", "انقلاب من اليسار",
    "انقلاب من الأعلى", "انقلاب من الأسفل",
    "بابٌ يُفتح يسارًا", "بابٌ يُفتح يمينًا", "بلا ميلان", "ميلان يستقيم", "ميلان يزداد",
    "ميلان ثابت لليسار", "ميلان ثابت لليمين", "تمايل", "انقلاب بطاقة",
    "بلا تحريك", "تقريب بطيء", "إبعاد بطيء", "تحريك لليمين",
    "تحريك لليسار", "تحريك للأعلى", "تحريك للأسفل",
    "تقريب مع انزلاق", "اهتزاز الكاميرا", "مقاس النصّ", "حدّ النصّ",
    "بلا أنيميشن", "حرفًا حرفًا من اليمين", "حرفًا حرفًا من اليسار",
    "حرفًا حرفًا من الأسفل", "سقوط الحروف", "تكبير حرفًا حرفًا",
    "دوران الحروف", "ظهورٌ متتابع",
    "لليمين", "في الوسط", "لليسار", "يتبع المقطع",
    "16:9  عريض", "9:16  عمودي", "1:1  مربّع", "4:5  إنستقرام",
    "أشرطة سوداء", "خلفية ضبابية",
    "تفاعلات", "إشارات", "أيادٍ", "ألعاب", "قلوب",
    "سهم لليمين", "سهم لليسار", "سهم للأعلى", "سهم للأسفل",
    "دائرة تمييز", "مربّع تمييز", "فقاعة كلام", "نجمة",
    "علامة صحّ", "علامة خطأ", "انفجار", "خطّ تحته",
    "بلا فلتر", "ضبابية", "حِدّة", "تعتيم الأطراف", "حبيبات فيلم",
    "دافئ", "بارد", "بنّي قديم", "باهت", "ألوان صارخة", "انعكاس أفقي",
    "بلا انتقال", "تلاشٍ", "تلاشٍ عبر الأسود", "تلاشٍ عبر الأبيض",
    "ذوبان", "انزلاق لليسار", "انزلاق لليمين", "انزلاق للأعلى",
    "انزلاق للأسفل", "مسح لليسار", "مسح لليمين", "دائرة تتّسع",
    "دائرة تنغلق", "دوران", "تبقّع", "انسياب لليسار",
    "مسح للأعلى", "مسح للأسفل", "قصٌّ دائري", "قصٌّ مستطيل", "تباعد", "انسياب لليمين", "انسياب للأعلى", "انسياب للأسفل", "فتحٌ رأسي", "إغلاقٌ رأسي", "فتحٌ أفقي", "إغلاقٌ أفقي", "قطريّ من أعلى اليسار", "قطريّ من أعلى اليمين", "قطريّ من أسفل اليسار", "قطريّ من أسفل اليمين", "شرائح لليسار", "شرائح لليمين", "شرائح للأعلى", "شرائح للأسفل", "ضبابٌ أفقي", "تلاشٍ عبر الرمادي", "مسح من أعلى اليسار", "مسح من أعلى اليمين", "مسح من أسفل اليسار", "مسح من أسفل اليمين", "عصرٌ أفقي", "عصرٌ رأسي", "اندفاعٌ للداخل", "تلاشٍ سريع", "تلاشٍ بطيء", "ريحٌ لليسار", "ريحٌ لليمين", "ريحٌ للأعلى", "ريحٌ للأسفل", "تغطيةٌ لليسار", "تغطيةٌ لليمين", "تغطيةٌ للأعلى", "تغطيةٌ للأسفل", "كشفٌ لليسار", "كشفٌ لليمين", "كشفٌ للأعلى", "كشفٌ للأسفل",
    "بلا حركة", "تكبير", "تصغير", "انزلاق من اليمين",
    "انزلاق من اليسار", "انزلاق من أعلى", "انزلاق من أسفل",
    "الخط الزمني فارغ", "لا يوجد مسار فيديو لتصديره",
}


def calls(path):
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "t"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.append(arg.value)
    return found


def loose(path):
    """نصوص عربية لم تُلفّ بعد."""
    source = io.open(path, encoding="utf-8").read()
    tree = ast.parse(source)
    wrapped = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "t" and node.args):
            arg = node.args[0]
            if isinstance(arg, ast.Constant):
                wrapped.add((arg.lineno, arg.col_offset))

    docs = set()
    targets = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, targets) and body:
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docs.add((first.value.lineno, first.value.col_offset))

    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        where = (node.lineno, node.col_offset)
        if where in wrapped or where in docs:
            continue
        if ARABIC.search(node.value) and len(node.value) < 400:
            out.append((node.lineno, node.value))
    return out


def main():
    paths = sorted(glob.glob(os.path.join(ROOT, "gui", "*.py"))) + \
            sorted(glob.glob(os.path.join(ROOT, "core", "*.py")))

    everything = []
    stragglers = []
    for path in paths:
        if os.path.basename(path) == "i18n.py":
            continue
        everything.extend(calls(path))
        for line, value in loose(path):
            stragglers.append((os.path.relpath(path, ROOT), line, value))

    unique = sorted(set(everything))
    out = os.path.join(ROOT, "build", "strings.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as handle:
        for value in unique:
            handle.write(repr(value) + "\n")

    print("استدعاءات t(): %d | نصوص فريدة: %d" % (len(everything), len(unique)))
    print("لم تُلفّ بعد: %d" % len(stragglers))
    for rel, line, value in stragglers[:40]:
        print("   %s:%d  %s" % (rel, line, value[:70]))

    sys.path.insert(0, ROOT)
    en = __import__("i18n").EN_MAP
    missing = [value for value in unique if value not in en]
    stale = [key for key in en
             if key not in set(unique) and key not in DYNAMIC]
    print("\nبلا ترجمة إنجليزية: %d" % len(missing))
    for value in missing:
        print("   %r" % value)
    print("ترجمات لم تعد مستعملة: %d" % len(stale))
    for key in stale:
        print("   %r" % key)


if __name__ == "__main__":
    main()
