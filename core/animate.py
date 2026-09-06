"""
حركات الدخول والخروج: أن يدخل المقطع الشاشة بدل أن يظهر فجأة.

الحركة جدولٌ لا شفرة: كل حركة سطرٌ يصف تكبيرها وإزاحتها بدلالة تقدّمها، فزيادة
حركة جديدة صفٌّ في الجدول لا دالّة جديدة في باني الأمر.

التقدّم يمرّ على تسارعٍ خارج (ease-out) لا خطّيًّا: الحركة الخطّية تبدو آليّة،
والعين تتوقّع بدايةً سريعة ونهايةً تهدأ. هذا وحده الفرق بين حركةٍ تبدو مصنوعة
وحركةٍ تبدو طبيعية.
"""

from __future__ import annotations

import math

# u: تقدّم الحركة بعد التسارع. صفرٌ = المقطع مزاح تمامًا، وواحدٌ = في مكانه.
# التكبير يساوي ١ عند u=1 والإزاحة تساوي ٠، فتُضرب التكبيرات وتُجمع الإزاحات
# حين تجتمع حركتا دخول وخروج على المقطع نفسه.
ANIMATIONS = [
    ("", "بلا حركة", {}),
    ("zoom_in", "تكبير", {"zoom": "(0.70+0.30*%(u)s)"}),
    ("zoom_out", "تصغير", {"zoom": "(1.35-0.35*%(u)s)"}),
    ("slide_right", "انزلاق من اليمين", {"dx": "((1-%(u)s)*W)"}),
    ("slide_left", "انزلاق من اليسار", {"dx": "(-(1-%(u)s)*W)"}),
    ("slide_down", "انزلاق من أعلى", {"dy": "(-(1-%(u)s)*H)"}),
    ("slide_up", "انزلاق من أسفل", {"dy": "((1-%(u)s)*H)"}),
]

# التحريك المستمرّ (Ken Burns): يمشي على طول المقطع كلّه لا على طرفيه.
#
# كل تحريكٍ فيه انزلاق يفرض تكبيرًا زائدًا: بلا فائضٍ خارج اللوحة ينزلق المشهد
# إلى السواد. الفائض هو (s-1)، ونصفه هو أقصى إزاحة ممكنة في كل اتجاه.
MOTIONS = [
    ("", "بلا تحريك", None),
    ("zoom_in", "تقريب بطيء", "zoom_in"),
    ("zoom_out", "إبعاد بطيء", "zoom_out"),
    ("pan_right", "تحريك لليمين", "pan_right"),
    ("pan_left", "تحريك لليسار", "pan_left"),
    ("pan_up", "تحريك للأعلى", "pan_up"),
    ("pan_down", "تحريك للأسفل", "pan_down"),
    ("zoom_pan", "تقريب مع انزلاق", "zoom_pan"),
    ("shake", "اهتزاز الكاميرا", "shake"),
]

MOTION_NAMES = [key for key, _label, _kind in MOTIONS]
MOTION_LABELS = {key: label for key, label, _kind in MOTIONS}
_MOTION_KINDS = {key: kind for key, _label, kind in MOTIONS}

MOTION_MIN, MOTION_MAX, MOTION_DEFAULT = 0, 100, 50
REACH = 0.34                # أقصى تكبير زائد عند الشدّة القصوى


