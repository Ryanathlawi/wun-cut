"""
نموذج المشروع: المسارات والمقاطع والزمن، مع تراجع.

الزمن بالإطارات لا بالثواني العشرية. مقطع يبدأ عند 1.4666666 ثانية يتراكم
خطؤه عبر عشرات المقاطع حتى ينزاح الصوت عن الصورة، والإطار عدد صحيح لا يكذب.
التحويل إلى ثوانٍ يصير عند الحافة وحدها: العرض للمستخدم وأوامر FFmpeg.

لا Qt هنا: يجب أن يُقاد كل تحرير من سطر الأوامر بلا نافذة.
"""

from __future__ import annotations

import json
import os
import uuid
from fractions import Fraction

SCHEMA = 1

# التأثيرات: الاسم -> (أدنى، أقصى، القيمة المحايدة)
# المحايدة لا تُخزَّن، فيبقى الملف المحفوظ نظيفًا ويصير سؤال "هل على المقطع
# تأثير؟" مجرّد فحص لقاموس فارغ.
EFFECTS = {
    "brightness": (-100, 100, 0),
    "contrast": (-100, 100, 0),
    "saturation": (-100, 100, 0),
    "speed": (25, 400, 100),        # نسبة مئوية من السرعة الأصلية
    "volume": (0, 200, 100),
    "fade_in": (0, 5000, 0),        # مللي ثانية
    "fade_out": (0, 5000, 0),
    "anim_ms": (200, 2000, 600),    # طول حركة الدخول/الخروج
    "layer_x": (-100, 100, 0),      # إزاحة أفقية، ٪ من عرض اللوحة
    "layer_y": (-100, 100, 0),
    "layer_scale": (10, 300, 100),  # حجم الطبقة، ٪
    "filter_amount": (0, 100, 60),  # شدّة الفلتر البصري
    "trans_ms": (100, 3000, 600),   # مدّة الانتقال إلى ما قبله
    "text_size": (16, 220, 64),     # مقاس النصّ بالبكسل
    "text_outline": (0, 100, 45),   # سماكة حدّ النصّ
    "motion_amount": (0, 100, 50),
    "tilt_amount": (0, 100, 40),    # شدّة الميلان
    "flip_amount": (0, 100, 70),    # شدّة الانقلاب
}

# أسماء الحركات في core.animate. تُخزَّن نصًّا لا رقمًا، فهي خارج EFFECTS.
ANIM_SLOTS = ("anim_in", "anim_out")

# خانات نصّية أخرى تُحفظ مع المقطع: اسم الفلتر البصري
TEXT_SLOTS = ANIM_SLOTS + ("filter", "trans", "motion", "text",
                           "text_colour", "text_align", "text_anim",
                           "tilt", "flip")


