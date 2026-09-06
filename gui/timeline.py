"""
الخط الزمني: مسطرة، مسارات، مقاطع، ورأس تشغيل.

مرسوم يدويًا لا مبنيًّا من عناصر Qt: عدد المقاطع قد يبلغ المئات، وإنشاء
ودجت لكل واحد يخنق التخطيط. الرسم المباشر يجعل التمرير والتكبير رخيصين.

الودجت لا يعدّل المشروع بنفسه. ينشر إشارات، والنافذة تترجمها إلى أوامر على
Editor. هذي هي القاعدة: المحرّك يملك التعديل، الواجهة ترسم وترسل.
"""

from __future__ import annotations

from PySide6.QtCore import QLineF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMenu, QSizePolicy, QWidget

from ..i18n import t
from . import icons, theme
from .previews import PreviewStore
from .widgets import ltr

RULER_H = 26
TRACK_H = 72                # يتّسع لشريط الإطارات فوق موجة الصوت
TRACK_GAP = 6
HEAD_W = 96                 # عمود أسماء المسارات
MIN_PPF = 0.02              # بكسل لكل إطار: أدنى تكبير
MAX_PPF = 12.0
EDGE = 7                    # عرض منطقة القصّ عند حافة المقطع، بالبكسل
SNAP = 9                    # مدى الالتقاط المغناطيسي، بالبكسل
WAVE_H = 20                 # ارتفاع شريط الموجة أسفل مقطع الفيديو