def motion(name, amount, seconds, shift=0.0):
    """
    (تكبير، إزاحة أفقية، إزاحة رأسية) للتحريك المستمرّ، أو None بلا تحريك.

    التقدّم خطّيّ لا متسارع: التحريك البطيء يُقرأ كحركة كاميرا ثابتة، وأي
    تسارعٍ فيه يجعلها تبدو كأنها تتعثّر.
    """
    kind = _MOTION_KINDS.get(name or "")
    if not kind:
        return None
    depth = max(0.0, min(100, amount)) / 100.0 * REACH
    if depth <= 0:
        return None
    span = max(0.04, seconds)
    p = "min(%s/%.4f,1)" % (_clock(shift), span)
    grown = 1.0 + depth
    half = depth / 2.0          # أقصى إزاحة كنسبةٍ من مقاس اللوحة

    if kind == "zoom_in":
        return ("(1+%.5f*%s)" % (depth, p), "0", "0")
    if kind == "zoom_out":
        return ("(%.5f-%.5f*%s)" % (grown, depth, p), "0", "0")
    if kind == "zoom_pan":
        return ("(1+%.5f*%s)" % (depth, p),
                "(%.5f*W*%s)" % (-half, p), "0")

    if kind == "shake":
        # اهتزازُ يدٍ لا رجفةُ محرّك: ترددان غير متناسبين على كل محور، فلا
        # تتكرّر الدورة فتُقرأ آليّة. مجموع المعاملين واحد، فالإزاحة لا
        # تتجاوز السعة أبدًا ولا ينكشف سوادٌ من خلف اللوحة.
        reach = half * 0.5              # نصفُ ما تبلغه بقيّةُ التحريكات
        clock = _clock(shift)
        return ("%.5f" % grown,
                "(%.5f*W*(0.6*sin(6.283*%s)+0.4*sin(11.09*%s+0.9)))"
                % (reach, clock, clock),
                "(%.5f*H*(0.6*sin(4.111*%s+1.7)+0.4*sin(9.677*%s)))"
                % (reach, clock, clock))

    swing = "(%.5f*%s*(1-2*%s))" % (half, "%s", p)
    if kind == "pan_right":
        return ("%.5f" % grown, swing % "W", "0")
    if kind == "pan_left":
        return ("%.5f" % grown, "(-%s)" % (swing % "W"), "0")
    if kind == "pan_up":
        return ("%.5f" % grown, "0", swing % "H")
    return ("%.5f" % grown, "0", "(-%s)" % (swing % "H"))


# الميلان: دورانٌ حول مركز الطبقة. يُطبَّق بمرشّح rotate على تيّار الطبقة
# وحدها - لا على المسار الأساس - لأن الطبقة تُركَّب بقناة شفافية، فتخرج
# البطاقة مائلةً بأركانٍ نظيفة. على الأساس كانت ستظهر أركانٌ سوداء.
#
# المفتاح، التسمية، (زاوية البداية، زاوية النهاية، تمايلٌ مستمرّ)
TILTS = [
    ("", "بلا ميلان", None),
    ("tilt_in", "ميلان يستقيم", (1.0, 0.0, 0.0)),
    ("tilt_out", "ميلان يزداد", (0.0, 1.0, 0.0)),
    ("tilt_left", "ميلان ثابت لليسار", (-1.0, -1.0, 0.0)),
    ("tilt_right", "ميلان ثابت لليمين", (1.0, 1.0, 0.0)),
    ("sway", "تمايل", (0.0, 0.0, 1.0)),
    ("card_flip", "انقلاب بطاقة", (4.0, 0.0, 0.0)),
]

TILT_NAMES = [key for key, _label, _spec in TILTS]
TILT_LABELS = {key: label for key, label, _spec in TILTS}
_TILT_SPECS = {key: spec for key, _label, spec in TILTS}

TILT_MIN, TILT_MAX, TILT_DEFAULT = 0, 100, 40
TILT_REACH = 0.42           # أقصى ميلٍ بالراديان عند الشدّة القصوى


def turn(name, amount, seconds, shift=0.0):
    """
    زاوية الميلان بالراديان كتعبير FFmpeg، أو None بلا ميلان.

    الزاوية تُمرَّر إلى مرشّح rotate، وهو يقبل الزمن `t` مباشرةً - على خلاف
    perspective الذي لا يعرف `t` ويحتاج رقم الإطار.
    """
    spec = _TILT_SPECS.get(name or "")
    if spec is None:
        return None
    depth = max(0.0, min(100, amount)) / 100.0 * TILT_REACH
    if depth <= 0:
        return None
    first, last, waving = spec
    span = max(0.04, seconds)
    clock = _clock(shift)
    if waving:
        # تمايلٌ لا يتكرّر بانتظام: ترددان غير متناسبين
        return ("(%.5f*(0.62*sin(1.7*%s)+0.38*sin(2.9*%s+0.7)))"
                % (depth, clock, clock))
    p = "min(%s/%.4f,1)" % (clock, span)
    return "(%.5f+%.5f*%s)" % (first * depth, (last - first) * depth, p)


