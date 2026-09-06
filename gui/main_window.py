"""
النافذة الرئيسية: مكتبة الوسائط، المعاينة، الخط الزمني.

النافذة لا تعدّل المشروع مباشرة. كل تغيير يمرّ على Editor في core، فيبقى
التراجع في مكان واحد ويمكن قيادة التحرير بلا نافذة.
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog,
                               QFrame,
                               QHBoxLayout, QLabel, QMessageBox,
                               QProgressDialog, QPushButton,
                               QScrollArea, QSplitter, QVBoxLayout,
                               QWidget)

from ..core import export, media, presence
from ..core.project import Clip, Editor, Project
from ..i18n import t
from . import icons, theme
from . import effects as effects_panel
from .effects import EffectsPanel
from .export_dialog import ExportDialog, ExportThread
from .media_bin import MediaBin
from .shell import FramelessWindow
from .stage import Stage
from .sticker_dialog import StickerDialog
from . import lettering, stickers, titles
from .timeline import Timeline
from .widgets import Divider, IconButton, ltr

PROJECT_FILTER = t("مشروع Wun Cut (*.wcut);;كل الملفات (*)")

# نسب اللوحة: الأولى تتبع أوّل مقطع، والباقي مقاسات النشر المعروفة
SHAPES = [
    (None, "يتبع المقطع"),
    ((16, 9), "16:9  عريض"),
    ((9, 16), "9:16  عمودي"),
    ((1, 1), "1:1  مربّع"),
    ((4, 5), "4:5  إنستقرام"),
]

FILLS = [("black", "أشرطة سوداء"), ("blur", "خلفية ضبابية")]

FILTER = t("ملفات الوسائط (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mp3 *.wav "
           "*.aac *.m4a *.png *.jpg *.jpeg);;كل الملفات (*)")


def _button(text, icon=None, kind=None, tip=""):
    button = QPushButton(text)
    if icon:
        button.setIcon(icons.icon(icon, 15,
                                  "#FFFFFF" if kind == "primary"
                                  else theme.TXT))
    if kind:
        button.setProperty("kind", kind)
    button.setToolTip(tip or text)
    button.setFixedHeight(34)
    button.setCursor(Qt.PointingHandCursor)
    return button


class MainWindow(FramelessWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(theme.APP_NAME)
        self.resize(1500, 900)

        self.editor = Editor()
        # حالة ديسكورد: تبدأ إن وُجد معرّف، وتصمت تمامًا إن لم يوجد
        self.presence = presence.Presence()
        self.presence.start()
        self._build()
        self._wire()
        self._shortcuts()
        self.timeline.set_project(self.editor.project)

    # ---------------------------------------------------------------- البناء

    def _build(self):
        root = QVBoxLayout(self.body)
        root.setContentsMargins(10, 4, 10, 10)
        root.setSpacing(9)

        root.addWidget(self._bar())

        self.timeline = Timeline()

        upper = QSplitter(Qt.Horizontal)
        upper.setChildrenCollapsible(False)
        upper.setHandleWidth(9)

        # المكتبة تتشارك مخزن المعاينات مع الخط الزمني: الملف يُقرأ مرّة واحدة
        self.bin = MediaBin(self.timeline.previews)
        self.bin.setMinimumWidth(230)
        upper.addWidget(self.bin)

        stage = QWidget()
        stage.setObjectName("Panel")
        stage_column = QVBoxLayout(stage)
        stage_column.setContentsMargins(10, 10, 10, 10)
        stage_column.setSpacing(9)

        host = self.preview_host = QWidget()
        host.setObjectName("CanvasHost")
        host_column = QVBoxLayout(host)
        host_column.setContentsMargins(1, 1, 1, 1)
        self.stage = Stage()
        self.video = self.stage.video
        host_column.addWidget(self.stage)
        stage_column.addWidget(host, 1)
        stage_column.addWidget(self._transport())
        stage.setMinimumWidth(400)
        upper.addWidget(stage)

        self.effects = EffectsPanel()
        self.effects.setMinimumWidth(effects_panel.MIN_WIDTH)
        self.effects.setMaximumWidth(effects_panel.MAX_WIDTH)
        upper.addWidget(self.effects)

        for index, grow in enumerate((0, 1, 0)):
            upper.setStretchFactor(index, grow)
        upper.setSizes([280, 940, effects_panel.MIN_WIDTH])

        lower = QWidget()
        lower.setObjectName("Panel")
        lower_column = QVBoxLayout(lower)
        lower_column.setContentsMargins(10, 8, 10, 10)
        lower_column.setSpacing(7)
        lower_column.addWidget(self._timeline_bar())
        # الطبقات تتجاوز ارتفاع اللوحة، فالتمرير لا الضغط
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.timeline)
        lower_column.addWidget(scroll, 1)

        split = QSplitter(Qt.Vertical)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(9)
        split.addWidget(upper)
        split.addWidget(lower)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([520, 300])
        root.addWidget(split, 1)

        self.status = QLabel(t("جاهز"))
        self.status.setObjectName("Hint")
        root.addWidget(self.status)

    def _bar(self):
        bar = QWidget()
        bar.setFixedHeight(46)
        row = QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(7)

        # بلا نقاط الحذف في التسميات: في واجهة عربية تقفز إلى الطرف المقابل
        # وتقتطع من عرض الزرّ بلا فائدة
        self.btn_open = IconButton("import", t("افتح مشروعًا  (Ctrl+O)"),
                                   34, 17)
        self.btn_save = IconButton("save", t("احفظ المشروع  (Ctrl+S)"), 34, 17)
        row.addWidget(self.btn_open)
        row.addWidget(self.btn_save)
        row.addWidget(Divider(vertical=True))

        self.btn_import = _button(t("استورد وسائط"), "open", "primary",
                                  t("أضف ملفات إلى المكتبة  (Ctrl+I)"))
        row.addWidget(self.btn_import)

        self.btn_add = _button(t("أضف للخط الزمني"), "import",
                               tip=t("يضع الملف المحدَّد في نهاية الخط"))
        row.addWidget(self.btn_add)

        self.btn_layer = _button(t("أضف كطبقة"), "layers", tip=t(
            "يضع الملف على طبقة جديدة فوق الفيديو، عند رأس التشغيل"))
        row.addWidget(self.btn_layer)

        self.btn_text = _button(t("أضف نصًّا"), "text", tip=t(
            "يضيف نصًّا على طبقة فوق الفيديو  (Ctrl+T)"))
        row.addWidget(self.btn_text)

        self.btn_sticker = _button(t("ملصق"), "brush", tip=t(
            "إيموجي وأشكال على طبقة فوق الفيديو  (Ctrl+K)"))
        row.addWidget(self.btn_sticker)

        row.addWidget(Divider(vertical=True))

        self.btn_split = _button(t("قسّم"), "crop", None,
                                 t("يقسم المقطع عند رأس التشغيل  (S)"))
        self.btn_delete = _button(t("احذف"), "trash", "danger",
                                  t("يحذف المقطع المحدَّد  (Delete)"))
        for widget in (self.btn_split, self.btn_delete):
            widget.setEnabled(False)
            row.addWidget(widget)

        row.addWidget(Divider(vertical=True))
        self.btn_undo = IconButton("undo", t("تراجع  (Ctrl+Z)"), 34, 17)
        self.btn_redo = IconButton("redo", t("إعادة  (Ctrl+Y)"), 34, 17)
        row.addWidget(self.btn_undo)
        row.addWidget(self.btn_redo)

        row.addStretch(1)

        self.btn_export = _button(t("صدّر الفيديو"), "export", "primary",
                                  t("يرسم الخط الزمني إلى ملف  (Ctrl+E)"))
        self.btn_export.setEnabled(False)
        row.addWidget(self.btn_export)
        return bar

    def _transport(self):
        bar = QWidget()
        bar.setFixedHeight(38)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)

        self.btn_play = _button(t("تشغيل"), "batch", "primary", t("مسافة"))
        self.btn_play.setMinimumWidth(104)
        row.addWidget(self.btn_play)

        self.clock = QLabel("00:00:00.00")
        self.clock.setObjectName("Clock")
        self.clock.setLayoutDirection(Qt.LeftToRight)
        row.addWidget(self.clock)

        self.total = QLabel("/ 00:00:00.00")
        self.total.setObjectName("Hint")
        self.total.setLayoutDirection(Qt.LeftToRight)
        row.addWidget(self.total)
        row.addStretch(1)

        self.shape = QComboBox()
        self.shape.setFixedHeight(30)
        self.shape.setCursor(Qt.PointingHandCursor)
        self.shape.setToolTip(t("نسبة اللوحة"))
        for value, label in SHAPES:
            self.shape.addItem(t(label), value)
        row.addWidget(self.shape)

        self.fill = QComboBox()
        self.fill.setFixedHeight(30)
        self.fill.setCursor(Qt.PointingHandCursor)
        self.fill.setToolTip(t("ما يملأ الفراغ حول المقطع"))
        for value, label in FILLS:
            self.fill.addItem(t(label), value)
        row.addWidget(self.fill)

        self.btn_fit = _button(t("ملء العرض"), "fit")
        row.addWidget(self.btn_fit)
        return bar

    def _timeline_bar(self):
        """شريط الخط الزمني: تكبير وتصغير وملء."""
        bar = QWidget()
        bar.setFixedHeight(28)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        glyph = QLabel()
        glyph.setPixmap(icons.pixmap("grid_view", 14, theme.TXT_DIM))
        title = QLabel(t("الخط الزمني"))
        title.setObjectName("PanelTitle")
        row.addWidget(glyph)
        row.addWidget(title)

        self.hint_timeline = QLabel(
            t("اسحب لتحريك المقطع · اسحب حافّته للقصّ · انقره لتعديل تأثيراته"))
        self.hint_timeline.setObjectName("Hint")
        row.addSpacing(10)
        row.addWidget(self.hint_timeline)
        row.addStretch(1)

        self.btn_zoom_out = IconButton("zoom_out", t("تصغير"), 26, 15)
        self.btn_zoom_in = IconButton("zoom_in", t("تكبير"), 26, 15)
        self.btn_zoom_fit = IconButton("fit", t("ملء الخط الزمني"), 26, 15)
        for widget in (self.btn_zoom_out, self.btn_zoom_in, self.btn_zoom_fit):
            row.addWidget(widget)
        return bar

    # ----------------------------------------------------------------- الربط

    def _wire(self):
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self._start_at = None

        self.btn_import.clicked.connect(self.import_media)
        self.btn_add.clicked.connect(
            lambda: self.add_to_timeline(self.bin.current()))
        self.bin.addRequested.connect(self.add_to_timeline)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_fit.clicked.connect(self.timeline.fit)
        self.shape.currentIndexChanged.connect(self._on_canvas)
        self.fill.currentIndexChanged.connect(self._on_canvas)
        self.timeline.seeked.connect(self.seek)
        self.timeline.clipPicked.connect(self._on_pick)
        self.timeline.dragBegan.connect(self.editor.begin)
        self.timeline.dragEnded.connect(self._on_drag_end)
        self.timeline.clipMoved.connect(self._on_moved)
        self.timeline.clipTrimmed.connect(self._on_trimmed)
        self.timeline.menuChosen.connect(self._on_menu)
        self.timeline.trackToggled.connect(self._on_track_flag)
        self.btn_export.clicked.connect(self.export)
        self.btn_split.clicked.connect(self.split_at_playhead)
        self.btn_delete.clicked.connect(self.delete_selected)
        self.btn_open.clicked.connect(self.open_project)
        self.btn_save.clicked.connect(self.save_project)
        self.btn_layer.clicked.connect(self.add_as_layer)
        self.btn_text.clicked.connect(self.add_text)
        self.btn_sticker.clicked.connect(self.add_sticker)
        self.effects.textChanged.connect(self._on_text)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo.clicked.connect(self.redo)
        self.btn_zoom_in.clicked.connect(lambda: self.timeline.zoom(1.4))
        self.btn_zoom_out.clicked.connect(lambda: self.timeline.zoom(1 / 1.4))
        self.btn_zoom_fit.clicked.connect(self.timeline.fit)

        self.effects.changed.connect(self._on_effect)
        self.effects.animated.connect(self._on_animation)
        self.effects.began.connect(self.editor.begin)
        self.effects.ended.connect(self.editor.end)
        self._refresh_history()

    def _shortcuts(self):
        for keys, slot in (("Ctrl+I", self.import_media),
                           ("Space", self.toggle_play),
                           ("Ctrl+E", self.export),
                           ("Ctrl+T", self.add_text),
                           ("Ctrl+K", self.add_sticker),
                           ("Ctrl+S", self.save_project),
                           ("Ctrl+Shift+S", self.save_project_as),
                           ("Ctrl+O", self.open_project),
                           ("S", self.split_at_playhead),
                           ("Delete", self.delete_selected),
                           ("Ctrl+Z", self.undo),
                           ("Ctrl+Y", self.redo)):
            QShortcut(QKeySequence(keys), self, activated=slot)

    # -------------------------------------------------------------- الاستيراد

    def import_media(self):
        paths, _ = QFileDialog.getOpenFileNames(self, t("استورد وسائط"), "",
                                                FILTER)
        added, failed = 0, []
        for path in paths:
            try:
                self.bin.add(media.probe(path))
                added += 1
            except media.MediaError as exc:
                failed.append("%s: %s" % (os.path.basename(path), exc))
        if failed:
            QMessageBox.warning(self, t("تعذّر استيراد بعض الملفات"),
                                "\n".join(failed[:10]))
        if added:
            self._status(t("استُورد %d ملف") % added)

    def open_paths(self, paths):
        """ملفات مُرِّرت في سطر الأوامر أو أُفلتت على الأيقونة."""
        for path in paths:
            try:
                info = media.probe(path)
            except media.MediaError:
                continue
            self.bin.add(info)
            self.add_to_timeline(info)

    def add_to_timeline(self, info):
        if info is None:
            return
        project = self.editor.project
        if not project.track("video").clips and not project.track("audio").clips:
            # أول مقطع يحدّد إعدادات المشروع، فلا يُعاد ترميز كل شيء بلا داعٍ
            if info.has_video and info.fps:
                project.fps = info.fps
                project.width, project.height = info.width, info.height
                self._sync_canvas()

        frames = project.frames(info.duration) or project.frames(5)
        kind = "video" if info.has_video else "audio"
        clip = self.editor.append(kind, Clip(info.path, 0, frames,
                                             name=info.name))
        self.timeline.set_project(project)
        self.timeline.fit()
        self.btn_export.setEnabled(project.duration > 0)
        self.total.setText("/ " + project.timecode(project.duration))
        self._refresh_history()
        self._status(t("أُضيف %s") % ltr(info.name))
        self._refresh_stage()


    # -------------------------------------------------------------- التشغيل

    def toggle_play(self):
        """
        التشغيل يعرض الخط الزمني بتأثيراته، لا الملف الخام.

        يُرمَّز المشروع مرّة بدقّة منخفضة ثم يُشغَّل الناتج. أوّل مرّة تنتظر
        ثواني، وبعدها يُعاد تشغيل ما رُمّز ما لم يتغيّر شيء. البديل - رسم
        التأثيرات في الواجهة - يعني منطقًا ثانيًا ينحرف عن الملف الناتج.
        """
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            return
        project = self.editor.project
        if project.duration <= 0:
            return

        plain = self._plain_clip()
        if plain is not None:
            self._play_raw(plain)
            return

        ready = self.stage.proxy_ready(project)
        if ready:
            self._play_proxy(ready)
            return

        self.btn_play.setEnabled(False)
        self.stage.show_busy(0, project.duration)
        self._status(t("جاري تجهيز المعاينة…"))
        self.stage.build_proxy(project, self._proxy_progress,
                               self._proxy_done)

    def _plain_clip(self):
        """
        المقطع الذي يُشغَّل من ملفه مباشرةً، أو None إن لزم ترميز معاينة.

        خطٌّ فيه مقطع واحد خام يُشغَّل فورًا كما كان: إجبار الترميز عليه يعني
        عشر ثوانٍ انتظار مقابل لا شيء. الترميز للخطّ المركّب وحده.
        """
        project = self.editor.project
        base = project.track("video")
        audio = project.track("audio")
        if base is None or len(base.clips) != 1:
            return None
        # الطبقة المخفيّة لا تُركَّب، فلا تُلزم بترميز
        if any(layer.clips for layer in project.layers
               if layer is not base and layer.visible):
            return None
        if audio is not None and audio.clips:
            return None
        clip = base.clips[0]
        if clip.touched or clip.start != 0:
            return None
        return clip

    def _play_raw(self, clip):
        self._begin_playback(
            clip.source,
            self.editor.project.seconds(clip.offset + self.timeline.playhead))

    def _proxy_progress(self, done, total):
        self.stage.show_busy(done, total)
        self.stage.busy_text.setText(
            t("جاري تجهيز المعاينة…  %d٪") % int(100 * done / max(1, total)))

    def _proxy_done(self, path):
        self.btn_play.setEnabled(True)
        if not path:
            self.stage.show_still()
            self._refresh_stage()
            self._status(t("أُلغي تجهيز المعاينة"))
            return
        self._status(t("جاهز"))
        self._play_proxy(path)

    def _play_proxy(self, path):
        self._begin_playback(
            path, self.editor.project.seconds(self.timeline.playhead))

    def _begin_playback(self, path, at_seconds):
        """
        يشغّل ملفًا من لحظة.

        الملف الجديد لا يُشغَّل فور setSource: الوسيط لم يُحمَّل بعد، فيُهمَل
        setPosition ويقبل المشغّل طلب التشغيل ويعلن PlayingState بينما يبقى
        الموضع على الصفر - يبدو شغّالًا ولا شيء يتحرّك. ننتظر LoadedMedia.
        """
        url = QUrl.fromLocalFile(path)
        self.stage.show_video()
        if self.player.source() != url:
            self._start_at = int(at_seconds * 1000)
            self.player.setSource(url)
            return
        self.player.setPosition(int(at_seconds * 1000))
        self.player.play()

    def _on_media_status(self, status):
        """وصل الوسيط: الآن يصحّ الانتقال إلى اللحظة والتشغيل."""
        if status not in (QMediaPlayer.LoadedMedia,
                          QMediaPlayer.BufferedMedia):
            return
        if getattr(self, "_start_at", None) is None:
            return
        at, self._start_at = self._start_at, None
        self.player.setPosition(at)
        self.player.play()

    def seek(self, frame):
        self.timeline.set_playhead(frame)
        self.clock.setText(self.editor.project.timecode(frame))
        if self.player.source().isValid():
            self.player.setPosition(
                int(self.editor.project.seconds(frame) * 1000))
        self._refresh_stage()

    def _on_position(self, ms):
        frame = self.editor.project.frames(ms / 1000.0)
        self.timeline.set_playhead(frame)
        self.clock.setText(self.editor.project.timecode(frame))

    def _on_state(self, state):
        """
        التشغيل يعرض الفيديو الخام، والتوقّف يعرض الصورة بالتأثيرات.

        رسم كل إطارٍ بمرشّحات التصدير أثناء التشغيل يعني استدعاء ffmpeg ستّين
        مرّة في الثانية. التصميم يحصل عند التوقّف، والتشغيل للإيقاع فحسب.
        """
        playing = state == QMediaPlayer.PlayingState
        self.btn_play.setText(t("إيقاف") if playing else t("تشغيل"))
        if playing:
            self.stage.show_video()
        else:
            self.stage.show_still()
            self._refresh_stage()

    def _on_pick(self, cid):
        clip = self.editor.project.find(cid) if cid else None
        self.btn_delete.setEnabled(clip is not None)
        self.btn_split.setEnabled(clip is not None)
        self.effects.set_clip(clip)
        if clip:
            self._status("%s  ·  %s" % (
                ltr(clip.name), self.editor.project.timecode(clip.duration)))

    def _on_effect(self, name, value):
        """منزلق تحرّك: التغيير يمرّ على المحرّك ليدخل التراجع."""
        clip = self.editor.project.find(self.timeline.selected)
        if clip is None:
            return
        self.editor.set_effect(clip, name, value)
        if clip.is_text and name in ("text_size", "text_outline"):
            self._draw_text(clip)
        self.timeline.update()          # الموجة تتبع الصوت والنجمة تظهر
        self._refresh_history()
        self._refresh_stage()

    def _on_animation(self, slot, name):
        clip = self.editor.project.find(self.timeline.selected)
        if clip is None:
            return
        self.editor.set_animation(clip, slot, name)
        self.timeline.update()
        self._refresh_history()
        self._refresh_stage()

    def _refresh_history(self):
        self.btn_undo.setEnabled(self.editor.can_undo)
        self.btn_redo.setEnabled(self.editor.can_redo)
        self.title_bar.set_dirty(self.editor.dirty)
        self._tell_discord()

    def _tell_discord(self):
        """
        حالةُ ديسكورد. تُستدعى بعد كل تعديل، فتُرسل حين يتغيّر النصّ وحده:
        الطابور يُطبّق آخر طلبٍ فقط، لكن إرسالَ ما لم يتغيّر شغلٌ بلا ثمرة.
        """
        project = self.editor.project
        clips = sum(len(t.clips) for t in project.tracks)
        name = os.path.basename(project.path) if project.path else ""
        title = t("يحرّر %s") % ltr(name) if name else t("مشروع جديد")
        note = (t("%d مقطعًا · %s") % (clips, project.timecode(
            project.duration))) if clips else t("خطٌّ زمنيّ فارغ")
        if (title, note) == getattr(self, "_discord_said", None):
            return
        self._discord_said = (title, note)
        self.presence.show(title, note)

    # ------------------------------------------------------ القوائم والطبقات

    def _on_track_flag(self, track, flag):
        if not flag:
            return
        self.editor.set_track_flag(track, flag, not getattr(track, flag))
        self.timeline.update()
        self._refresh_history()

    def _on_menu(self, data, frame):
        """أمرٌ من قائمة النقر الأيمن. القائمة ترسل، والنافذة تنفّذ."""
        scope, name, target = data
        project = self.editor.project
        if scope == "track":
            self._track_command(name, target)
        else:
            self._clip_command(name, project.find(target), frame)
        self.timeline.set_project(project)
        self.timeline.update()
        self._refresh_history()
        self._refresh_stage()

    def _track_command(self, name, track):
        if name == "add_layer":
            self.editor.add_layer()
            self._status(t("أُضيفت طبقة"))
        elif name == "remove_layer":
            if self.editor.remove_layer(track):
                self._status(t("حُذفت الطبقة"))
            else:
                self._status(t("لا يمكن حذف المسار الأساس"))
        else:
            self.editor.set_track_flag(track, name, not getattr(track, name))

    def _clip_command(self, name, clip, frame):
        if clip is None:
            return
        if name == "split":
            self.timeline.set_playhead(frame)
            self.split_at_playhead()
        elif name == "delete":
            self.delete_selected()
        elif name == "duplicate":
            twin = Clip(clip.source, clip.end, clip.duration, clip.offset,
                        clip.name, effects=clip.effects,
                        anim_in=clip.anim_in, anim_out=clip.anim_out)
            for track in self.editor.project.tracks:
                if clip in track.clips:
                    self.editor.append(track, twin)
                    self.editor.move(twin, clip.end)
                    break
            self.timeline.select(twin.cid)
            self.effects.set_clip(twin)
            self._status(t("كُرِّر %s") % ltr(clip.name))
        elif name == "copy_fx":
            self._clipboard = (dict(clip.effects), clip.anim_in, clip.anim_out)
            self._status(t("نُسخت التأثيرات"))
        elif name == "paste_fx":
            saved = getattr(self, "_clipboard", None)
            if saved is None:
                self._status(t("لا توجد تأثيرات منسوخة"))
                return
            self.editor.begin()
            effects, anim_in, anim_out = saved
            for key, value in effects.items():
                self.editor.set_effect(clip, key, value)
            self.editor.set_animation(clip, "anim_in", anim_in)
            self.editor.set_animation(clip, "anim_out", anim_out)
            self.editor.end()
            self.effects.set_clip(clip)
            self._status(t("لُصقت التأثيرات"))
        elif name == "clear_fx":
            self.editor.clear_effects(clip)
            self.effects.set_clip(clip)
            self._status(t("صُفِّرت التأثيرات"))

    def add_as_layer(self):
        """يضع الملف المحدَّد على طبقة جديدة عند رأس التشغيل."""
        info = self.bin.current()
        if info is None:
            self._status(t("اختر ملفًا من المكتبة أولًا"))
            return
        project = self.editor.project
        layer = self.editor.add_layer()
        frames = project.frames(info.duration) or project.frames(5)
        clip = self.editor.append(layer, Clip(info.path, 0, frames,
                                              name=info.name))
        self.editor.move(clip, self.timeline.playhead)
        self.timeline.set_project(project)
        self.timeline.select(clip.cid)
        self.effects.set_clip(clip)
        self.btn_export.setEnabled(project.duration > 0)
        self._refresh_history()
        self._refresh_stage()
        self._status(t("أُضيف %s على طبقة جديدة") % ltr(info.name))

    # ---------------------------------------------------------- اللوحة

    def _on_canvas(self):
        """
        نسبة اللوحة وطريقة ملئها.

        الضلع القصير يبقى ثابتًا: 1920×1080 تصير 1080×1920 عموديًّا و
        1080×1080 مربّعًا - وهي المقاسات التي تتوقّعها منصّات النشر. تثبيت
        الضلع الطويل بدلها يعطي 1215×2160 وأمثالها: صحيحة النسبة، غريبة.
        """
        project = self.editor.project
        ratio = self.shape.currentData()
        width, height = project.width, project.height
        if ratio:
            short = max(480, min(min(width, height), 1440))
            if ratio[0] >= ratio[1]:
                height, width = short, short * ratio[0] // ratio[1]
            else:
                width, height = short, short * ratio[1] // ratio[0]
        self.editor.set_canvas(width, height, self.fill.currentData())
        self._refresh_history()
        self._refresh_stage()
        self._status(t("اللوحة %d×%d") % (project.width, project.height))

    def _sync_canvas(self):
        """يعكس حالة المشروع في القائمتين بلا أن يُطلق تغييرًا."""
        project = self.editor.project
        for widget in (self.shape, self.fill):
            widget.blockSignals(True)
        self.fill.setCurrentIndex(max(0, self.fill.findData(project.fill)))
        found = 0
        for index, (ratio, _label) in enumerate(SHAPES):
            if ratio and abs(project.width / max(1, project.height)
                             - ratio[0] / ratio[1]) < 0.02:
                found = index
                break
        self.shape.setCurrentIndex(found)
        for widget in (self.shape, self.fill):
            widget.blockSignals(False)

    # ------------------------------------------------------- حفظ المشروع

    def save_project(self):
        """يحفظ في مساره، أو يسأل عن مسار إن لم يُحفظ من قبل."""
        if not self.editor.project.path:
            return self.save_project_as()
        return self._write(self.editor.project.path)

    def save_project_as(self):
        suggested = self.editor.project.path or os.path.join(
            os.path.expanduser("~"), "Videos", "مشروعي.wcut")
        path, _ = QFileDialog.getSaveFileName(self, t("احفظ المشروع"),
                                              suggested, PROJECT_FILTER)
        return self._write(path) if path else False

    def _write(self, path):
        try:
            self.editor.project.save(path)
        except OSError as exc:
            QMessageBox.warning(self, t("تعذّر الحفظ"), str(exc))
            return False
        self.editor.dirty = False
        self._sync_title()
        self._status(t("حُفظ إلى %s") % ltr(path))
        return True

    def open_project(self):
        if not self._offer_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, t("افتح مشروعًا"), "",
                                              PROJECT_FILTER)
        if not path:
            return
        try:
            loaded = Project.load(path)
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.warning(self, t("تعذّر فتح المشروع"), str(exc))
            return

        self.editor = Editor(loaded)
        self._wire_editor()
        self.timeline.set_project(loaded)
        self.timeline.select(None)
        self.timeline.set_playhead(0)
        self.timeline.fit()
        self.effects.set_clip(None)
        self.player.setSource(QUrl())
        self.stage.clear()
        self.btn_export.setEnabled(loaded.duration > 0)
        self.total.setText("/ " + loaded.timecode(loaded.duration))
        self._sync_title()
        self._sync_canvas()
        self._refresh_history()
        self._refresh_stage()
        self._status(t("فُتح %s") % ltr(os.path.basename(path)))

    def _wire_editor(self):
        """يعيد ربط ما يمسك المحرّك بعد استبداله بمشروع مفتوح."""
        self.timeline.dragBegan.disconnect()
        self.timeline.dragEnded.disconnect()
        self.effects.began.disconnect()
        self.effects.ended.disconnect()
        self.timeline.dragBegan.connect(self.editor.begin)
        self.timeline.dragEnded.connect(self._on_drag_end)
        self.effects.began.connect(self.editor.begin)
        self.effects.ended.connect(self.editor.end)

    def _sync_title(self):
        project = self.editor.project
        self.title_bar.set_file(ltr(os.path.basename(project.path))
                                if project.path else None)
        self.title_bar.set_dirty(self.editor.dirty)

    def _offer_save(self):
        """
        يسأل قبل ما يُفقد عملٌ غير محفوظ. يرجع False إن اختار المستخدم الإلغاء.

        بلا هذا السؤال يضيع عملُ ساعةٍ بنقرةِ «افتح» أو «إغلاق»، وهو أسوأ ما
        يفعله محرّر بمستخدمه.
        """
        if not self.editor.dirty:
            return True
        answer = QMessageBox.question(
            self, t("توجد تعديلات غير محفوظة"),
            t("هل تحفظ التعديلات قبل المتابعة؟"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_project()
        return True

    # ---------------------------------------------------------------- النصّ

    def add_text(self):
        """نصّ جديد على طبقة فوق الفيديو، عند رأس التشغيل."""
        project = self.editor.project
        body = t("اكتب نصّك هنا")
        layer = self.editor.add_layer(t("نصّ"))
        clip = Clip("", 0, project.frames(4), name=body[:24], text=body)
        if not self._draw_text(clip):
            self.editor.remove_layer(layer)
            QMessageBox.warning(self, t("تعذّر رسم النصّ"), t("تعذّر رسم النصّ"))
            return
        self.editor.append(layer, clip)
        self.editor.move(clip, self.timeline.playhead)
        self.timeline.set_project(project)
        self.timeline.select(clip.cid)
        self.effects.set_clip(clip)
        self.btn_export.setEnabled(project.duration > 0)
        self._refresh_history()
        self._refresh_stage()
        self._status(t("أُضيف نصّ"))

    def add_sticker(self):
        """يفتح المنتقي، ويضع المختار طبقةً عند رأس التشغيل."""
        dialog = StickerDialog(self)
        if dialog.exec() != StickerDialog.Accepted or not dialog.choice:
            return
        kind, value, colour = dialog.choice
        path = stickers.render(kind, value, colour)
        if not path:
            QMessageBox.warning(self, t("تعذّر رسم الملصق"),
                                t("تعذّر رسم الملصق"))
            return

        project = self.editor.project
        label = stickers.SHAPE_LABELS.get(value, value)
        layer = self.editor.add_layer(t("ملصق"))
        clip = Clip(path, 0, project.frames(3), name=label)
        clip.set_effect("layer_scale", 28)
        self.editor.append(layer, clip)
        self.editor.move(clip, self.timeline.playhead)
        self.timeline.set_project(project)
        self.timeline.select(clip.cid)
        self.effects.set_clip(clip)
        self.btn_export.setEnabled(project.duration > 0)
        self._refresh_history()
        self._refresh_stage()
        self._status(t("أُضيف ملصق %s") % label)

    def _draw_text(self, clip):
        """
        يعيد رسم صورة النصّ ويجعلها مصدر المقطع.

        النصّ ليس نوعًا خاصًّا في التصدير: يُرسم صورةً شفّافة فيصير مقطع صورة
        عاديًّا يرث الموضع والحجم والحركات والفلاتر بلا شفرةٍ جديدة.
        """
        project = self.editor.project
        if clip.text_anim:
            # الحركة حرفًا حرفًا تحتاج زمنًا، والصورة الساكنة لا تحمله:
            # تُرسم مقطعًا شفّافًا بطول القصاصة
            path = lettering.render(clip.text, project.width,
                                    project.seconds(clip.duration),
                                    clip.text_anim,
                                    size=clip.effect("text_size"),
                                    colour=clip.text_colour,
                                    outline=clip.effect("text_outline"),
                                    align=clip.text_align)
        else:
            path = titles.render(clip.text, project.width,
                                 size=clip.effect("text_size"),
                                 colour=clip.text_colour,
                                 outline=clip.effect("text_outline"),
                                 align=clip.text_align)
        if not path:
            return False
        clip.source = path
        clip.name = (clip.text.strip().splitlines() or [""])[0][:24]
        return True

    def _on_text(self, body, colour, align, anim=""):
        """عُدّل النصّ في اللوحة: نعيد رسمه ونحدّث المعاينة."""
        clip = self.editor.project.find(self.timeline.selected)
        if clip is None or not clip.is_text:
            return
        self.editor.begin()
        clip.text = body
        clip.text_colour = colour
        clip.text_align = align
        clip.text_anim = anim
        self.editor.end()
        self._draw_text(clip)
        self.timeline.update()
        self._refresh_history()
        self._refresh_stage()

    def _refresh_stage(self):
        """يعيد رسم المعاينة عند رأس التشغيل. مؤجَّل ومدموج داخل Stage."""
        self.stage.refresh(self.editor.project, self.timeline.playhead)

    # -------------------------------------------------------------- التحرير

    def _on_moved(self, cid, start):
        clip = self.editor.project.find(cid)
        if clip:
            self.editor.move(clip, start)
            self.timeline.update()

    def _on_trimmed(self, cid, duration, from_start):
        clip = self.editor.project.find(cid)
        if clip and duration >= 1:
            self.editor.trim(clip, duration, from_start)
            self.timeline.update()

    def _on_drag_end(self):
        self.editor.end()
        self._refresh_history()
        self._refresh_stage()
        clip = self.editor.project.find(self.timeline.selected)
        if clip:
            self._status("%s  ·  %s" % (
                ltr(clip.name), self.editor.project.timecode(clip.duration)))

    def split_at_playhead(self):
        clip = self.editor.project.find(self.timeline.selected)
        if clip is None:
            return
        tail = self.editor.split(clip, self.timeline.playhead)
        if tail is None:
            self._status(t("رأس التشغيل خارج المقطع المحدَّد"))
            return
        self.timeline.select(tail.cid)
        self.timeline.update()
        self.effects.set_clip(tail)
        self._refresh_history()
        self._status(t("قُسِّم %s") % ltr(clip.name))
        self._refresh_stage()

    def delete_selected(self):
        clip = self.editor.project.find(self.timeline.selected)
        if clip is None:
            return
        self.editor.remove(clip)
        self.timeline.select(None)
        self.btn_delete.setEnabled(False)
        self.btn_split.setEnabled(False)
        self.timeline.update()
        self.effects.set_clip(None)
        self.total.setText("/ " + self.editor.project.timecode(
            self.editor.project.duration))
        self._refresh_history()
        self._status(t("حُذف %s") % ltr(clip.name))
        self._refresh_stage()

    # -------------------------------------------------------------- التصدير

    def export(self):
        project = self.editor.project
        if project.duration <= 0:
            return
        dialog = ExportDialog(project, self)
        if dialog.exec() != ExportDialog.Accepted:
            return

        options = dialog.settings()
        output = options.pop("output")
        if not output:
            return
        folder = os.path.dirname(os.path.abspath(output))
        if not os.path.isdir(folder):
            QMessageBox.warning(self, t("مجلد غير موجود"), folder)
            return

        try:
            job = export.ExportJob(project, output, **options)
        except export.ExportError as exc:
            QMessageBox.warning(self, t("تعذّر التصدير"), t(str(exc)))
            return

        progress = QProgressDialog(t("جاري التصدير…"), t("إلغاء"), 0,
                                   job.total, self)
        progress.setWindowTitle(t("تصدير الفيديو"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)

        thread = ExportThread(job, self)
        # يبقى مرجع على النافذة: خيط بلا مالك قد يُجمع وهو يعمل
        self._export_thread = thread

        def on_progress(done, total):
            progress.setMaximum(max(1, total))
            progress.setValue(done)
            progress.setLabelText(t("%s من %s")
                                  % (project.timecode(done),
                                     project.timecode(total)))

        def on_done(path):
            progress.close()
            self._status(t("صُدِّر إلى %s") % ltr(path))
            QMessageBox.information(
                self, t("تمّ التصدير"),
                t("%s\n\nالحجم: %.1f م.ب")
                % (path, os.path.getsize(path) / 1e6))

        def on_failed(message):
            progress.close()
            QMessageBox.warning(self, t("فشل التصدير"), message)

        thread.progress.connect(on_progress)
        thread.done.connect(on_done)
        thread.failed.connect(on_failed)
        progress.canceled.connect(thread.cancel)
        thread.finished.connect(progress.close)
        thread.start()

    # -------------------------------------------------------------- التراجع

    def _resync(self):
        project = self.editor.project
        self.timeline.set_project(project)
        self.btn_export.setEnabled(project.duration > 0)
        self.total.setText("/ " + project.timecode(project.duration))
        self._refresh_history()
        # التراجع يبني المقاطع من جديد: اللوحة تمسك جسمًا ميتًا حتى تُطعَم غيره
        clip = project.find(self.timeline.selected)
        if clip is None:
            self.timeline.select(None)
            self.btn_delete.setEnabled(False)
            self.btn_split.setEnabled(False)
        self.effects.set_clip(clip)
        self._refresh_stage()

    def undo(self):
        if self.editor.undo():
            self._resync()
            self._status(t("تراجع"))

    def redo(self):
        if self.editor.redo():
            self._resync()
            self._status(t("إعادة"))

    # ---------------------------------------------------------------- الحالة

    def _status(self, text):
        self.status.setText(text)

    def closeEvent(self, event):
        """يسأل عن الحفظ، ثم ينتظر خيوط المعاينة قبل الهدم."""
        if not getattr(self, "_quitting", False) and not self._offer_save():
            event.ignore()
            return
        self.stage.shutdown()
        self.presence.close()
        super().closeEvent(event)

    def show_about(self):
        QMessageBox.information(
            self, t("عن البرنامج"),
            "%s %s\n%s" % (theme.APP_NAME, theme.VERSION, theme.COPYRIGHT))

    def toggle_language(self):
        """
        يبدّل اللغة ثم يعيد تشغيل البرنامج.

        لا تبديل حيّ: كثير من النصوص تُترجم وقت الاستيراد - جداول الثوابت
        وعناوين الأعمدة - فتبقى بلغتها القديمة. وإعادة التشغيل تقلب اتجاه
        التخطيط كاملًا وهو ما لا يفعله setLayoutDirection على نافذة قائمة.
        """
        from .. import i18n
        target = i18n.other_language()
        if QMessageBox.question(
                self, t("تغيير اللغة"),
                t("سيُعاد تشغيل البرنامج لتطبيق %s.\nأي عمل غير محفوظ سيضيع.")
                % i18n.LANGUAGES[target],
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes) != QMessageBox.Yes:
            return
        i18n.set_language(target)
        self._quitting = True      # التبديل سأل عن الحفظ أصلًا
        self.restart()

    def restart(self):
        """
        يشغّل نسخة جديدة ثم يغلق هذه.

        sys.executable هو ملف exe نفسه عند التغليف، والمفسّر عند التشغيل من
        المصدر: الحالتان تحتاجان أمرين مختلفين.
        """
        import subprocess
        import sys

        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            command = [sys.executable, os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "main.py"))]
        try:
            subprocess.Popen(command, cwd=os.path.dirname(command[-1])
                             if len(command) > 1 else None)
        except OSError as exc:
            QMessageBox.warning(self, t("تعذّرت إعادة التشغيل"), str(exc))
            return
        QApplication.instance().quit()

    # ---------------------------------------------------------------- الجولة

    def show_tour(self, force=True):
        """جولة التعريف. تُعرض تلقائيًا مرّة واحدة، ويدويًا متى طُلبت."""
        from .. import i18n
        from .tour import SEEN, Tour, steps_for

        if not force and i18n.get(SEEN):
            return False
        # ودجت الفيديو سطحُ عرضٍ أصليّ يرسمه النظام فوق ودجات Qt الشقيقة مهما
        # كان ترتيبها، فيبتلع ما يقع عليه من طبقة الجولة. التبديل إلى صورة
        # المعاينة يُخرجه من المكدّس فلا يرسم شيئًا.
        self.player.pause()
        self.stage.show_still()
        self._tour = Tour(self, steps_for(self), self.body)
        return self._tour.start()

    def showEvent(self, event):
        super().showEvent(event)
        # أول تشغيل فقط، وبعد أن تستقرّ الأبعاد وإلا رُسمت الفتحات في غير مكانها
        if not getattr(self, "_tour_checked", False):
            self._tour_checked = True
            QTimer.singleShot(350, lambda: self.show_tour(force=False))