class Clip:
    """قصاصة على مسار: مقطعٌ من ملف مصدر، موضوعٌ عند إطار بداية."""

    def __init__(self, source, start, duration, offset=0, name="", cid=None,
                 effects=None, anim_in="", anim_out="", filter="", trans="", motion="",
                 text="", text_colour="", text_align="",
                 text_anim="", tilt="", flip=""):
        # معرّف ثابت: التراجع يعيد بناء الأجسام، فتمسك الواجهة المعرّف لا الجسم
        self.cid = cid or uuid.uuid4().hex[:8]
        self.source = source        # مسار الملف
        self.start = int(start)     # إطار البداية على الخط الزمني
        self.duration = int(duration)
        self.offset = int(offset)   # إطار البداية داخل الملف المصدر
        self.name = name or os.path.basename(source)
        self.effects = {k: v for k, v in (effects or {}).items()
                        if k in EFFECTS}
        self.anim_in = anim_in or ""        # حركة الدخول
        self.anim_out = anim_out or ""      # حركة الخروج
        self.filter = filter or ""          # اسم الفلتر البصري
        self.trans = trans or ""            # الانتقال من المقطع السابق
        self.motion = motion or ""          # تحريك مستمرّ على طول المقطع
        # مقطع النصّ: مصدره صورة مرسومة، وهذي خصائصها ليُعاد رسمها عند التعديل
        self.text = text or ""
        self.text_colour = text_colour or "#FFFFFF"
        self.text_align = text_align or "center"
        self.text_anim = text_anim or ""
        self.tilt = tilt or ""
        self.flip = flip or ""

    @property
    def end(self):
        return self.start + self.duration

    def overlaps(self, other):
        return self.start < other.end and other.start < self.end

    # ------------------------------------------------------------ التأثيرات

    def effect(self, name):
        """قيمة التأثير، أو المحايدة إن لم يُضبط."""
        return self.effects.get(name, EFFECTS[name][2])

    def set_effect(self, name, value):
        low, high, neutral = EFFECTS[name]
        value = max(low, min(high, int(value)))
        if value == neutral:
            self.effects.pop(name, None)
        else:
            self.effects[name] = value
        return value

    def clear_effects(self):
        self.effects.clear()
        self.anim_in = self.anim_out = self.filter = self.trans = ""
        self.motion = ""

    @property
    def is_text(self):
        return bool(self.text)

    @property
    def animated(self):
        return bool(self.anim_in or self.anim_out)

    @property
    def touched(self):
        """هل على المقطع أيّ تعديل؟ تستعمله الواجهة لعلامة المقطع المعدَّل."""
        return (bool(self.effects) or self.animated or bool(self.filter)
                or bool(self.trans) or bool(self.motion))

    @property
    def speed(self):
        """معامل السرعة. المدّة على الخط هي المرجع، والسرعة تحدّد كم يُستهلك
        من المصدر لملئها: سرعة ٢٠٠٪ تبتلع ضعف الإطارات في المدّة نفسها."""
        return self.effect("speed") / 100.0

    @property
    def source_frames(self):
        return max(1, int(round(self.duration * self.speed)))

    def to_dict(self):
        data = {"cid": self.cid, "source": self.source, "start": self.start,
                "duration": self.duration, "offset": self.offset,
                "name": self.name}
        if self.effects:
            data["effects"] = dict(self.effects)
        for slot in TEXT_SLOTS:
            if getattr(self, slot):
                data[slot] = getattr(self, slot)
        return data

    @classmethod
    def from_dict(cls, data):
        return cls(data["source"], data["start"], data["duration"],
                   data.get("offset", 0), data.get("name", ""),
                   data.get("cid"), data.get("effects"),
                   data.get("anim_in", ""), data.get("anim_out", ""),
                   data.get("filter", ""), data.get("trans", ""),
                   data.get("motion", ""),
                   data.get("text", ""), data.get("text_colour", ""),
                   data.get("text_align", ""),
                   data.get("text_anim", ""),
                   data.get("tilt", ""),
                   data.get("flip", ""))

    def __repr__(self):
        return "<Clip %s %d..%d>" % (self.name, self.start, self.end)


class Track:
    """
    مسار واحد: مقاطع مرتّبة بالبداية، لا تتداخل.

    مسارات الفيديو طبقات: ترتيبها في `Project.tracks` هو ترتيب تركيبها،
    الأوّل فوق والأخير أساس. الإخفاء والكتم والقفل حالة عرضٍ لا تحرير، فتُحفظ
    مع المشروع ولا تغيّر المقاطع.
    """

    def __init__(self, kind="video", name="", visible=True, muted=False,
                 locked=False):
        self.kind = kind            # video | audio
        self.name = name or kind
        self.visible = bool(visible)
        self.muted = bool(muted)
        self.locked = bool(locked)
        self.clips: list[Clip] = []

    @property
    def duration(self):
        return max((c.end for c in self.clips), default=0)

    def add(self, clip):
        self.clips.append(clip)
        self.clips.sort(key=lambda c: c.start)

    def remove(self, clip):
        if clip in self.clips:
            self.clips.remove(clip)

    def free_start(self, clip, desired):
        """
        أقرب بداية لا تتداخل مع بقية المقاطع.

        المسار لا يقبل تداخلًا: لو تداخل مقطعان فأيّهما يظهر عند التصدير سؤال
        بلا جواب صحيح. فبدل رفض الإفلات نزحزحه إلى أقرب موضع يسع.
        """
        # الزحزحة تكرارًا لا استدعاءً ذاتيًّا: مقطعان متلاصقان يتقاذفان
        # الموضع بينهما بلا نهاية - يُزاح قبل الأوّل فيصطدم بالثاني، ويُزاح
        # بعد الثاني فيصطدم بالأوّل - فتنهار المكدّسة بدل أن يُرجَع موضع.
        desired = max(0, int(desired))
        others = sorted((c for c in self.clips if c is not clip),
                        key=lambda c: c.start)
        for _ in range(len(others) + 1):
            for other in others:
                if desired < other.end and                         other.start < desired + clip.duration:
                    # يتداخل: جرّب قبله، وإلا فبعده
                    before = other.start - clip.duration
                    after = other.end
                    desired = before if before >= 0 and (
                        desired - before) <= (after - desired) else after
                    break
            else:
                return desired
        # لم تتّسع أي فجوة: بعد آخر مقطع، وهذا موضعٌ حرٌّ دائمًا
        return max((c.end for c in others), default=0)

    def at(self, frame):
        for clip in self.clips:
            if clip.start <= frame < clip.end:
                return clip
        return None

    def to_dict(self):
        return {"kind": self.kind, "name": self.name,
                "visible": self.visible, "muted": self.muted,
                "locked": self.locked,
                "clips": [c.to_dict() for c in self.clips]}

    @classmethod
    def from_dict(cls, data):
        track = cls(data.get("kind", "video"), data.get("name", ""),
                    data.get("visible", True), data.get("muted", False),
                    data.get("locked", False))
        track.clips = [Clip.from_dict(c) for c in data.get("clips", [])]
        track.clips.sort(key=lambda c: c.start)
        return track