# الانقلاب ثلاثيّ الأبعاد: البطاقة تدور حول محورٍ فتُقرأ كأنها لوحٌ في
# فضاء. يُبنى بمرشّح perspective: العرض يضيق بجيب التمام، والحافّة القريبة
# تطول والبعيدة تقصر - وهذا الفرقُ بين انقلابٍ حقيقيّ وضغطٍ أفقيّ مسطّح.
#
# وperspective لا يعرف `t` بحال - جُرّب فرفضه - فيقرأ رقمَ الإطار `on`
# ويحتاج معدّلَ الإطارات ليحوّله زمنًا. لهذا يأخذ `rate` بخلاف بقيّة الجداول.
#
# المفتاح، التسمية، (المحور، اتّجاه العمق، المفصلة)
# المفصلة: صفرٌ في الوسط، و١- عند الحافّة اليسرى/العليا، و١+ المقابلة.
FLIPS = [
    ("", "بلا انقلاب", None),
    ("flip_right", "انقلاب من اليمين", ("y", 1.0, 0.0)),
    ("flip_left", "انقلاب من اليسار", ("y", -1.0, 0.0)),
    ("flip_up", "انقلاب من الأعلى", ("x", 1.0, 0.0)),
    ("flip_down", "انقلاب من الأسفل", ("x", -1.0, 0.0)),
    ("door_left", "بابٌ يُفتح يسارًا", ("y", 1.0, -1.0)),
    ("door_right", "بابٌ يُفتح يمينًا", ("y", -1.0, 1.0)),
]

FLIP_NAMES = [key for key, _label, _spec in FLIPS]
FLIP_LABELS = {key: label for key, label, _spec in FLIPS}
_FLIP_SPECS = {key: spec for key, _label, spec in FLIPS}

FLIP_MIN, FLIP_MAX, FLIP_DEFAULT = 0, 100, 70
FLIP_ANGLE = 1.40           # أقصى زاويةٍ بالراديان عند الشدّة القصوى
FLIP_DEPTH = 0.45           # كم تطول الحافّة القريبة وتقصر البعيدة


def warp(name, amount, seconds, rate, window):
    """
    مرشّح perspective للانقلاب، أو None بلا انقلاب.

    `window` زمن الدخول بالثواني: تنقلب البطاقة فيه ثم تستقرّ مسطّحةً.
    """
    spec = _FLIP_SPECS.get(name or "")
    if spec is None:
        return None
    reach = max(0.0, min(100, amount)) / 100.0 * FLIP_ANGLE
    if reach <= 0:
        return None
    axis, way, hinge = spec
    span = max(1.0, float(window) * float(rate))
    # الزاوية تنطفئ بتسارعٍ خارج، فتهدأ البطاقة عند استقرارها لا تصطدم
    left = "(1-%s)" % _ease("min(on/%.4f,1)" % span)
    turn = "(%.5f*%s)" % (reach, left)
    flat = "cos(%s)" % turn
    lean = "(%.5f*%.1f*sin(%s))" % (FLIP_DEPTH, way, turn)

    if axis == "y":
        if hinge < 0:                       # مفصلةٌ عند الحافّة اليسرى
            near, far = "0", "W*%s" % flat
        elif hinge > 0:                     # وعند اليمنى
            near, far = "W-W*%s" % flat, "W"
        else:
            near = "W/2-W/2*%s" % flat
            far = "W/2+W/2*%s" % flat
        tall = "H/2*(1+%s)" % lean
        short = "H/2*(1-%s)" % lean
        return ("perspective=x0='%s':y0='H/2-%s':x1='%s':y1='H/2-%s'"
                ":x2='%s':y2='H/2+%s':x3='%s':y3='H/2+%s'"
                ":sense=destination:eval=frame"
                % (near, tall, far, short, near, tall, far, short))

    top = "H/2-H/2*%s" % flat
    bottom = "H/2+H/2*%s" % flat
    wide = "W/2*(1+%s)" % lean
    narrow = "W/2*(1-%s)" % lean
    return ("perspective=x0='W/2-%s':y0='%s':x1='W/2+%s':y1='%s'"
            ":x2='W/2-%s':y2='%s':x3='W/2+%s':y3='%s'"
            ":sense=destination:eval=frame"
            % (wide, top, wide, top, narrow, bottom, narrow, bottom))