class Timeline(QWidget):

    seeked = Signal(int)            # إطار
    clipPicked = Signal(object)     # معرّف المقطع أو None
    dragBegan = Signal()            # بداية سحبة: لقطة تراجع واحدة
    dragEnded = Signal()
    clipMoved = Signal(object, int)          # معرّف، بداية جديدة
    clipTrimmed = Signal(object, int, bool)  # معرّف، مدّة، من البداية؟
    menuChosen = Signal(object, int)         # (نطاق، أمر، هدف)، الإطار
    trackToggled = Signal(object, str)       # المسار، العلم المنقور

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Timeline")
        self.setMinimumHeight(RULER_H + 2 * (TRACK_H + TRACK_GAP) + 12)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(),
                           QSizePolicy.MinimumExpanding)
        self.setMouseTracking(True)

        self.project = None
        self.playhead = 0
        self.selected = None        # معرّف المقطع
        self.ppf = 0.5              # بكسل لكل إطار
        self.offset = 0             # أول إطار ظاهر
        self._mode = None           # seek | move | trim_start | trim_end
        self._grab = None           # المقطع المسحوب
        self._anchor = 0            # فرق الإطارات بين نقرة الفأرة وبداية المقطع

        # يتبع تغيّر العرض حتى يتدخّل المستخدم بتكبير أو تمرير
        self._fitted = True

        # المعاينات تصل بعد ثوانٍ من خيط آخر: كل وصول يعيد الرسم وحده
        self.previews = PreviewStore(self)
        self.previews.ready.connect(lambda _source: self.update())

    # ---------------------------------------------------------------- الربط

    def set_project(self, project):
        self.project = project
        self._grow()
        self.update()

    def _grow(self):
        """ارتفاع الودجت يتبع عدد المسارات، وإلا اختفت الطبقات الجديدة."""
        rows = len(self.project.tracks) if self.project else 2
        self.setMinimumHeight(RULER_H + max(2, rows) * (TRACK_H + TRACK_GAP)
                              + 12)

    def set_playhead(self, frame):
        frame = max(0, int(frame))
        if frame != self.playhead:
            self.playhead = frame
            self._reveal(frame)
            self.update()

    def select(self, cid):
        self.selected = cid
        self.update()

    def zoom(self, factor):
        self.ppf = max(MIN_PPF, min(MAX_PPF, self.ppf * factor))
        self._fitted = False
        self.update()

    def fit(self):
        """يضبط التكبير ليملأ الخط الزمني عرض الودجت."""
        total = self.project.duration if self.project else 0
        width = max(1, self.width() - HEAD_W - 16)
        self.ppf = max(MIN_PPF, min(MAX_PPF, width / total)) if total else 0.5
        self.offset = 0
        self._fitted = True
        self.update()

    def resizeEvent(self, event):
        """
        يعيد الملء مع تغيّر العرض ما دام المستخدم لم يكبّر بنفسه.

        `fit` يُستدعى ساعة إضافة الملف، وقد يكون التخطيط لم يستقرّ بعد فيكون
        عرض الودجت مئتَي بكسل: الحساب يصطدم بحدّ التكبير الأدنى فيُرسم مقطعٌ
        مدّته دقيقتان في ١٧٠ بكسل ولا يتصحّح أبدًا.
        """
        super().resizeEvent(event)
        if self._fitted:
            self.fit()

    # -------------------------------------------------------- تحويل الإحداثي

    def x_of(self, frame):
        return HEAD_W + (frame - self.offset) * self.ppf

    def frame_at(self, x):
        return max(0, int(round((x - HEAD_W) / self.ppf + self.offset)))

    def _reveal(self, frame):
        """يمرّر الخط الزمني ليبقى الإطار ظاهرًا."""
        span = max(1, int((self.width() - HEAD_W) / max(self.ppf, 1e-6)))
        if frame < self.offset:
            self.offset = max(0, frame - span // 8)
        elif frame > self.offset + span:
            self.offset = max(0, frame - span * 7 // 8)

    # ---------------------------------------------------------------- الرسم

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("BG_CANVAS"))

        self._paint_ruler(p)
        if self.project:
            for index, track in enumerate(self.project.tracks):
                self._paint_track(p, index, track)
        self._paint_playhead(p)
        p.end()

    def _paint_ruler(self, p):
        p.fillRect(0, 0, self.width(), RULER_H, theme.color("BG_PANEL"))
        p.setPen(QPen(theme.color("BORDER"), 1))
        p.drawLine(0, RULER_H, self.width(), RULER_H)
        if not self.project:
            return

        rate = max(1.0, float(self.project.fps))
        # نختار خطوة تعطي علامة كل 70 بكسل تقريبًا، من سلّم ثوانٍ مألوف
        target = 70 / max(self.ppf, 1e-6) / rate
        for step in (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600):
            if step >= target:
                break
        frames = int(step * rate)

        p.setFont(theme.font(8))
        first = (self.offset // frames) * frames
        frame = first
        while self.x_of(frame) < self.width():
            x = self.x_of(frame)
            if x >= HEAD_W:
                p.setPen(QPen(theme.color("BORDER_HI"), 1))
                p.drawLine(int(x), RULER_H - 7, int(x), RULER_H)
                p.setPen(theme.color("TXT_MUTE"))
                p.drawText(int(x) + 4, RULER_H - 9,
                           self.project.timecode(frame)[:-3])
            frame += frames

    @staticmethod
    def _track_label(track):
        if track.kind == "audio":
            return t("صوت")
        return track.name if track.name != "video" else t("فيديو")

    @staticmethod
    def _flag_boxes(row):
        """مربّعات الأعلام الثلاثة أسفل اسم المسار."""
        top = row.top() + TRACK_H - 24
        return {name: QRectF(8 + index * 22, top, 16, 16)
                for index, name in enumerate(("visible", "muted", "locked"))}

    def _flag_at(self, point):
        """اسم العلم تحت النقطة، أو "" إن نُقر الاسم لا الأعلام."""
        track = self._track_at(point)
        if track is None:
            return ""
        row = self._track_rect(self.project.tracks.index(track))
        for name, box in self._flag_boxes(row).items():
            if box.adjusted(-3, -3, 3, 3).contains(point):
                return name
        return ""

    def _track_rect(self, index):
        top = RULER_H + TRACK_GAP + index * (TRACK_H + TRACK_GAP)
        return QRectF(HEAD_W, top, max(0, self.width() - HEAD_W), TRACK_H)

    def _paint_track(self, p, index, track):
        row = self._track_rect(index)
        video = track.kind == "video"

        head = QRectF(0, row.top(), HEAD_W, TRACK_H)
        p.fillRect(head, theme.color("BG_PANEL"))
        p.setPen(QPen(theme.color("BORDER"), 1))
        p.drawLine(QLineF(HEAD_W, row.top(), HEAD_W, row.bottom()))

        glyph = icons.pixmap("image" if video else "layers", 13,
                             theme.TXT_MUTE)
        p.drawPixmap(int(HEAD_W - 22), int(row.top() + 8), glyph)
        p.setPen(theme.color("TXT" if track.visible else "TXT_MUTE"))
        p.setFont(theme.font(9, medium=True))
        p.drawText(QRectF(4, row.top() + 4, HEAD_W - 30, 20),
                   Qt.AlignVCenter | Qt.AlignRight,
                   p.fontMetrics().elidedText(self._track_label(track),
                                              Qt.ElideRight, HEAD_W - 34))

        # أعلام الحالة: تُنقر فتُبدَّل، ولونها يقول أهي مفعَّلة
        for name, box in self._flag_boxes(row).items():
            on = {"visible": not track.visible, "muted": track.muted,
                  "locked": track.locked}[name]
            key = {"visible": "compare", "muted": "eraser",
                   "locked": "select"}[name]
            p.drawPixmap(int(box.left()), int(box.top()),
                         icons.pixmap(key, 13,
                                      theme.WARN if on else theme.TXT_MUTE))

        p.fillRect(row, theme.color("BG_APP"))
        p.setPen(QPen(theme.color("BORDER"), 1))
        p.drawRect(row)

        for clip in track.clips:
            self._paint_clip(p, row, clip, track.kind)

    def _paint_clip(self, p, row, clip, kind):
        x0 = self.x_of(clip.start)
        x1 = self.x_of(clip.end)
        if x1 < HEAD_W or x0 > self.width() or x1 <= x0:
            return
        box = QRectF(max(x0, HEAD_W), row.top() + 3,
                     min(x1, self.width()) - max(x0, HEAD_W), TRACK_H - 6)
        if box.width() < 1:
            return

        # نسبة الجزء الظاهر من المقطع: المقطع قد يخرج نصفه عن الشاشة، فنقتطع
        # من الشريط ما يقابل الظاهر وحده لا المقطع كلّه
        span = max(1.0, x1 - x0)
        head = (box.left() - x0) / span
        tail = (box.right() - x0) / span

        chosen = clip.cid == self.selected
        video = kind == "video"
        path = QPainterPath()
        path.addRoundedRect(box, 6, 6)

        p.save()
        p.setClipPath(path)
        p.fillPath(path, theme.color("ACCENT_DEEP" if video else "BG_ELEV"))

        wave_box = QRectF(box)
        if video and self._paint_strip(p, box, clip, head, tail):
            wave_box = QRectF(box.left(), box.bottom() - WAVE_H,
                              box.width(), WAVE_H)
            p.fillRect(wave_box, QColor(5, 8, 14, 150))
        self._paint_wave(p, wave_box, clip, head, tail, video)
        p.restore()

        p.setPen(QPen(theme.color("ACCENT_HI" if chosen else "BORDER_HI"),
                      2 if chosen else 1))
        p.drawPath(path)

        if box.width() > 46:
            self._paint_label(p, box, clip)

    def _source_rect(self, pixmap, clip, head, tail):
        """
        الجزء من شريط الملف الذي يقابل الظاهر من المقطع.

        الشريط يغطّي الملف كلّه، والمقطع قصاصة منه تبدأ عند إزاحته. تجاهُل هذا
        يعرض بداية الملف على كل قصاصة مهما قُصّت.
        """
        length = self.previews.span(clip.source)
        if not length or pixmap.isNull():
            return None
        project = self.project
        begin = project.seconds(clip.offset)
        used = project.seconds(clip.duration) * clip.speed
        left = (begin + used * head) / length
        right = (begin + used * tail) / length
        left, right = max(0.0, left), min(1.0, right)
        if right - left <= 0:
            return None
        return QRectF(left * pixmap.width(), 0,
                      (right - left) * pixmap.width(), pixmap.height())

    def _paint_strip(self, p, box, clip, head, tail):
        """شريط الإطارات. يرجع False إن لم يصل بعد."""
        pixmap = self.previews.strip(clip.source)
        if pixmap is None or pixmap.isNull():
            return False
        source = self._source_rect(pixmap, clip, head, tail)
        if source is None:
            return False
        p.setOpacity(0.92)
        p.drawPixmap(box, pixmap, source)
        p.setOpacity(1.0)
        return True

    def _paint_wave(self, p, box, clip, head, tail, video):
        peaks = self.previews.wave(clip.source)
        length = self.previews.span(clip.source)
        if not peaks or not length or box.width() < 2:
            return

        begin = self.project.seconds(clip.offset)
        used = self.project.seconds(clip.duration) * clip.speed
        volume = clip.effect("volume") / 100.0
        middle = box.center().y()
        reach = (box.height() / 2 - 2) * min(1.5, volume)

        lines = []
        for step in range(int(box.width())):
            ratio = head + (tail - head) * step / max(1.0, box.width())
            index = int((begin + used * ratio) / length * len(peaks))
            if not 0 <= index < len(peaks):
                continue
            high = peaks[index] * reach
            x = box.left() + step
            lines.append(QLineF(x, middle - high, x, middle + high))

        p.setPen(QPen(theme.color("ACCENT_HI" if video else "ACCENT"), 1))
        p.setOpacity(0.75 if video else 0.9)
        p.drawLines(lines)
        p.setOpacity(1.0)

    def _paint_label(self, p, box, clip):
        """الاسم على لوحة معتمة: النص العاري فوق الإطارات لا يُقرأ."""
        p.setFont(theme.font(8, medium=True))
        text = p.fontMetrics().elidedText(ltr(clip.name), Qt.ElideMiddle,
                                          int(box.width()) - 24)
        width = p.fontMetrics().horizontalAdvance(text)
        mark = 13 if clip.touched else 0
        plate = QRectF(box.left() + 4, box.top() + 4, width + 12 + mark, 17)
        plate_path = QPainterPath()
        plate_path.addRoundedRect(plate, 5, 5)
        p.fillPath(plate_path, QColor(5, 8, 14, 185))

        if mark:
            # نقطة لا رمزًا نصيًّا: الخط قد لا يحمل الرمز فيُرسم فراغًا، والدائرة
            # المرسومة تظهر دائمًا مهما كان الخط
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("WARN"))
            p.drawEllipse(QRectF(plate.left() + 5, plate.center().y() - 3, 6, 6))
            p.setBrush(Qt.NoBrush)

        p.setPen(theme.color("TXT"))
        p.drawText(plate.adjusted(6 + mark, 0, -6, 0),
                   Qt.AlignVCenter | Qt.AlignLeft, text)

    def _paint_playhead(self, p):
        x = self.x_of(self.playhead)
        if x < HEAD_W or x > self.width():
            return
        p.setPen(QPen(theme.color("ACCENT_HI"), 2))
        p.drawLine(int(x), 0, int(x), self.height())
        head = QPainterPath()
        head.moveTo(x - 6, 0)
        head.lineTo(x + 6, 0)
        head.lineTo(x, 9)
        head.closeSubpath()
        p.fillPath(head, theme.color("ACCENT_HI"))

    # ---------------------------------------------------------------- الفأرة

    def _clip_at(self, point):
        if not self.project:
            return None
        for index, track in enumerate(self.project.tracks):
            row = self._track_rect(index)
            if row.top() <= point.y() <= row.bottom():
                frame = self.frame_at(point.x())
                return track.at(frame)
        return None

    def _hit(self, point):
        """يرجع (المقطع، الوضع). الحواف تقصّ، والوسط يسحب."""
        clip = self._clip_at(point)
        if clip is None:
            return None, "seek"
        if abs(point.x() - self.x_of(clip.start)) <= EDGE:
            return clip, "trim_start"
        if abs(point.x() - self.x_of(clip.end)) <= EDGE:
            return clip, "trim_end"
        return clip, "move"

    def _snap(self, frame, moving=None):
        """يلتقط رأس التشغيل وحواف المقاطع الأخرى إن قربت."""
        window = SNAP / max(self.ppf, 1e-6)
        best, distance = frame, window
        candidates = [0, self.playhead]
        if self.project:
            for track in self.project.tracks:
                for clip in track.clips:
                    if clip is moving:
                        continue
                    candidates += [clip.start, clip.end]
        for candidate in candidates:
            gap = abs(candidate - frame)
            if gap < distance:
                best, distance = candidate, gap
        return int(best)

    def _track_at(self, point):
        """المسار تحت النقطة، أو None فوق المسطرة وتحت آخر مسار."""
        if not self.project:
            return None
        for index, track in enumerate(self.project.tracks):
            row = self._track_rect(index)
            if row.top() - TRACK_GAP <= point.y() <= row.bottom():
                return track
        return None

    def contextMenuEvent(self, event):
        """
        قائمة النقر الأيمن.

        على المقطع: أوامره. وعلى عمود الأسماء: أوامر المسار. النافذة تنفّذها،
        فيبقى التعديل كلّه عند المحرّك مثل بقيّة الواجهة.
        """
        point = event.pos()
        track = self._track_at(point)
        clip = self._clip_at(point) if point.x() >= HEAD_W else None
        if track is None:
            return

        menu = QMenu(self)
        if clip is not None:
            self.select(clip.cid)
            self.clipPicked.emit(clip.cid)
            for label, name in ((t("قسّم هنا"), "split"),
                                (t("كرّر المقطع"), "duplicate"),
                                (t("احذف المقطع"), "delete"),
                                (None, None),
                                (t("انسخ التأثيرات"), "copy_fx"),
                                (t("ألصق التأثيرات"), "paste_fx"),
                                (t("صفّر التأثيرات"), "clear_fx")):
                if label is None:
                    menu.addSeparator()
                    continue
                menu.addAction(label).setData(("clip", name, clip.cid))
        else:
            for label, name in ((t("طبقة جديدة فوق"), "add_layer"),
                                (t("احذف هذي الطبقة"), "remove_layer"),
                                (None, None),
                                (t("إخفاء الطبقة") if track.visible
                                 else t("إظهار الطبقة"), "visible"),
                                (t("كتم الصوت") if not track.muted
                                 else t("إلغاء الكتم"), "muted"),
                                (t("قفل الطبقة") if not track.locked
                                 else t("فكّ القفل"), "locked")):
                if label is None:
                    menu.addSeparator()
                    continue
                menu.addAction(label).setData(("track", name, track))

        chosen = menu.exec(event.globalPos())
        if chosen is not None:
            self.menuChosen.emit(chosen.data(), self.frame_at(point.x()))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        point = event.position()
        if point.x() < HEAD_W:
            # النقر على عمود الأسماء يبدّل حالة المسار بأيقونتها
            track = self._track_at(point)
            if track is not None:
                self.trackToggled.emit(track, self._flag_at(point))
            return
        clip, mode = self._hit(point)
        self.selected = clip.cid if clip else None
        self.clipPicked.emit(self.selected)
        self._mode = mode
        self._grab = clip
        if mode == "seek":
            self.seeked.emit(self.frame_at(point.x()))
        else:
            self._anchor = self.frame_at(point.x()) - clip.start
            self.dragBegan.emit()
        self.update()

    def mouseMoveEvent(self, event):
        point = event.position()
        if self._mode is None:
            _clip, mode = self._hit(point)
            self.setCursor(Qt.SizeHorCursor if mode.startswith("trim")
                           else Qt.ArrowCursor)
            return

        frame = self.frame_at(point.x())
        if self._mode == "seek":
            self.seeked.emit(frame)
        elif self._mode == "move":
            self.clipMoved.emit(self._grab.cid,
                                self._snap(frame - self._anchor, self._grab))
        elif self._mode == "trim_end":
            edge = self._snap(frame, self._grab)
            self.clipTrimmed.emit(self._grab.cid,
                                  edge - self._grab.start, False)
        elif self._mode == "trim_start":
            edge = self._snap(frame, self._grab)
            self.clipTrimmed.emit(self._grab.cid,
                                  self._grab.end - edge, True)

    def mouseReleaseEvent(self, _event):
        if self._mode and self._mode != "seek":
            self.dragEnded.emit()
        self._mode = None
        self._grab = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.ControlModifier:
            # التكبير حول المؤشر: الإطار تحته يبقى تحته بعد التكبير
            anchor = self.frame_at(event.position().x())
            self.zoom(1.2 if delta > 0 else 1 / 1.2)
            self.offset = max(0, anchor - int(
                (event.position().x() - HEAD_W) / max(self.ppf, 1e-6)))
        else:
            span = (self.width() - HEAD_W) / max(self.ppf, 1e-6)
            self.offset = max(0, int(self.offset - (delta / 120) * span * 0.15))
            self._fitted = False
        self.update()