class Project:
    """المستند: معدّل الإطارات والمقاس والمسارات."""

    def __init__(self, fps=Fraction(30, 1), width=1920, height=1080):
        self.fps = Fraction(fps)
        self.width = int(width)
        self.height = int(height)
        self.path = None
        # ملء اللوحة حين لا يطابق المقطعُ نسبتَها: أشرطة سوداء أو خلفية ضبابية
        self.fill = "black"
        self.tracks: list[Track] = [Track("video"), Track("audio")]

    # ---------------------------------------------------------------- الزمن

    def frames(self, seconds):
        return int(round(float(seconds) * float(self.fps)))

    def seconds(self, frames):
        return float(frames) / float(self.fps)

    def timecode(self, frames):
        total = int(frames)
        rate = max(1, int(round(float(self.fps))))
        f = total % rate
        total //= rate
        return "%02d:%02d:%02d.%02d" % (total // 3600, (total // 60) % 60,
                                        total % 60, f)

    @property
    def duration(self):
        return max((t.duration for t in self.tracks), default=0)

    # -------------------------------------------------------------- المسارات

    def find(self, cid):
        """المقطع بمعرّفه. الواجهة تنادي هذي بعد كل تراجع."""
        for track in self.tracks:
            for clip in track.clips:
                if clip.cid == cid:
                    return clip
        return None

    def track(self, kind):
        """
        المسار الأساسي من نوعه.

        آخرُ مسارات الفيديو لا أوّلها: الترتيب من الأعلى إلى الأسفل، والأسفل
        هو الأساس الذي تُركَّب عليه الطبقات. بمسار واحد لا فرق بينهما.
        """
        matches = [t for t in self.tracks if t.kind == kind]
        return matches[-1] if matches else None

    @property
    def layers(self):
        """مسارات الفيديو مرتّبةً من الأعلى إلى الأسفل."""
        return [t for t in self.tracks if t.kind == "video"]

    def index_of(self, track):
        return self.tracks.index(track) if track in self.tracks else -1

    def add_layer(self, name=""):
        """طبقة فيديو جديدة فوق الكلّ."""
        layer = Track("video", name or "طبقة %d" % (len(self.layers) + 1))
        self.tracks.insert(0, layer)
        return layer

    def remove_layer(self, track):
        """يحذف طبقة فيديو. الأساس لا يُحذف: بلا مسارٍ أساس لا مشروع."""
        if track.kind != "video" or len(self.layers) <= 1:
            return False
        if track is self.track("video"):
            return False
        self.tracks.remove(track)
        return True

    # ------------------------------------------------------------ الحفظ

    def to_dict(self):
        return {"schema": SCHEMA, "fill": self.fill,
                "fps": [self.fps.numerator, self.fps.denominator],
                "width": self.width, "height": self.height,
                "tracks": [t.to_dict() for t in self.tracks]}

    def save(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
        self.path = path

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        num, den = data.get("fps", [30, 1])
        project = cls(Fraction(num, den), data.get("width", 1920),
                      data.get("height", 1080))
        project.fill = data.get("fill", "black")
        tracks = [Track.from_dict(t) for t in data.get("tracks", [])]
        if tracks:
            project.tracks = tracks
        project.path = path
        return project


class Editor:
    """
    تحرير المشروع مع تراجع.

    كل تعديل يمرّ من هنا ويُسجَّل كحالة كاملة. المشروع نصٌّ صغير - عشرات
    الكيلوبايتات في أسوأ حال - فنسخُه أرخص من كتابة أمرٍ عكسيّ لكل عملية،
    وأقلّ مصادر للخطأ.
    """

    LIMIT = 60

    def __init__(self, project=None):
        self.project = project or Project()
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._batch = False
        self.dirty = False

    def begin(self):
        """بداية سلسلة متصلة - سحبة فأرة مثلًا - بلقطة تراجع واحدة."""
        self._snapshot()
        self._batch = True

    def end(self):
        self._batch = False

    def _snapshot(self):
        if self._batch:
            return
        self._undo.append(self.project.to_dict())
        del self._undo[:-self.LIMIT]
        self._redo.clear()
        self.dirty = True

    def _restore(self, data):
        num, den = data["fps"]
        self.project.fps = Fraction(num, den)
        self.project.width = data["width"]
        self.project.height = data["height"]
        self.project.fill = data.get("fill", "black")
        self.project.tracks = [Track.from_dict(t) for t in data["tracks"]]

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        self._batch = False
        if not self._undo:
            return False
        self._redo.append(self.project.to_dict())
        self._restore(self._undo.pop())
        self.dirty = True
        return True

    def redo(self):
        self._batch = False
        if not self._redo:
            return False
        self._undo.append(self.project.to_dict())
        self._restore(self._redo.pop())
        self.dirty = True
        return True

    # -------------------------------------------------------------- الأوامر

    def append(self, kind, clip):
        """يضيف مقطعًا في نهاية المسار. kind اسم نوعٍ أو جسم Track بعينه."""
        track = kind if isinstance(kind, Track) else self.project.track(kind)
        if track is None:
            return None
        self._snapshot()
        clip.start = track.duration
        track.add(clip)
        return clip

    def move(self, clip, start):
        self._snapshot()
        for track in self.project.tracks:
            if clip in track.clips:
                clip.start = track.free_start(clip, start)
                track.clips.sort(key=lambda c: c.start)
                break
        return clip

    def trim(self, clip, duration, from_start=False):
        """يقصّ المقطع. القصّ من البداية يزحزح الإزاحة داخل المصدر معها."""
        duration = max(1, int(duration))
        self._snapshot()
        if from_start:
            delta = clip.duration - duration
            clip.offset += delta
            clip.start += delta
        clip.duration = duration
        return clip

    def split(self, clip, frame):
        """يقسم المقطع عند إطار مطلق على الخط الزمني."""
        if not (clip.start < frame < clip.end):
            return None
        self._snapshot()
        # النصفان يرثان تأثيرات الأصل: من يقصّ مقطعًا عدّله لا يتوقّع أن يعود
        # نصفه إلى الخام
        tail = Clip(clip.source, frame, clip.end - frame,
                    clip.offset + (frame - clip.start), clip.name,
                    effects=clip.effects, anim_in=clip.anim_in,
                    anim_out=clip.anim_out, filter=clip.filter,
                    trans=clip.trans, motion=clip.motion,
                    text=clip.text,
                    text_colour=clip.text_colour,
                    text_align=clip.text_align,
                    text_anim=clip.text_anim, tilt=clip.tilt,
                    flip=clip.flip)
        clip.duration = frame - clip.start
        for track in self.project.tracks:
            if clip in track.clips:
                track.add(tail)
                break
        return tail

    def remove(self, clip):
        self._snapshot()
        for track in self.project.tracks:
            track.remove(clip)

    def set_effect(self, clip, name, value):
        """يضبط تأثيرًا على مقطع. سحبة المنزلق كاملة تُلفّ بـ begin/end."""
        self._snapshot()
        return clip.set_effect(name, value)

    def clear_effects(self, clip):
        self._snapshot()
        clip.clear_effects()

    def add_layer(self, name=""):
        self._snapshot()
        return self.project.add_layer(name)

    def remove_layer(self, track):
        self._snapshot()
        if self.project.remove_layer(track):
            return True
        self._undo.pop()            # لم يتغيّر شيء: لا نترك لقطة فارغة
        return False

    def set_canvas(self, width, height, fill=None):
        """يغيّر مقاس اللوحة أو طريقة ملئها. يدخل التراجع كبقيّة التحرير."""
        self._snapshot()
        self.project.width = int(width) // 2 * 2
        self.project.height = int(height) // 2 * 2
        if fill:
            self.project.fill = fill
        return self.project.width, self.project.height

    def set_track_flag(self, track, flag, value):
        """visible أو muted أو locked."""
        if flag not in ("visible", "muted", "locked"):
            return None
        self._snapshot()
        setattr(track, flag, bool(value))
        return value

    def set_animation(self, clip, slot, name):
        """slot: anim_in أو anim_out أو filter."""
        if slot not in TEXT_SLOTS:
            return None
        self._snapshot()
        setattr(clip, slot, name or "")
        return name

    def save(self, path=None):
        target = path or self.project.path
        if not target:
            return False
        self.project.save(target)
        self.dirty = False
        return True


def demo():
    """فحص ذاتي: الزمن والقصّ والتقسيم والتراجع."""
    from fractions import Fraction as F

    editor = Editor(Project(F(30000, 1001)))       # 29.97 إسقاطية
    project = editor.project
    assert project.frames(1) == 30, project.frames(1)
    assert abs(project.seconds(30) - 1.001) < 1e-6

    a = editor.append("video", Clip("a.mp4", 0, 90))
    b = editor.append("video", Clip("b.mp4", 0, 60))
    assert a.start == 0 and b.start == 90, (a, b)
    assert project.duration == 150

    tail = editor.split(a, 30)
    assert tail is not None and a.duration == 30 and tail.duration == 60
    assert tail.offset == 30, tail.offset
    assert editor.split(a, 500) is None

    bid = b.cid
    editor.trim(b, 20, from_start=True)
    assert project.find(bid).duration == 20
    assert project.find(bid).offset == 40

    before = project.duration
    editor.undo()
    assert project.find(bid).duration == 60, "التراجع لم يُرجع القصّ"
    editor.redo()
    assert project.find(bid).duration == 20
    assert project.duration == before

    editor.remove(project.track("video").clips[0])
    assert len(project.track("video").clips) == 2

    # --- التأثيرات ---
    target = project.find(bid)
    assert target.effect("brightness") == 0 and not target.effects
    editor.set_effect(target, "brightness", 300)          # يُقصّ إلى الحدّ
    assert target.effect("brightness") == 100
    editor.set_effect(target, "brightness", 0)            # المحايد لا يُخزَّن
    assert not target.effects, target.effects
    editor.set_effect(target, "speed", 200)
    assert target.speed == 2.0
    assert target.source_frames == target.duration * 2
    editor.undo()
    assert project.find(bid).speed == 1.0, "التراجع لم يُلغِ التأثير"
    editor.redo()
    assert project.find(bid).speed == 2.0

    marked = editor.append("video", Clip("c.mp4", 0, 100))
    editor.set_effect(marked, "saturation", 40)
    half = editor.split(marked, marked.start + 50)
    assert half.effect("saturation") == 40, "التقسيم فقد التأثيرات"

    import tempfile
    path = os.path.join(tempfile.gettempdir(), "wuncut_demo.json")
    project.save(path)
    again = Project.load(path)
    assert again.fps == F(30000, 1001)
    assert again.duration == project.duration
    assert again.find(bid) is not None, "المعرّف لم ينجُ من الحفظ"
    os.remove(path)

    assert project.timecode(95) == "00:00:03.05", project.timecode(95)

    # منع التداخل: مقطع يُفلت فوق آخر ينزاح لأقرب موضع يسع
    e2 = Editor(Project(F(30, 1)))
    x = e2.append("video", Clip("x.mp4", 0, 100))
    y = e2.append("video", Clip("y.mp4", 0, 100))
    assert y.start == 100
    e2.move(y, 10)
    assert y.start in (0, 100) and not x.overlaps(y), (x.start, y.start)
    e2.move(y, 95)
    assert not x.overlaps(y), (x.start, x.end, y.start, y.end)

    # المعاملة: سحبة كاملة = لقطة تراجع واحدة
    depth = len(e2._undo)
    e2.begin()
    for frame in range(200, 260, 5):
        e2.move(y, frame)
    e2.end()
    assert len(e2._undo) == depth + 1, len(e2._undo) - depth
    e2.undo()
    assert e2.project.find(y.cid).start == 100

    # --- الإفلات بين مقطعين متلاصقين ينتهي، ولا يقذف الموضع بلا نهاية ---
    #
    # قبل الإصلاح كان هذا يستهلك المكدّسة كلّها ويُسقط البرنامج بـ
    # RecursionError: المستخدم يُفلت مقطعًا في مكانٍ مزدحم فينهار كل شيء.
    tight = Track("video")
    tight.add(Clip("a.mp4", 0, 60))
    tight.add(Clip("b.mp4", 60, 60))
    dropped = Clip("c.mp4", 0, 60)
    spot = tight.free_start(dropped, 30)
    assert spot >= 0, spot
    for other in tight.clips:
        assert not (spot < other.end and other.start < spot + 60),             "الموضع %d يتداخل مع %d..%d" % (spot, other.start, other.end)
    print("الإفلات المزدحم: موضعٌ حرّ عند %d بلا انهيار ✓" % spot)

    print("core/project: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