NAMES = [key for key, _label, _spec in ANIMATIONS]
LABELS = {key: label for key, label, _spec in ANIMATIONS}
_SPECS = {key: spec for key, _label, spec in ANIMATIONS}

MIN_MS, MAX_MS, DEFAULT_MS = 200, 2000, 600


def _ease(progress):
    """تسارع خارج تكعيبيّ: سريع في أوّله، يهدأ في آخره."""
    return "(1-pow(1-%s,3))" % progress


def _clock(shift):
    """
    زمن المقطع من زمن الرسم البياني.

    إزاحات الطبقات تُحسب داخل مرشّح overlay، و`t` هناك زمن الخط الزمني لا زمن
    المقطع: مقطعٌ يبدأ عند الثانية ١١ ترى حركةُ خروجه أن عمرها تجاوز مدّته
    فتدفعه خارج اللوحة من أوّل إطار. `shift` يردّ الساعة إلى بداية المقطع.
    """
    return "t" if not shift else "(t-%.4f)" % shift


def _u(slot, seconds, window, shift=0.0):
    """
    تقدّم الحركة: صفرٌ حين يكون المقطع مزاحًا وواحدٌ حين يستقرّ.

    الدخول يبدأ مزاحًا ويستقرّ، والخروج عكسه: يبقى مستقرًّا حتى تبقى `window`
    من آخر المقطع ثم ينزاح.
    """
    window = max(0.04, min(window, seconds))
    clock = _clock(shift)
    if slot == "in":
        return _ease("min(%s/%.4f,1)" % (clock, window))
    start = max(0.0, seconds - window)
    return _ease("(1-min(max((%s-%.4f)/%.4f,0),1))" % (clock, start, window))


def transform(anim_in, anim_out, seconds, window, motion_name="",
              motion_amount=MOTION_DEFAULT, shift=0.0):
    """
    يرجع (تكبير، إزاحة أفقية، إزاحة رأسية) كتعبيرات FFmpeg، أو None بلا حركة.

    التعبيرات بلغة مرشّحات FFmpeg: `t` زمن الإطار، و`W`/`H` مقاس اللوحة داخل
    overlay.

    الحركات والتحريك المستمرّ يجتمعان هنا في مكانٍ واحد: التكبيرات تُضرب
    (كلّها ١ عند الحياد) والإزاحات تُجمع (كلّها ٠). لو حُسب كلٌّ منهما وحده
    لتنازعا على الموضع نفسه.
    """
    zooms, xs, ys = [], [], []
    steady = motion(motion_name, motion_amount, seconds, shift)
    if steady is not None:
        zooms.append("(%s)" % steady[0])
        if steady[1] != "0":
            xs.append(steady[1])
        if steady[2] != "0":
            ys.append(steady[2])
    for slot, name in (("in", anim_in), ("out", anim_out)):
        spec = _SPECS.get(name or "")
        if not spec:
            continue
        eased = _u(slot, seconds, window, shift)
        if "zoom" in spec:
            zooms.append(spec["zoom"] % {"u": eased})
        if "dx" in spec:
            xs.append(spec["dx"] % {"u": eased})
        if "dy" in spec:
            ys.append(spec["dy"] % {"u": eased})

    if not (zooms or xs or ys):
        return None
    return ("*".join(zooms) or "1",
            "+".join(xs) or "0",
            "+".join(ys) or "0")


