"""
الترجمة: عربي وإنجليزي.

النص العربي نفسه هو المفتاح، فلا حاجة لاختراع مفاتيح ولا لأدوات بناء
إضافية. أي نص بلا ترجمة يظهر بالعربية كما هو بدل أن يختفي.

الوحدة لا تستورد Qt إطلاقًا حتى تبقى core صالحة كمكتبة مستقلة، والاختيار
يُحفظ في ملف JSON بجانب إعدادات المستخدم.
"""

from __future__ import annotations

import json
import os

APP_FOLDER = "Wun Cut"

AR = "ar"
EN = "en"
LANGUAGES = {AR: "العربية", EN: "English"}

_current = AR
_settings_path = None


def settings_file():
    global _settings_path
    if _settings_path is None:
        root = (os.environ.get("APPDATA")
                or os.path.join(os.path.expanduser("~"), ".config"))
        folder = os.path.join(root, APP_FOLDER)
        _settings_path = os.path.join(folder, "settings.json")
    return _settings_path


def _read_settings():
    try:
        with open(settings_file(), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def _write_settings(data):
    path = settings_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def load():
    global _current
    stored = _read_settings().get("language")
    if stored in LANGUAGES:
        _current = stored
    return _current


def language():
    return _current


def set_language(code):
    global _current
    if code not in LANGUAGES:
        return False
    _current = code
    data = _read_settings()
    data["language"] = code
    return _write_settings(data)


def get(key, default=None):
    """
    إعداد عام من ملف الإعدادات نفسه.

    الوحدة تملك الملف أصلًا، فإضافة وحدة إعدادات ثانية بجانبها تعني مسارين
    ومِلفّين لشيء واحد.
    """
    return _read_settings().get(key, default)


def put(key, value):
    data = _read_settings()
    data[key] = value
    return _write_settings(data)


def other_language():
    return EN if _current == AR else AR


def is_rtl():
    return _current == AR


def t(text):
    if _current == AR:
        return text
    return EN_MAP.get(text, text)


EN_MAP: dict[str, str] = {
    # ---------------------------------------------------------- شريط الأدوات
    "استورد وسائط": "Import Media",
    "أضف ملفات إلى المكتبة  (Ctrl+I)": "Add files to the library  (Ctrl+I)",
    "أضف للخط الزمني": "Add to Timeline",
    "يضع الملف المحدَّد في نهاية الخط": "Appends the selected file to the timeline",
    "قسّم": "Split",
    "يقسم المقطع عند رأس التشغيل  (S)": "Splits the clip at the playhead  (S)",
    "احذف": "Delete",
    "يحذف المقطع المحدَّد  (Delete)": "Deletes the selected clip  (Delete)",
    "تراجع  (Ctrl+Z)": "Undo  (Ctrl+Z)",
    "إعادة  (Ctrl+Y)": "Redo  (Ctrl+Y)",
    "صدّر الفيديو": "Export Video",
    "يرسم الخط الزمني إلى ملف  (Ctrl+E)":
        "Renders the timeline to a file  (Ctrl+E)",

    # ------------------------------------------------------- المشروع
    "احفظ المشروع": "Save Project",
    "احفظ المشروع  (Ctrl+S)": "Save project  (Ctrl+S)",
    "افتح مشروعًا": "Open Project",
    "افتح مشروعًا  (Ctrl+O)": "Open project  (Ctrl+O)",
    "مشروع Wun Cut (*.wcut);;كل الملفات (*)":
        "Wun Cut project (*.wcut);;All files (*)",
    "تعذّر الحفظ": "Could not save",
    "تعذّر فتح المشروع": "Could not open the project",
    "حُفظ إلى %s": "Saved to %s",
    "فُتح %s": "Opened %s",
    "هل تحفظ التعديلات قبل المتابعة؟": "Save your changes before continuing?",

    # --------------------------------------------------------- اللوحة
    "نسبة اللوحة": "Canvas ratio",
    "ما يملأ الفراغ حول المقطع": "What fills the space around the clip",
    "اللوحة %d×%d": "Canvas %d×%d",
    "يتبع المقطع": "Match clip",
    "16:9  عريض": "16:9  Wide",
    "9:16  عمودي": "9:16  Vertical",
    "1:1  مربّع": "1:1  Square",
    "4:5  إنستقرام": "4:5  Instagram",
    "أشرطة سوداء": "Black bars",
    "خلفية ضبابية": "Blurred background",

    # -------------------------------------------------------- الملصقات
    "ملصق": "Sticker",
    "الملصقات": "Stickers",
    "إيموجي وأشكال على طبقة فوق الفيديو  (Ctrl+K)":
        "Emoji and shapes on a layer above the video  (Ctrl+K)",
    "أُضيف ملصق %s": "Added sticker %s",
    "تعذّر رسم الملصق": "Could not render the sticker",
    "لون الأشكال": "Shape colour",
    "أشكال": "Shapes",
    "لملصق خاصّ بك، استورد صورتك واضغط «أضف كطبقة».":
        "For your own sticker, import your image and press Add as Layer.",
    "تفاعلات": "Reactions",
    "إشارات": "Signals",
    "أيادٍ": "Hands",
    "ألعاب": "Gaming",
    "قلوب": "Hearts",
    "سهم لليمين": "Arrow right",
    "سهم لليسار": "Arrow left",
    "سهم للأعلى": "Arrow up",
    "سهم للأسفل": "Arrow down",
    "دائرة تمييز": "Highlight circle",
    "مربّع تمييز": "Highlight box",
    "فقاعة كلام": "Speech bubble",
    "نجمة": "Star",
    "علامة صحّ": "Tick",
    "علامة خطأ": "Cross",
    "انفجار": "Burst",
    "خطّ تحته": "Underline",

    # ---------------------------------------------------------- النصوص
    "أضف نصًّا": "Add Text",
    "يضيف نصًّا على طبقة فوق الفيديو  (Ctrl+T)":
        "Adds text on a layer above the video  (Ctrl+T)",
    "أُضيف نصّ": "Text added",
    "اكتب نصّك هنا": "Type your text here",
    "النصّ": "Text",
    "نصّ": "Text",
    "تعذّر رسم النصّ": "Could not render the text",
    "لون النصّ": "Text colour",
    "مقاس النصّ": "Text size",
    "حدّ النصّ": "Text outline",
    "لليمين": "Right",
    "في الوسط": "Centre",
    "لليسار": "Left",

    # -------------------------------------------------------- الفلاتر
    "الفلتر": "Filter",
    "شدّة الفلتر": "Filter strength",
    "بلا فلتر": "None",
    "ضبابية": "Blur",
    "حِدّة": "Sharpen",
    "تعتيم الأطراف": "Vignette",
    "حبيبات فيلم": "Film grain",
    "دافئ": "Warm",
    "بارد": "Cool",
    "بنّي قديم": "Sepia",
    "باهت": "Faded",
    "ألوان صارخة": "Punchy",
    "انعكاس أفقي": "Mirror",

    # ------------------------------------------------- التحريك المستمرّ
    "التحريك": "Motion",
    "شدّة التحريك": "Motion strength",
    "بلا تحريك": "None",
    "تقريب بطيء": "Slow zoom in",
    "إبعاد بطيء": "Slow zoom out",
    "تحريك لليمين": "Pan right",
    "تحريك لليسار": "Pan left",
    "تحريك للأعلى": "Pan up",
    "تحريك للأسفل": "Pan down",
    "تقريب مع انزلاق": "Zoom and pan",
    "اهتزاز الكاميرا": "Camera shake",
    "يحرّر %s": "Editing %s",
    "مشروع جديد": "New project",
    "%d مقطعًا · %s": "%d clips · %s",
    "خطٌّ زمنيّ فارغ": "Empty timeline",
    "الانقلاب": "Flip",
    "شدّة الانقلاب": "Flip amount",
    "بلا انقلاب": "None",
    "انقلاب من اليمين": "Flip from right",
    "انقلاب من اليسار": "Flip from left",
    "انقلاب من الأعلى": "Flip from top",
    "انقلاب من الأسفل": "Flip from bottom",
    "بابٌ يُفتح يسارًا": "Door opens left",
    "بابٌ يُفتح يمينًا": "Door opens right",
    "الميلان": "Tilt",
    "شدّة الميلان": "Tilt amount",
    "بلا ميلان": "None",
    "ميلان يستقيم": "Tilt straightens",
    "ميلان يزداد": "Tilt grows",
    "ميلان ثابت لليسار": "Lean left",
    "ميلان ثابت لليمين": "Lean right",
    "تمايل": "Sway",
    "انقلاب بطاقة": "Card flip",
    "بلا أنيميشن": "None",
    "حرفًا حرفًا من اليمين": "Letters from right",
    "حرفًا حرفًا من اليسار": "Letters from left",
    "حرفًا حرفًا من الأسفل": "Letters from below",
    "سقوط الحروف": "Letters drop",
    "تكبير حرفًا حرفًا": "Letters pop",
    "دوران الحروف": "Letters spin",
    "ظهورٌ متتابع": "Staggered fade",

    # ------------------------------------------------------- الانتقالات
    "الانتقال": "Transition",
    "مدّة الانتقال": "Transition length",
    "بلا انتقال": "None",
    "تلاشٍ": "Fade",
    "تلاشٍ عبر الأسود": "Fade through black",
    "تلاشٍ عبر الأبيض": "Fade through white",
    "ذوبان": "Dissolve",
    "انزلاق لليسار": "Slide left",
    "انزلاق لليمين": "Slide right",
    "انزلاق للأعلى": "Slide up",
    "انزلاق للأسفل": "Slide down",
    "مسح لليسار": "Wipe left",
    "مسح لليمين": "Wipe right",
    "دائرة تتّسع": "Circle open",
    "دائرة تنغلق": "Circle close",
    "دوران": "Radial",
    "تبقّع": "Pixelize",
    "انسياب لليسار": "Smooth left",
    "مسح للأعلى": "Wipe up",
    "مسح للأسفل": "Wipe down",
    "قصٌّ دائري": "Circle crop",
    "قصٌّ مستطيل": "Rect crop",
    "تباعد": "Distance",
    "انسياب لليمين": "Smooth right",
    "انسياب للأعلى": "Smooth up",
    "انسياب للأسفل": "Smooth down",
    "فتحٌ رأسي": "Vertical open",
    "إغلاقٌ رأسي": "Vertical close",
    "فتحٌ أفقي": "Horizontal open",
    "إغلاقٌ أفقي": "Horizontal close",
    "قطريّ من أعلى اليسار": "Diagonal top-left",
    "قطريّ من أعلى اليمين": "Diagonal top-right",
    "قطريّ من أسفل اليسار": "Diagonal bottom-left",
    "قطريّ من أسفل اليمين": "Diagonal bottom-right",
    "شرائح لليسار": "Slices left",
    "شرائح لليمين": "Slices right",
    "شرائح للأعلى": "Slices up",
    "شرائح للأسفل": "Slices down",
    "ضبابٌ أفقي": "Horizontal blur",
    "تلاشٍ عبر الرمادي": "Fade grays",
    "مسح من أعلى اليسار": "Wipe top-left",
    "مسح من أعلى اليمين": "Wipe top-right",
    "مسح من أسفل اليسار": "Wipe bottom-left",
    "مسح من أسفل اليمين": "Wipe bottom-right",
    "عصرٌ أفقي": "Squeeze horizontal",
    "عصرٌ رأسي": "Squeeze vertical",
    "اندفاعٌ للداخل": "Zoom in",
    "تلاشٍ سريع": "Fade fast",
    "تلاشٍ بطيء": "Fade slow",
    "ريحٌ لليسار": "Wind left",
    "ريحٌ لليمين": "Wind right",
    "ريحٌ للأعلى": "Wind up",
    "ريحٌ للأسفل": "Wind down",
    "تغطيةٌ لليسار": "Cover left",
    "تغطيةٌ لليمين": "Cover right",
    "تغطيةٌ للأعلى": "Cover up",
    "تغطيةٌ للأسفل": "Cover down",
    "كشفٌ لليسار": "Reveal left",
    "كشفٌ لليمين": "Reveal right",
    "كشفٌ للأعلى": "Reveal up",
    "كشفٌ للأسفل": "Reveal down",

    # -------------------------------------------------------------- الطبقات
    "أضف كطبقة": "Add as Layer",
    "يضع الملف على طبقة جديدة فوق الفيديو، عند رأس التشغيل":
        "Places the file on a new layer above the video, at the playhead",
    "أُضيف %s على طبقة جديدة": "Added %s on a new layer",
    "أُضيفت طبقة": "Layer added",
    "حُذفت الطبقة": "Layer removed",
    "طبقة جديدة فوق": "New layer above",
    "احذف هذي الطبقة": "Delete this layer",
    "لا يمكن حذف المسار الأساس": "The base track cannot be deleted",
    "إخفاء الطبقة": "Hide layer",
    "إظهار الطبقة": "Show layer",
    "كتم الصوت": "Mute",
    "إلغاء الكتم": "Unmute",
    "قفل الطبقة": "Lock layer",
    "فكّ القفل": "Unlock",
    "اختر ملفًا من المكتبة أولًا": "Pick a file from the library first",
    "حجم الطبقة": "Layer size",
    "الموضع الأفقي": "Horizontal position",
    "الموضع الرأسي": "Vertical position",

    # ------------------------------------------------------- قائمة النقر
    "قسّم هنا": "Split here",
    "كرّر المقطع": "Duplicate clip",
    "احذف المقطع": "Delete clip",
    "انسخ التأثيرات": "Copy effects",
    "ألصق التأثيرات": "Paste effects",
    "صفّر التأثيرات": "Clear effects",
    "كُرِّر %s": "Duplicated %s",
    "نُسخت التأثيرات": "Effects copied",
    "لُصقت التأثيرات": "Effects pasted",
    "صُفِّرت التأثيرات": "Effects cleared",
    "لا توجد تأثيرات منسوخة": "No effects copied yet",

    # -------------------------------------------------------------- المعاينة
    "جاري تجهيز المعاينة…": "Preparing preview…",
    "أُلغي تجهيز المعاينة": "Preview preparation cancelled",
    "جاري تجهيز المعاينة…  %d٪": "Preparing preview…  %d%%",
    "يُرمَّز مرّة واحدة، ثم يشتغل فورًا ما لم تعدّل شيئًا.":
        "Rendered once, then plays instantly unless you change something.",
    "تشغيل": "Play",
    "إيقاف": "Pause",
    "مسافة": "Space",
    "ملء العرض": "Fit View",

    # -------------------------------------------------------- مكتبة الوسائط
    "الوسائط": "Media",
    "%d ملف": "%d file(s)",
    "لا توجد وسائط": "No media yet",
    "استورد فيديو أو صوتًا أو صورة، ثم انقر مرّتين لإضافته إلى الخط الزمني.":
        "Import a video, audio file or image, then double-click it to add it "
        "to the timeline.",
    "استورد وسائط": "Import Media",
    "استُورد %d ملف": "Imported %d file(s)",
    "تعذّر استيراد بعض الملفات": "Some files could not be imported",
    "ملفات الوسائط (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mp3 *.wav *.aac "
    "*.m4a *.png *.jpg *.jpeg);;كل الملفات (*)":
        "Media files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mp3 *.wav *.aac "
        "*.m4a *.png *.jpg *.jpeg);;All files (*)",

    # ------------------------------------------------------------ الخط الزمني
    "الخط الزمني": "Timeline",
    "فيديو": "Video",
    "صوت": "Audio",
    "اسحب لتحريك المقطع · اسحب حافّته للقصّ · انقره لتعديل تأثيراته":
        "Drag to move · drag an edge to trim · click to edit its effects",
    "تكبير": "Zoom in",
    "تصغير": "Zoom out",
    "ملء الخط الزمني": "Fit timeline",
    "أُضيف %s": "Added %s",
    "قُسِّم %s": "Split %s",
    "حُذف %s": "Deleted %s",
    "رأس التشغيل خارج المقطع المحدَّد":
        "The playhead is outside the selected clip",
    "تراجع": "Undo",
    "إعادة": "Redo",
    "جاهز": "Ready",

    # ------------------------------------------------------------- التأثيرات
    "التأثيرات": "Effects",
    "تصفير": "Reset",
    "لم يُحدَّد مقطع": "No clip selected",
    "انقر مقطعًا على الخط الزمني لتعديل ألوانه وسرعته وصوته.":
        "Click a clip on the timeline to adjust its colour, speed and audio.",
    "السطوع": "Brightness",
    "التباين": "Contrast",
    "التشبّع": "Saturation",
    "السرعة": "Speed",
    "الصوت": "Volume",
    "تلاشي الدخول": "Fade in",
    "تلاشي الخروج": "Fade out",
    " م.ث": " ms",
    "طبيعي": "Normal",
    "ساطع": "Vivid",
    "سينمائي": "Cinematic",
    "أبيض وأسود": "Grayscale",

    # ----------------------------------------------------------- الحركة
    "حركة الدخول": "In animation",
    "حركة الخروج": "Out animation",
    "مدّة الحركة": "Animation length",
    "بلا حركة": "None",
    "تكبير": "Zoom in",
    "تصغير": "Zoom out",
    "انزلاق من اليمين": "Slide from right",
    "انزلاق من اليسار": "Slide from left",
    "انزلاق من أعلى": "Slide from top",
    "انزلاق من أسفل": "Slide from bottom",

    # --------------------------------------------------------------- التصدير
    "تصدير الفيديو": "Export Video",
    "الملف الناتج": "Output file",
    "تصفّح…": "Browse…",
    "حفظ الفيديو": "Save video",
    "فيديو MP4 (*.mp4)": "MP4 video (*.mp4)",
    "الدقة": "Resolution",
    "مقاس المشروع": "Project size",
    "معدّل الإطارات": "Frame rate",
    "معدّل المشروع": "Project rate",
    "المرمّز": "Encoder",
    "الجودة": "Quality",
    "توليد إطارات بينيّة (أنعم حركة)":
        "Generate in-between frames (smoother motion)",
    "توليد الإطارات بطيء جدًا: نحو %d دقيقة لهذا المشروع. يعمل في الخلفية "
    "ويمكن إلغاؤه في أي لحظة.":
        "Frame generation is very slow: about %d minute(s) for this project. "
        "It runs in the background and can be cancelled at any time.",
    "المدّة %s · التصدير أسرع من الزمن الحقيقي على كرت الشاشة.":
        "Duration %s · export runs faster than real time on the GPU.",
    "صدّر": "Export",
    "إلغاء": "Cancel",
    "جاري التصدير…": "Exporting…",
    "%s من %s": "%s of %s",
    "تمّ التصدير": "Export complete",
    "%s\n\nالحجم: %.1f م.ب": "%s\n\nSize: %.1f MB",
    "صُدِّر إلى %s": "Exported to %s",
    "فشل التصدير": "Export failed",
    "تعذّر التصدير": "Could not export",
    "مجلد غير موجود": "Folder does not exist",
    "الخط الزمني فارغ": "The timeline is empty",
    "لا يوجد مسار فيديو لتصديره": "There is no video track to export",

    # ------------------------------------------------------- المشروع
    "احفظ المشروع": "Save Project",
    "احفظ المشروع  (Ctrl+S)": "Save project  (Ctrl+S)",
    "افتح مشروعًا": "Open Project",
    "افتح مشروعًا  (Ctrl+O)": "Open project  (Ctrl+O)",
    "مشروع Wun Cut (*.wcut);;كل الملفات (*)":
        "Wun Cut project (*.wcut);;All files (*)",
    "تعذّر الحفظ": "Could not save",
    "تعذّر فتح المشروع": "Could not open the project",
    "حُفظ إلى %s": "Saved to %s",
    "فُتح %s": "Opened %s",
    "هل تحفظ التعديلات قبل المتابعة؟": "Save your changes before continuing?",

    # --------------------------------------------------------- اللوحة
    "نسبة اللوحة": "Canvas ratio",
    "ما يملأ الفراغ حول المقطع": "What fills the space around the clip",
    "اللوحة %d×%d": "Canvas %d×%d",
    "يتبع المقطع": "Match clip",
    "16:9  عريض": "16:9  Wide",
    "9:16  عمودي": "9:16  Vertical",
    "1:1  مربّع": "1:1  Square",
    "4:5  إنستقرام": "4:5  Instagram",
    "أشرطة سوداء": "Black bars",
    "خلفية ضبابية": "Blurred background",

    # -------------------------------------------------------- الملصقات
    "ملصق": "Sticker",
    "الملصقات": "Stickers",
    "إيموجي وأشكال على طبقة فوق الفيديو  (Ctrl+K)":
        "Emoji and shapes on a layer above the video  (Ctrl+K)",
    "أُضيف ملصق %s": "Added sticker %s",
    "تعذّر رسم الملصق": "Could not render the sticker",
    "لون الأشكال": "Shape colour",
    "أشكال": "Shapes",
    "لملصق خاصّ بك، استورد صورتك واضغط «أضف كطبقة».":
        "For your own sticker, import your image and press Add as Layer.",
    "تفاعلات": "Reactions",
    "إشارات": "Signals",
    "أيادٍ": "Hands",
    "ألعاب": "Gaming",
    "قلوب": "Hearts",
    "سهم لليمين": "Arrow right",
    "سهم لليسار": "Arrow left",
    "سهم للأعلى": "Arrow up",
    "سهم للأسفل": "Arrow down",
    "دائرة تمييز": "Highlight circle",
    "مربّع تمييز": "Highlight box",
    "فقاعة كلام": "Speech bubble",
    "نجمة": "Star",
    "علامة صحّ": "Tick",
    "علامة خطأ": "Cross",
    "انفجار": "Burst",
    "خطّ تحته": "Underline",

    # ---------------------------------------------------------- النصوص
    "أضف نصًّا": "Add Text",
    "يضيف نصًّا على طبقة فوق الفيديو  (Ctrl+T)":
        "Adds text on a layer above the video  (Ctrl+T)",
    "أُضيف نصّ": "Text added",
    "اكتب نصّك هنا": "Type your text here",
    "النصّ": "Text",
    "نصّ": "Text",
    "تعذّر رسم النصّ": "Could not render the text",
    "لون النصّ": "Text colour",
    "مقاس النصّ": "Text size",
    "حدّ النصّ": "Text outline",
    "لليمين": "Right",
    "في الوسط": "Centre",
    "لليسار": "Left",

    # -------------------------------------------------------- الفلاتر
    "الفلتر": "Filter",
    "شدّة الفلتر": "Filter strength",
    "بلا فلتر": "None",
    "ضبابية": "Blur",
    "حِدّة": "Sharpen",
    "تعتيم الأطراف": "Vignette",
    "حبيبات فيلم": "Film grain",
    "دافئ": "Warm",
    "بارد": "Cool",
    "بنّي قديم": "Sepia",
    "باهت": "Faded",
    "ألوان صارخة": "Punchy",
    "انعكاس أفقي": "Mirror",

    # ------------------------------------------------- التحريك المستمرّ
    "التحريك": "Motion",
    "شدّة التحريك": "Motion strength",
    "بلا تحريك": "None",
    "تقريب بطيء": "Slow zoom in",
    "إبعاد بطيء": "Slow zoom out",
    "تحريك لليمين": "Pan right",
    "تحريك لليسار": "Pan left",
    "تحريك للأعلى": "Pan up",
    "تحريك للأسفل": "Pan down",
    "تقريب مع انزلاق": "Zoom and pan",
    "اهتزاز الكاميرا": "Camera shake",
    "يحرّر %s": "Editing %s",
    "مشروع جديد": "New project",
    "%d مقطعًا · %s": "%d clips · %s",
    "خطٌّ زمنيّ فارغ": "Empty timeline",
    "الانقلاب": "Flip",
    "شدّة الانقلاب": "Flip amount",
    "بلا انقلاب": "None",
    "انقلاب من اليمين": "Flip from right",
    "انقلاب من اليسار": "Flip from left",
    "انقلاب من الأعلى": "Flip from top",
    "انقلاب من الأسفل": "Flip from bottom",
    "بابٌ يُفتح يسارًا": "Door opens left",
    "بابٌ يُفتح يمينًا": "Door opens right",
    "الميلان": "Tilt",
    "شدّة الميلان": "Tilt amount",
    "بلا ميلان": "None",
    "ميلان يستقيم": "Tilt straightens",
    "ميلان يزداد": "Tilt grows",
    "ميلان ثابت لليسار": "Lean left",
    "ميلان ثابت لليمين": "Lean right",
    "تمايل": "Sway",
    "انقلاب بطاقة": "Card flip",
    "بلا أنيميشن": "None",
    "حرفًا حرفًا من اليمين": "Letters from right",
    "حرفًا حرفًا من اليسار": "Letters from left",
    "حرفًا حرفًا من الأسفل": "Letters from below",
    "سقوط الحروف": "Letters drop",
    "تكبير حرفًا حرفًا": "Letters pop",
    "دوران الحروف": "Letters spin",
    "ظهورٌ متتابع": "Staggered fade",

    # ------------------------------------------------------- الانتقالات
    "الانتقال": "Transition",
    "مدّة الانتقال": "Transition length",
    "بلا انتقال": "None",
    "تلاشٍ": "Fade",
    "تلاشٍ عبر الأسود": "Fade through black",
    "تلاشٍ عبر الأبيض": "Fade through white",
    "ذوبان": "Dissolve",
    "انزلاق لليسار": "Slide left",
    "انزلاق لليمين": "Slide right",
    "انزلاق للأعلى": "Slide up",
    "انزلاق للأسفل": "Slide down",
    "مسح لليسار": "Wipe left",
    "مسح لليمين": "Wipe right",
    "دائرة تتّسع": "Circle open",
    "دائرة تنغلق": "Circle close",
    "دوران": "Radial",
    "تبقّع": "Pixelize",
    "انسياب لليسار": "Smooth left",
    "مسح للأعلى": "Wipe up",
    "مسح للأسفل": "Wipe down",
    "قصٌّ دائري": "Circle crop",
    "قصٌّ مستطيل": "Rect crop",
    "تباعد": "Distance",
    "انسياب لليمين": "Smooth right",
    "انسياب للأعلى": "Smooth up",
    "انسياب للأسفل": "Smooth down",
    "فتحٌ رأسي": "Vertical open",
    "إغلاقٌ رأسي": "Vertical close",
    "فتحٌ أفقي": "Horizontal open",
    "إغلاقٌ أفقي": "Horizontal close",
    "قطريّ من أعلى اليسار": "Diagonal top-left",
    "قطريّ من أعلى اليمين": "Diagonal top-right",
    "قطريّ من أسفل اليسار": "Diagonal bottom-left",
    "قطريّ من أسفل اليمين": "Diagonal bottom-right",
    "شرائح لليسار": "Slices left",
    "شرائح لليمين": "Slices right",
    "شرائح للأعلى": "Slices up",
    "شرائح للأسفل": "Slices down",
    "ضبابٌ أفقي": "Horizontal blur",
    "تلاشٍ عبر الرمادي": "Fade grays",
    "مسح من أعلى اليسار": "Wipe top-left",
    "مسح من أعلى اليمين": "Wipe top-right",
    "مسح من أسفل اليسار": "Wipe bottom-left",
    "مسح من أسفل اليمين": "Wipe bottom-right",
    "عصرٌ أفقي": "Squeeze horizontal",
    "عصرٌ رأسي": "Squeeze vertical",
    "اندفاعٌ للداخل": "Zoom in",
    "تلاشٍ سريع": "Fade fast",
    "تلاشٍ بطيء": "Fade slow",
    "ريحٌ لليسار": "Wind left",
    "ريحٌ لليمين": "Wind right",
    "ريحٌ للأعلى": "Wind up",
    "ريحٌ للأسفل": "Wind down",
    "تغطيةٌ لليسار": "Cover left",
    "تغطيةٌ لليمين": "Cover right",
    "تغطيةٌ للأعلى": "Cover up",
    "تغطيةٌ للأسفل": "Cover down",
    "كشفٌ لليسار": "Reveal left",
    "كشفٌ لليمين": "Reveal right",
    "كشفٌ للأعلى": "Reveal up",
    "كشفٌ للأسفل": "Reveal down",

    # -------------------------------------------------------------- الطبقات
    "أضف كطبقة": "Add as Layer",
    "يضع الملف على طبقة جديدة فوق الفيديو، عند رأس التشغيل":
        "Places the file on a new layer above the video, at the playhead",
    "أُضيف %s على طبقة جديدة": "Added %s on a new layer",
    "أُضيفت طبقة": "Layer added",
    "حُذفت الطبقة": "Layer removed",
    "طبقة جديدة فوق": "New layer above",
    "احذف هذي الطبقة": "Delete this layer",
    "لا يمكن حذف المسار الأساس": "The base track cannot be deleted",
    "إخفاء الطبقة": "Hide layer",
    "إظهار الطبقة": "Show layer",
    "كتم الصوت": "Mute",
    "إلغاء الكتم": "Unmute",
    "قفل الطبقة": "Lock layer",
    "فكّ القفل": "Unlock",
    "اختر ملفًا من المكتبة أولًا": "Pick a file from the library first",
    "حجم الطبقة": "Layer size",
    "الموضع الأفقي": "Horizontal position",
    "الموضع الرأسي": "Vertical position",

    # ------------------------------------------------------- قائمة النقر
    "قسّم هنا": "Split here",
    "كرّر المقطع": "Duplicate clip",
    "احذف المقطع": "Delete clip",
    "انسخ التأثيرات": "Copy effects",
    "ألصق التأثيرات": "Paste effects",
    "صفّر التأثيرات": "Clear effects",
    "كُرِّر %s": "Duplicated %s",
    "نُسخت التأثيرات": "Effects copied",
    "لُصقت التأثيرات": "Effects pasted",
    "صُفِّرت التأثيرات": "Effects cleared",
    "لا توجد تأثيرات منسوخة": "No effects copied yet",

    # -------------------------------------------------------------- المعاينة
    "جاري تجهيز المعاينة…": "Preparing preview…",
    "أُلغي تجهيز المعاينة": "Preview preparation cancelled",
    "جاري تجهيز المعاينة…  %d٪": "Preparing preview…  %d%%",
    "يُرمَّز مرّة واحدة، ثم يشتغل فورًا ما لم تعدّل شيئًا.":
        "Rendered once, then plays instantly unless you change something.",
    "حرّك رأس التشغيل لتظهر المعاينة":
        "Move the playhead to see the preview",
    "لا يوجد مقطع عند رأس التشغيل": "No clip under the playhead",

    # ---------------------------------------------------------------- الجولة
    "جولة تعريفية بالبرنامج": "Take a tour of the app",
    "التالي": "Next",
    "السابق": "Back",
    "تخطّي": "Skip",
    "تمّ": "Done",
    "مكتبة الوسائط": "Media library",
    "استورد هنا كل ما ستستعمله: فيديو أو صوت أو صورة. النقر مرّتين على ملف "
    "يضعه في نهاية الخط الزمني.":
        "Bring in everything you will use here: video, audio or images. "
        "Double-clicking a file drops it at the end of the timeline.",
    "المعاينة": "Preview",
    "تعرض ما عند رأس التشغيل. مسافة للتشغيل والإيقاف، والساعة تحتها تبيّن "
    "موضعك من مدّة المشروع.":
        "Shows whatever sits under the playhead. Space plays and pauses, and "
        "the clock below tells you where you are in the project.",
    "قلب البرنامج. اسحب المقطع لتحريكه، واسحب حافّته لقصّه، و S تقسمه عند رأس "
    "التشغيل. الصور والموجة تحتها تريك أين تقصّ بلا تشغيل.":
        "The heart of the app. Drag a clip to move it, drag its edge to trim "
        "it, and press S to split it at the playhead. The thumbnails and "
        "waveform show you where to cut without playing anything.",
    "انقر مقطعًا فتفتح خصائصه: الألوان والسرعة والصوت والتلاشي، أو نظرة جاهزة "
    "بنقرة. المقطع المعدَّل تظهر عليه نقطة برتقالية.":
        "Click a clip to open its properties: colour, speed, volume and "
        "fades, or apply a ready-made look in one click. An edited clip gets "
        "an orange dot.",
    "التصدير": "Exporting",
    "يجمع الخط الزمني في ملف واحد بكرت الشاشة. من هنا أيضًا ترفع الدقة إلى 4K "
    "وتزيد معدّل الإطارات.":
        "Renders the whole timeline into one file using your GPU. This is "
        "also where you upscale to 4K and raise the frame rate.",
    "تراجع بلا خوف": "Undo without fear",
    "كل تعديل يُسجَّل: Ctrl+Z يرجع خطوة وCtrl+Y يعيدها. جرّب بحرّية، لا شيء "
    "يضيع.":
        "Every edit is recorded: Ctrl+Z steps back and Ctrl+Y steps forward. "
        "Experiment freely, nothing is lost.",

    # ------------------------------------------------------- الإطار والنافذة
    "عن البرنامج": "About",
    "لا يوجد ملف مفتوح": "No file open",
    "توجد تعديلات غير محفوظة": "Unsaved changes",
    "الرجوع إلى الأدوات": "Back to tools",
    "استعادة": "Restore",
    "إغلاق": "Close",
    "محرّر فيديو": "Video editor",
    "اختيار اللون": "Pick a colour",
    " بكسل": " px",

    # ---------------------------------------------------------------- اللغة
    "تغيير اللغة": "Change language",
    "تغيير لغة الواجهة  (يعيد تشغيل البرنامج)":
        "Change the interface language  (restarts the app)",
    "سيُعاد تشغيل البرنامج لتطبيق %s.\nأي عمل غير محفوظ سيضيع.":
        "The app will restart to switch to %s.\nAny unsaved work will be lost.",
    "تعذّرت إعادة التشغيل": "Could not restart",

    # -------------------------------------------------------------- التحديث
    "تحديث": "Update",
    "تحديث %s": "Update %s",
    "تحديث كبير": "Major update",
    "مزايا جديدة": "New features",
    "إصلاحات": "Fixes",
}