def sample(anim_in, anim_out, seconds, window, at, canvas,
           motion_name="", motion_amount=MOTION_DEFAULT):
    """
    قيم التحويل عند لحظة بعينها: (تكبير، إزاحة أفقية، إزاحة رأسية) بالبكسل.

    المعاينة ترسم إطارًا واحدًا، فلا يصلها زمنٌ يتغيّر: تحتاج الرقم عند اللحظة
    لا التعبير. نحسبها من التعابير نفسها لا من نسخةٍ ثانية منها، وإلا انحرفت
    المعاينة عن التصدير بلا أن يلاحظ أحد.
    """
    made = transform(anim_in, anim_out, seconds, window, motion_name,
                     motion_amount)
    if made is None:
        return 1.0, 0.0, 0.0
    scope = {"pow": pow, "min": min, "max": max, "sin": math.sin,
             "t": float(at), "W": float(canvas[0]), "H": float(canvas[1])}
    return tuple(eval(expr, {"__builtins__": {}}, scope) for expr in made)


def demo():
    """فحص ذاتي: الحياد، والاتجاه، واجتماع الحركتين."""
    assert NAMES[0] == "" and len(NAMES) == 7
    assert transform("", "", 5, 0.6) is None, "بلا حركة أنتج تحويلًا"
    assert transform("لا-توجد", "", 5, 0.6) is None, "اسم مجهول لم يُتجاهل"

    zoom, dx, dy = transform("zoom_in", "", 5, 0.6)
    assert dx == "0" and dy == "0", (dx, dy)
    assert "min(t/0.6000,1)" in zoom, zoom

    # القيم الفعلية عبر sample نفسها التي تستعملها المعاينة
    def value(kind, t, a_in="", a_out="", seconds=5, window=0.6):
        got = sample(a_in, a_out, seconds, window, t, (1920, 1080))
        return got[{"zoom": 0, "dx": 1, "dy": 2}[kind]]

    assert sample("", "", 5, 0.6, 1.0, (1920, 1080)) == (1.0, 0.0, 0.0)

    zoom, _dx, _dy = transform("zoom_in", "", 5, 0.6)
    assert abs(value("zoom", 0.0, "zoom_in") - 0.70) < 1e-6
    assert abs(value("zoom", 0.6, "zoom_in") - 1.00) < 1e-6
    assert abs(value("zoom", 4.0, "zoom_in") - 1.00) < 1e-6, "لم يستقرّ"
    # التسارع الخارج: نصف الزمن يقطع أكثر من نصف المسافة
    half = (value("zoom", 0.3, "zoom_in") - 0.70) / 0.30
    assert half > 0.6, "الحركة خطّية لا متسارعة: %.2f" % half

    assert abs(value("dx", 0.0, "", "slide_left", 5, 0.8)) < 1e-6,         "الخروج أزاح المقطع من أوّله"
    assert abs(value("dx", 4.2, "", "slide_left", 5, 0.8)) < 1e-6,         "الخروج بدأ قبل نافذته"
    assert abs(value("dx", 5.0, "", "slide_left", 5, 0.8) + 1920) < 1e-3

    # حركتان معًا: الدخول تكبير والخروج انزلاق
    assert abs(value("zoom", 2.5, "zoom_in", "slide_up") - 1.0) < 1e-6
    assert abs(value("dx", 2.5, "zoom_in", "slide_up")) < 1e-6
    assert abs(value("zoom", 0.0, "zoom_out", "slide_up", 4, 0.5) - 1.35) < 1e-6
    assert abs(value("dy", 4.0, "zoom_out", "slide_up", 4, 0.5) - 1080) < 1e-3

    # نافذة أطول من المقطع تُقصّ فلا يخرج التعبير عن حدّه
    assert abs(value("zoom", 0.3, "zoom_in", "", 0.3, 5.0) - 1.0) < 1e-6,         "النافذة الأطول من المقطع لم تُقصّ"

    # --- التحريك المستمرّ ---
    assert motion("", 50, 5) is None and motion("zoom_in", 0, 5) is None
    assert motion("لا-يوجد", 50, 5) is None

    def steady(name, at, amount=100, seconds=5.0, canvas=(1920, 1080)):
        got = sample("", "", seconds, 0.6, at, canvas, name, amount)
        return got

    # التقريب يبدأ من ١ وينتهي عند ١+المدى، والإبعاد عكسه
    assert abs(steady("zoom_in", 0.0)[0] - 1.0) < 1e-4
    assert abs(steady("zoom_in", 5.0)[0] - (1 + REACH)) < 1e-4
    assert abs(steady("zoom_out", 0.0)[0] - (1 + REACH)) < 1e-4
    assert abs(steady("zoom_out", 5.0)[0] - 1.0) < 1e-4

    # التحريك خطّيّ: منتصف الزمن عند منتصف المسافة تمامًا
    middle = steady("zoom_in", 2.5)[0]
    assert abs(middle - (1 + REACH / 2)) < 1e-4, middle

    # الانزلاق لا يكشف سوادًا أبدًا: الإزاحة لا تتجاوز نصف الفائض
    for name in ("pan_right", "pan_left", "pan_up", "pan_down", "zoom_pan"):
        for at in (0.0, 1.2, 2.5, 3.8, 5.0):
            zoom, dx, dy = steady(name, at)
            slack_x = (zoom - 1) / 2 * 1920 + 0.5
            slack_y = (zoom - 1) / 2 * 1080 + 0.5
            assert zoom >= 1.0, (name, at, zoom)
            assert abs(dx) <= slack_x,                 "%s عند %.1f يكشف سوادًا أفقيًّا: %.1f > %.1f" % (name, at,
                                                                 dx, slack_x)
            assert abs(dy) <= slack_y,                 "%s عند %.1f يكشف سوادًا رأسيًّا: %.1f > %.1f" % (name, at,
                                                                 dy, slack_y)

    # ويتحرّك فعلًا: الطرفان مختلفان.
    # التكبير نسبةٌ والإزاحة بالبكسل، فلكلٍّ عتبته: عتبةٌ واحدة تُسقط
    # التقريبَ الصحيح لأن فرقه 0.34 لا مئات البكسلات.
    for name in MOTION_NAMES[1:]:
        first, last = steady(name, 0.0), steady(name, 5.0)
        moved = (abs(first[0] - last[0]) > 0.05
                 or abs(first[1] - last[1]) > 8
                 or abs(first[2] - last[2]) > 8)
        assert moved, "%s لا يتحرّك: %s -> %s" % (name, first, last)

    # يجتمع مع حركة الدخول بلا تنازع: التكبيران يُضربان
    both = sample("zoom_in", "", 5, 0.6, 0.0, (1920, 1080), "zoom_in", 100)
    assert abs(both[0] - 0.70 * 1.0) < 1e-3, both[0]

    # الاهتزاز يتذبذب ولا ينجرف: هذا ما يفرّقه عن التحريك الانزلاقيّ.
    # بلا هذا الفحص يمرّ تعبيرٌ يزحف في اتّجاهٍ واحد على أنه اهتزاز.
    walk = [steady("shake", at / 20.0, 60, 6.0)[1] for at in range(120)]
    turns = sum(1 for i in range(1, len(walk) - 1)
                if (walk[i] - walk[i - 1]) * (walk[i + 1] - walk[i]) < 0)
    assert turns >= 8, "الاهتزاز ينجرف ولا يتذبذب: %d انعطافة" % turns
    reach = max(abs(v) for v in walk)
    assert reach > 4, "الاهتزاز لا يُرى: %.1f بكسل" % reach
    # وهادئ: أقلّ من التحريكات الأخرى عند الشدّة نفسها
    slide = max(abs(steady("pan_right", at / 20.0, 60, 6.0)[1])
                for at in range(120))
    assert reach < slide, "الاهتزاز أعنف من الانزلاق: %.0f مقابل %.0f" % (
        reach, slide)
    print("الاهتزاز: %d انعطافة في ٦ ث · مداه %.0f بكسل مقابل %.0f للانزلاق ✓"
          % (turns, reach, slide))

    print("التحريك المستمرّ: %d نوعًا، لا انزلاق إلى السواد ✓"
          % (len(MOTION_NAMES) - 1))
    # --- الانقلاب: يبدأ مائلًا ويستقيم، ولا يقلب البطاقة على ظهرها ---
    assert FLIP_NAMES[0] == "" and len(FLIP_NAMES) == 7
    assert warp("", 70, 5, 60, 1.0) is None
    assert warp("flip_right", 0, 5, 60, 1.0) is None, "شدّةٌ صفر أنتجت انقلابًا"

    def corners(style, at, amount=70, rate=60.0, window=1.0):
        """قيم الأركان الثمانية عند إطارٍ بعينه."""
        text = warp(style, amount, 5.0, rate, window)
        scope = {"cos": math.cos, "sin": math.sin, "pow": pow,
                 "min": min, "max": max, "on": at * rate,
                 "W": 1920.0, "H": 1080.0}
        out = {}
        for part in text.split("perspective=")[1].split(":"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            if key in ("sense", "eval"):
                continue
            out[key] = eval(value.strip("'"), {"__builtins__": {}}, scope)
        return out

    # عند الشدّة القصوى تكاد البطاقة تختفي حافّةً، وعند الاستقرار تملأ
    begin = corners("flip_right", 0.0, amount=100)
    end = corners("flip_right", 2.0, amount=100)
    wide_begin = begin["x1"] - begin["x0"]
    wide_end = end["x1"] - end["x0"]
    assert wide_begin < wide_end * 0.30,         "البطاقة لا تضيق عند الدخول: %.0f ثم %.0f" % (wide_begin, wide_end)
    # والشدّة تعني شيئًا: الأقوى أضيقُ بدايةً
    soft = corners("flip_right", 0.0, amount=40)
    assert (soft["x1"] - soft["x0"]) > wide_begin * 1.5,         "الشدّة لا تغيّر الانقلاب"
    assert abs(wide_end - 1920) < 2, "لم تستقرّ مسطّحةً: %.1f" % wide_end
    # الحافّة القريبة أطول من البعيدة: هذا ما يجعله منظورًا لا ضغطًا
    near = begin["y2"] - begin["y0"]
    far = begin["y3"] - begin["y1"]
    assert near > far * 1.2, "بلا عمق: القريبة %.0f والبعيدة %.0f" % (near, far)
    # وعند الاستقرار يتساويان
    assert abs((end["y2"] - end["y0"]) - (end["y3"] - end["y1"])) < 2

    # البابُ مفصلته ثابتة: حافّةٌ لا تتحرّك
    door = corners("door_left", 0.0, amount=100)
    assert abs(door["x0"]) < 1 and abs(door["x2"]) < 1,         "مفصلة الباب تتحرّك: %.1f" % door["x0"]

    # المحور الأفقيّ يضيق ارتفاعًا لا عرضًا
    lying = corners("flip_up", 0.0, amount=100)
    assert (lying["y2"] - lying["y0"]) < 1080 * 0.30, "لم ينقلب أفقيًّا"
    assert abs((lying["x1"] - lying["x0"]) - 1920) > 200,         "المحور الأفقيّ لم يُنتج عمقًا عرضيًّا"
    print("الانقلاب: %d أنماط · يضيق %.0f←%.0f ومنظورُه %.0f/%.0f ✓"
          % (len(FLIP_NAMES) - 1, wide_begin, wide_end, near, far))

    print("core/animate: كل الفحوص سليمة (%d حركة)" % (len(NAMES) - 1))


if __name__ == "__main__":
    demo()
