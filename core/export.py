"""
التصدير: من الخط الزمني إلى ملف، عبر FFmpeg.

بناء الأمر دالة نقية (`build`) منفصلة عن تشغيله (`ExportJob`)، فيُفحص الأمر
بلا ترميز ولا انتظار. هذا ما يجعل اختبار التصدير ممكنًا أصلًا.

الفجوات على الخط الزمني تُملأ سوادًا وصمتًا لا تُطوى. طيّها يزيح كل ما بعدها
عن موضعه الذي وضعه المستخدم، وهو آخر ما يتوقّعه.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading

from . import animate, filters, media, tools, transitions

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
AUDIO_RATE = 48000

# مرتّبة بالأفضلية: كرت الشاشة أولًا، والمعالج ملاذًا أخيرًا
ENCODERS = [
    ("h264_nvenc", "NVIDIA"),
    ("h264_amf", "AMD"),
    ("h264_qsv", "Intel"),
    ("libx264", "CPU"),
]

_cache = None


class ExportError(Exception):
    pass


def encoders():
    """المرمّزات المتوفّرة فعلًا في هذه النسخة من FFmpeg."""
    global _cache
    if _cache is not None:
        return _cache
    _cache = []
    if tools.ready():
        result = subprocess.run([tools.ffmpeg(), "-hide_banner", "-encoders"],
                                capture_output=True, creationflags=NO_WINDOW)
        text = result.stdout.decode("utf-8", "replace")
        _cache = [(name, label) for name, label in ENCODERS
                  if re.search(r"\b%s\b" % re.escape(name), text)]
    return _cache


def _quality(encoder, level):
    """
    مستوى الجودة 0..100 إلى معامل المرمّز.

    libx264 يستعمل crf و nvenc يستعمل cq، ومداهما 0..51 بالمقلوب: الأصغر
    أجود. نعرض للمستخدم رقمًا يزيد بزيادة الجودة لأنه ما يتوقّعه.
    """
    value = int(round(51 - (max(0, min(100, level)) / 100.0) * 33))
    if encoder == "libx264":
        return ["-crf", str(value), "-preset", "medium"]
    if encoder == "h264_nvenc":
        return ["-rc", "vbr", "-cq", str(value), "-preset", "p5"]
    if encoder == "h264_amf":
        return ["-rc", "cqp", "-qp_i", str(value), "-qp_p", str(value)]
    if encoder == "h264_qsv":
        return ["-global_quality", str(value)]
    return ["-q:v", str(value)]


def _eq(clip):
    """
    مرشّح eq من قيم -100..100 المعروضة للمستخدم.

    مدى eq الحقيقي مختلف لكل معامل: السطوع ±1 والتباين والتشبّع حول 1. نعرض
    للمستخدم مقياسًا واحدًا مفهومًا ونترجمه هنا.
    """
    bright = clip.effect("brightness") / 200.0          # ±0.5 يكفي بصريًا
    contrast = 1 + clip.effect("contrast") / 100.0      # 0..2
    saturation = 1 + clip.effect("saturation") / 100.0  # 0..2
    if (bright, contrast, saturation) == (0.0, 1.0, 1.0):
        return []
    return ["eq=brightness=%.4f:contrast=%.4f:saturation=%.4f"
            % (bright, contrast, saturation)]


def _look(clip):
    """تصحيح الألوان ثم الفلتر البصري: الفلتر يعمل على الصورة بعد ضبطها."""
    return _eq(clip) + filters.chain(clip.filter,
                                     clip.effect("filter_amount"))


def _atempo(factor):
    """
    سلسلة atempo لعامل سرعة.

    المرشّح يقبل 0.5..2.0 وحدها، فالعوامل خارج المدى تُجزّأ حلقاتٍ متتالية.
    تمريرُ 4.0 مباشرةً يجعل FFmpeg يرفض الرسم البياني كلّه.
    """
    out = []
    while factor > 2.0 + 1e-9:
        out.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5 - 1e-9:
        out.append("atempo=0.5")
        factor *= 2.0
    if abs(factor - 1.0) > 1e-9:
        out.append("atempo=%.6f" % factor)
    return out


def _fade(clip, seconds, audio=False):
    """التلاشي بأزمنة الخرج: يُركَّب بعد تغيير السرعة لا قبله."""
    name = "afade" if audio else "fade"
    out = []
    rise = min(clip.effect("fade_in") / 1000.0, seconds)
    drop = min(clip.effect("fade_out") / 1000.0, seconds)
    if rise > 0:
        out.append("%s=t=in:st=0:d=%.4f" % (name, rise))
    if drop > 0:
        out.append("%s=t=out:st=%.4f:d=%.4f"
                   % (name, max(0.0, seconds - drop), drop))
    return out


_AUDIO_SEEN = {}


def _has_audio(path):
    """
    هل في الملفّ تيّار صوت؟ يُسأل مرّةً لكل مسار.

    مرشّح `[N:a?]` يتخطّى السلسلة كلّها إن غاب التيّار، فلا تُنتَج تسميتها -
    ثم يشير إليها amix فيسقط الأمر كلُّه برسالة «matches no streams».
    الخطأ لا يظهر إلّا عند تصدير مشروعٍ فيه طبقةٌ بلا صوت، كنصٍّ متحرّك.
    """
    if path not in _AUDIO_SEEN:
        try:
            _AUDIO_SEEN[path] = bool(media.probe(path).has_audio)
        except Exception:
            _AUDIO_SEEN[path] = False
    return _AUDIO_SEEN[path]


def _is_image(path):
    """الصورة تحتاج -loop عند الإدخال: بلا حلقةٍ تعطي إطارًا واحدًا لا مقطعًا."""
    return media.kind(path) == "image"


def _placement(clip, canvas, seconds, window, shift=0.0):
    """
    مقاس الطبقة وموضعها على اللوحة، بتعبيرات FFmpeg.

    الحجم والموضع من تأثيرات المقطع، والحركة تُضاف فوقهما: الاثنان إزاحةٌ عن
    المركز فتُجمعان بلا تعارض.

    والتكبير والإزاحة يُحسبان بساعتين مختلفتين: التكبير في مرشّح scale على
    تيّار المقطع - زمنه محلّيّ - والإزاحة في مرشّح overlay على الخط الزمني.
    ساعةٌ واحدة لهما تُخرج إحداهما عن موضعها بمقدار بداية المقطع.
    """
    width, height = canvas
    factor = clip.effect("layer_scale") / 100.0
    box = (max(2, int(width * factor) // 2 * 2),
           max(2, int(height * factor) // 2 * 2))
    dx = "%.4f" % (clip.effect("layer_x") / 100.0 * width)
    dy = "%.4f" % (clip.effect("layer_y") / 100.0 * height)

    local = animate.transform(clip.anim_in, clip.anim_out, seconds, window,
                              clip.motion, clip.effect("motion_amount"))
    zoom = local[0] if local is not None else "1"

    shifted = animate.transform(clip.anim_in, clip.anim_out, seconds, window,
                                clip.motion, clip.effect("motion_amount"),
                                shift)
    if shifted is not None:
        dx = "(%s)+(%s)" % (dx, shifted[1])
        dy = "(%s)+(%s)" % (dy, shifted[2])
    return box, zoom, dx, dy


def _fit(stream, width, height, fill, index):
    """
    يُدخل المقطع في اللوحة. يرجع (أسطر الرسم، المدخل التالي).

    بالأشرطة السوداء تكفي سلسلة واحدة. أما الخلفية الضبابية فتحتاج نسخةً
    ثانية من الصورة مكبَّرةً ومقصوصةً وراء الأصل، والنسخ يقطع السلسلة فتصير
    أسطرًا مستقلّة.
    """
    if fill != "blur":
        return ([], ["setpts=PTS-STARTPTS",
                     "scale=%d:%d:force_original_aspect_ratio=decrease"
                     % (width, height),
                     "pad=%d:%d:(ow-iw)/2:(oh-ih)/2" % (width, height),
                     "setsar=1"], stream)

    sigma = max(6.0, min(width, height) / 26.0)
    lines = [
        "%ssetpts=PTS-STARTPTS,split=2[bg%d][fg%d]" % (stream, index, index),
        "[bg%d]scale=%d:%d:force_original_aspect_ratio=increase,"
        "crop=%d:%d,gblur=sigma=%.1f,setsar=1[bb%d]"
        % (index, width, height, width, height, sigma, index),
        "[fg%d]scale=%d:%d:force_original_aspect_ratio=decrease,setsar=1[ff%d]"
        % (index, width, height, index),
        "[bb%d][ff%d]overlay=(W-w)/2:(H-h)/2[fit%d]" % (index, index, index),
    ]
    return (lines, [], "[fit%d]" % index)


def _segments(project, track):
    """
    مقاطع المسار مرتّبةً، مع الفجوات بينها.

    يُرجع قائمة (clip أو None، عدد الإطارات). None تعني فجوة.
    """
    out = []
    cursor = 0
    for clip in sorted(track.clips, key=lambda c: c.start):
        if clip.start > cursor:
            out.append((None, clip.start - cursor))
        out.append((clip, clip.duration))
        cursor = clip.end
    return out


def still(project, frame, target, width=640):
    """
    يرسم إطارًا واحدًا من الخط الزمني إلى ملف صورة، بمرشّحات التصدير نفسها.

    هذي هي المعاينة: لا نسخةً ثانية من منطق التأثيرات في الواجهة. أيّ منطقٍ
    ثانٍ ينحرف عن التصدير بلا أن يلاحظ أحد، فيصمّم المستخدم على صورةٍ ويصدّر
    غيرها.

    يرجع True عند النجاح، وFalse إن لم يكن تحت رأس التشغيل شيء أو فشل الرسم.
    """
    track = project.track("video")
    clip = track.at(frame) if track else None
    layers = [layer.at(frame) for layer in project.layers
              if layer is not track and layer.visible]
    layers = [c for c in layers if c is not None]
    if clip is None and not layers:
        return False

    ratio = project.height / float(project.width or 1)
    canvas = (int(width) // 2 * 2, int(width * ratio) // 2 * 2)

    if clip is None:
        # لا مقطع في الأساس لكن فوقه طبقات: لوحةٌ سوداء تُركَّب عليها
        args = [tools.ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=%dx%d:d=0.1" % canvas]
        base, graph, stream = "[0:v]", [], 0
        return _compose_still(project, frame, layers, canvas, args, base,
                              graph, stream, target)

    local = project.seconds(frame - clip.start)          # زمنه داخل المقطع
    seconds = project.seconds(clip.duration)
    source_at = project.seconds(clip.offset) + local * clip.speed

    chain = ["scale=%d:%d:force_original_aspect_ratio=decrease" % canvas,
             "pad=%d:%d:(ow-iw)/2:(oh-ih)/2" % canvas, "setsar=1"]
    chain += _look(clip)

    # الحركة تُحسب رقميًّا عند هذي اللحظة: الإطار الواحد لا يمرّ عليه زمن
    zoom, dx, dy = animate.sample(clip.anim_in, clip.anim_out, seconds,
                                  clip.effect("anim_ms") / 1000.0, local,
                                  canvas, clip.motion,
                                  clip.effect("motion_amount"))
    if abs(zoom - 1.0) > 1e-6 or abs(dx) > 0.5 or abs(dy) > 0.5:
        inner = (max(2, int(canvas[0] * zoom) // 2 * 2),
                 max(2, int(canvas[1] * zoom) // 2 * 2))
        chain.append("scale=%d:%d" % inner)
        chain.append("pad=%d:%d:%d:%d:color=black"
                     % (canvas[0], canvas[1],
                        int((canvas[0] - inner[0]) / 2 + dx),
                        int((canvas[1] - inner[1]) / 2 + dy)))
        chain.append("crop=%d:%d:0:0" % canvas)

    # التلاشي يظهر في المعاينة كما يظهر في الملف الناتج
    rise = clip.effect("fade_in") / 1000.0
    drop = clip.effect("fade_out") / 1000.0
    if rise > 0 and local < rise:
        chain.append("colorlevels=romax=%.4f:gomax=%.4f:bomax=%.4f"
                     % ((local / rise,) * 3))
    elif drop > 0 and local > seconds - drop:
        left = max(0.0, (seconds - local) / drop)
        chain.append("colorlevels=romax=%.4f:gomax=%.4f:bomax=%.4f"
                     % ((left,) * 3))

    args = [tools.ffmpeg(), "-y", "-v", "error",
            "-ss", "%.6f" % max(0.0, source_at), "-i", clip.source]
    if not layers:
        return (_run_still(args + ["-frames:v", "1", "-vf", ",".join(chain),
                                   target])
                and os.path.exists(target))
    return _compose_still(project, frame, layers, canvas, args,
                          "[b]", ["[0:v]%s[b]" % ",".join(chain)], 0, target)


def _compose_still(project, frame, layers, canvas, args, base, graph, stream,
                   target):
    """
    يركّب طبقات المعاينة على الأساس في استدعاءٍ واحد.

    المعاينة تُظهر الطبقات كما تظهر في الملف الناتج، وإلا وضع المصمّم صورةً
    وهو لا يرى أين تقع.
    """
    for clip in layers:
        local = project.seconds(frame - clip.start)
        seconds = project.seconds(clip.duration)
        still_image = _is_image(clip.source)
        if still_image:
            args += ["-i", clip.source]
        else:
            args += ["-ss", "%.6f" % (project.seconds(clip.offset)
                                      + local * clip.speed),
                     "-i", clip.source]
        stream += 1

        box, _zoom_expr, _dx, _dy = _placement(clip, canvas, seconds, 1.0)
        zoom, dx, dy = animate.sample(clip.anim_in, clip.anim_out, seconds,
                                      clip.effect("anim_ms") / 1000.0, local,
                                      canvas, clip.motion,
                                      clip.effect("motion_amount"))
        box = (max(2, int(box[0] * zoom) // 2 * 2),
               max(2, int(box[1] * zoom) // 2 * 2))
        chain = ["scale=%d:%d:force_original_aspect_ratio=decrease" % box]
        chain += _look(clip)
        chain.append("format=rgba")
        graph.append("[%d:v]%s[o%d]" % (stream, ",".join(chain), stream))

        x = int((canvas[0] - box[0]) / 2
                + clip.effect("layer_x") / 100.0 * canvas[0] + dx)
        y = int((canvas[1] - box[1]) / 2
                + clip.effect("layer_y") / 100.0 * canvas[1] + dy)
        graph.append("%s[o%d]overlay=%d:%d[m%d]" % (base, stream, x, y,
                                                    stream))
        base = "[m%d]" % stream

    args += ["-filter_complex", ";".join(graph), "-map", base,
             "-frames:v", "1", target]
    return _run_still(args) and os.path.exists(target)


def _run_still(args):
    try:
        done = subprocess.run(args, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=25,
                              creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def build(project, output, encoder="libx264", quality=70, scale=None,
          fps=None, interpolate=False):
    """
    يبني أمر FFmpeg كاملًا. لا يشغّل شيئًا.

    scale: (عرض، ارتفاع) أو None لمقاس المشروع.
    fps: معدّل إطارات الخرج، أو None لمعدّل المشروع.
    interpolate: توليد إطارات بينيّة بدل تكرارها. مكلف جدًا.
    """
    video_track = project.track("video")
    audio_track = project.track("audio")
    if not (video_track and video_track.clips) and \
            not (audio_track and audio_track.clips):
        raise ExportError("الخط الزمني فارغ")

    width, height = scale or (project.width, project.height)
    width, height = int(width) // 2 * 2, int(height) // 2 * 2   # زوجيّة لـ H.264
    rate = float(fps or project.fps)

    args = [tools.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    graph, index = [], 0
    video_labels, audio_labels = [], []
    spans = []                  # (مدّة القطعة، مقطعها أو None للفجوة)

    for clip, frames in _segments(project, video_track) if video_track else []:
        seconds = project.seconds(frames)
        if clip is None:
            graph.append("color=c=black:s=%dx%d:r=%g:d=%.6f[v%d]"
                         % (width, height, rate, seconds, index))
            graph.append("anullsrc=r=%d:cl=stereo:d=%.6f[a%d]"
                         % (AUDIO_RATE, seconds, index))
        else:
            # المدّة على الخط هي المرجع: سرعة ٢٠٠٪ تستهلك ضعف ثوانى المصدر
            # لتملأ المدّة نفسها، فالقصّ عند المدخل يُضرب في السرعة.
            speed = clip.speed
            source_seconds = seconds * speed
            frozen = _is_image(clip.source)
            if frozen:
                # الصورة إطارٌ واحد: بلا حلقةٍ تنتهي فورًا ويسقط الرسم كلّه
                args += ["-loop", "1", "-t", "%.6f" % seconds,
                         "-i", clip.source]
            else:
                args += ["-ss", "%.6f" % project.seconds(clip.offset),
                         "-t", "%.6f" % source_seconds, "-i", clip.source]
            stream = len([a for a in args if a == "-i"]) - 1

            lines, chain, head = _fit("[%d:v]" % stream, width, height,
                                      project.fill, index)
            graph += lines
            chain = list(chain)
            chain += _look(clip)
            if not frozen and abs(speed - 1.0) > 1e-9:
                chain.append("setpts=PTS/%.6f" % speed)
            chain.append("fps=%g" % rate)

            # الانقلاب قبل الميلان: هذا يقلب اللوح في الفضاء، وذاك يميله
            # في المستوى. وperspective يقرأ رقم الإطار لا الزمن، فيأخذ
            # معدّل الإطارات ليحوّله.
            turned = animate.warp(clip.flip, clip.effect("flip_amount"),
                                  seconds, rate,
                                  clip.effect("anim_ms") / 1000.0)
            if turned:
                chain.append(turned)

            # الميلان بعد الإدخال في اللوحة: التيّار حينها بمقاس اللوحة
            # وأشرطتُه السوداء معه، فتميل البطاقةُ كاملةً على سوادها. وساعته
            # محلّية لأن setpts=PTS-STARTPTS في أوّل السلسلة.
            lean = animate.turn(clip.tilt, clip.effect("tilt_amount"),
                                seconds)
            if lean:
                chain.append("rotate=a='%s':fillcolor=black" % lean)

            # الحركة بعد تغيير السرعة: نافذتها بزمن الخرج الذي يراه المستخدم.
            # والتلاشي بعد التركيب لا قبله، وإلا تلاشى المقطعُ وحده وبقيت
            # اللوحة تحته ظاهرة.
            motion = animate.transform(clip.anim_in, clip.anim_out, seconds,
                                       clip.effect("anim_ms") / 1000.0,
                                       clip.motion,
                                       clip.effect("motion_amount"))
            if motion is None:
                chain += _fade(clip, seconds)
                graph.append("%s%s[v%d]" % (head, ",".join(chain), index))
            else:
                zoom, dx, dy = motion
                chain.append(
                    "scale=w='trunc(iw*(%s)/2)*2':h='trunc(ih*(%s)/2)*2'"
                    ":eval=frame" % (zoom, zoom))
                graph.append("%s%s[f%d]" % (head, ",".join(chain), index))
                graph.append("color=c=black:s=%dx%d:r=%g:d=%.6f[c%d]"
                             % (width, height, rate, seconds, index))
                over = ["overlay=x='(W-w)/2+(%s)':y='(H-h)/2+(%s)':shortest=1"
                        % (dx, dy)]
                over += _fade(clip, seconds)
                graph.append("[c%d][f%d]%s[v%d]"
                             % (index, index, ",".join(over), index))

            # الصوت قد لا يوجد في المصدر: نخلطه مع صمت بطول المقطع فيوجد دائمًا.
            # طول الصمت بزمن المصدر لأن atempo بعده يضغطه إلى زمن الخرج.
            if frozen:
                # الصورة بلا صوت: صمتٌ بطولها بدل خلطٍ مع تيّارٍ غير موجود
                graph.append("anullsrc=r=%d:cl=stereo:d=%.6f[a%d]"
                             % (AUDIO_RATE, seconds, index))
            else:
                achain = ["aresample=%d" % AUDIO_RATE, "asetpts=PTS-STARTPTS"]
                achain += _atempo(speed)
                if clip.effect("volume") != 100:
                    achain.append("volume=%.4f"
                                  % (clip.effect("volume") / 100.0))
                achain += _fade(clip, seconds, audio=True)
                graph.append(
                    "anullsrc=r=%d:cl=stereo:d=%.6f[s%d];"
                    "[%d:a?][s%d]amix=inputs=2:duration=first"
                    ":dropout_transition=0,%s[a%d]"
                    % (AUDIO_RATE, source_seconds, index, stream, index,
                       ",".join(achain), index))
        video_labels.append("[v%d]" % index)
        audio_labels.append("[a%d]" % index)
        spans.append((seconds, clip))
        index += 1

    if not video_labels:
        raise ExportError("لا يوجد مسار فيديو لتصديره")

    # الانتقالات: سلسلة xfade بدل الوصل المباشر.
    #
    # كل انتقالٍ يبتلع مدّته من الطول، فنمدّ القطعة الخارجة بمقداره من ذيل
    # مصدرها (tpad يستنسخ آخر إطار إن نفد)، فيصير (d1+D)+d2-D = d1+d2
    # ويطابق الناتج الخط الزمني تمامًا.
    fades = []
    for position in range(1, len(spans)):
        after, clip = spans[position]
        before = spans[position - 1][0]
        span = transitions.window(clip, before, after) if clip else 0.0
        fades.append(span if transitions.mode(clip.trans if clip else "")
                     else 0.0)

    if any(fades):
        current = video_labels[0]
        total = spans[0][0]
        for position in range(1, len(spans)):
            span = fades[position - 1]
            nxt = video_labels[position]
            if span <= 0:
                graph.append("%s%sconcat=n=2:v=1:a=0[j%d]"
                             % (current, nxt, position))
                total += spans[position][0]
            else:
                # settb على الطرفين: xfade يشترط تطابق القاعدة الزمنية، و
                # concat وtpad يحوّلان قاعدتهما إلى AVTB بينما يبقى المقطع
                # الجديد على قاعدة معدّل إطاراته، فيرفض الرسمَ البياني كلّه.
                graph.append("%stpad=stop_mode=clone:stop_duration=%.4f,"
                             "settb=AVTB[p%d]" % (current, span, position))
                graph.append("%ssettb=AVTB[q%d]" % (nxt, position))
                graph.append("[p%d][q%d]xfade=transition=%s:duration=%.4f"
                             ":offset=%.4f[j%d]"
                             % (position, position,
                                transitions.mode(spans[position][1].trans),
                                span, max(0.0, total), position))
                total += spans[position][0]
            current = "[j%d]" % position
        graph.append("%snull[vcat]" % current)
    else:
        graph.append("%sconcat=n=%d:v=1:a=0[vcat]"
                     % ("".join(video_labels), len(video_labels)))

    graph.append("%sconcat=n=%d:v=0:a=1[acat]"
                 % ("".join(audio_labels), len(audio_labels)))

    video_out = "[vcat]"
    if interpolate:
        graph.append("[vcat]minterpolate=fps=%g:mi_mode=mci[vint]" % rate)
        video_out = "[vint]"

    # ---------------------------------------------------------- الطبقات فوق
    #
    # الأساس آخر مسارات الفيديو، وما فوقه يُركَّب واحدًا واحدًا من الأسفل إلى
    # الأعلى. كل مقطع يُزاح زمنيًّا إلى موضعه على الخط ثم يُفتَح بـ enable في
    # نافذته وحدها، فلا يظهر قبلها ولا يبقى بعدها.
    extra = []
    layers = [t for t in project.layers if t is not video_track and t.visible]
    for layer in reversed(layers):
        for clip in sorted(layer.clips, key=lambda c: c.start):
            seconds = project.seconds(clip.duration)
            begin = project.seconds(clip.start)
            speed = clip.speed
            still_image = _is_image(clip.source)

            if still_image:
                args += ["-loop", "1", "-t", "%.6f" % seconds,
                         "-i", clip.source]
            else:
                args += ["-ss", "%.6f" % project.seconds(clip.offset),
                         "-t", "%.6f" % (seconds * speed), "-i", clip.source]
            stream = len([a for a in args if a == "-i"]) - 1

            # الإزاحة تُحسب في overlay بزمن الخط الزمني، فنردّ ساعتها إلى
            # بداية المقطع؛ والتكبير يُحسب في scale بزمنٍ محلّيّ أصلًا
            box, zoom, dx, dy = _placement(
                clip, (width, height), seconds,
                clip.effect("anim_ms") / 1000.0, begin)
            chain = ["setpts=PTS-STARTPTS",
                     # بلا حشو: الطبقة تُركَّب بمقاسها فتبقى شفافيّة الصورة
                     "scale=%d:%d:force_original_aspect_ratio=decrease" % box]
            chain += _look(clip)
            if not still_image and abs(speed - 1.0) > 1e-9:
                chain.append("setpts=PTS/%.6f" % speed)
            chain.append("fps=%g" % rate)
            if zoom != "1":
                chain.append("scale=w='trunc(iw*(%s)/2)*2':h='trunc(ih*(%s)"
                             "/2)*2':eval=frame" % (zoom, zoom))
            chain += _fade(clip, seconds)
            # الصورة ذات القناة الرابعة تفقد شفافيّتها بلا تثبيت الصيغة
            chain.append("format=yuva420p")
            # الميلان هنا لا في overlay: الساعةُ الثالثة. setpts=PTS-STARTPTS
            # في أوّل السلسلة ردّ زمنَ التيّار إلى الصفر، فـ`t` عند rotate
            # زمنٌ محلّيّ - بخلاف الإزاحة التي تُحسب على الخط الزمني.
            spun = animate.warp(clip.flip, clip.effect("flip_amount"),
                                seconds, rate,
                                clip.effect("anim_ms") / 1000.0)
            if spun:
                chain.append(spun)
            angle = animate.turn(clip.tilt, clip.effect("tilt_amount"),
                                 seconds)
            if angle:
                # ow/oh يوسّعان اللوحة لقطر الإطار، وإلا قُصّت أركان
                # البطاقة المائلة
                chain.append("rotate=a='%s':ow='hypot(iw,ih)'"
                             ":oh='hypot(iw,ih)':fillcolor=none" % angle)
            chain.append("setpts=PTS+%.6f/TB" % begin)
            graph.append("[%d:v]%s[l%d]" % (stream, ",".join(chain), stream))

            graph.append(
                "%s[l%d]overlay=x='(W-w)/2+(%s)':y='(H-h)/2+(%s)'"
                ":enable='between(t,%.4f,%.4f)':eof_action=pass:repeatlast=0"
                "[k%d]"
                % (video_out, stream, dx, dy, begin, begin + seconds, stream))
            video_out = "[k%d]" % stream

            # مصدرٌ بلا صوت لا تُبنى له سلسلة: `[N:a?]` يتخطّاها فلا
            # تُنتَج تسميتُها، ثم يشير إليها amix فيسقط الأمر كلُّه
            if (not still_image and clip.effect("volume") > 0
                    and _has_audio(clip.source)):
                delay = int(begin * 1000)
                achain = ["aresample=%d" % AUDIO_RATE] + _atempo(speed)
                if clip.effect("volume") != 100:
                    achain.append("volume=%.4f"
                                  % (clip.effect("volume") / 100.0))
                achain.append("adelay=%d|%d" % (delay, delay))
                graph.append("[%d:a?]%s[y%d]"
                             % (stream, ",".join(achain), stream))
                extra.append("[y%d]" % stream)

    # مسار الصوت المستقل يُخلط فوق صوت الفيديو
    for clip, frames in _segments(project, audio_track) if audio_track else []:
        if clip is None:
            continue
        # المسار الموسيقيّ يمرّ بما يمرّ به صوت الفيديو: الصوت والتلاشي
        # والسرعة. بدونها تكون منزلقاتها معروضةً في اللوحة وبلا أثر، وتنتهي
        # الموسيقى قطعًا حادًّا في آخر المقطع.
        seconds = project.seconds(frames)
        args += ["-ss", "%.6f" % project.seconds(clip.offset),
                 "-t", "%.6f" % (seconds * clip.speed), "-i", clip.source]
        stream = len([a for a in args if a == "-i"]) - 1
        delay = int(project.seconds(clip.start) * 1000)
        achain = ["aresample=%d" % AUDIO_RATE] + _atempo(clip.speed)
        if clip.effect("volume") != 100:
            achain.append("volume=%.4f" % (clip.effect("volume") / 100.0))
        achain += _fade(clip, seconds, audio=True)
        achain.append("adelay=%d|%d" % (delay, delay))
        graph.append("[%d:a]%s[x%d]" % (stream, ",".join(achain), stream))
        extra.append("[x%d]" % stream)

    audio_out = "[acat]"
    if extra:
        graph.append("[acat]%samix=inputs=%d:duration=longest[amixed]"
                     % ("".join(extra), len(extra) + 1))
        audio_out = "[amixed]"

    args += ["-filter_complex", ";".join(graph),
             "-map", video_out, "-map", audio_out,
             "-c:v", encoder] + _quality(encoder, quality) + \
            ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart",
             "-progress", "pipe:1", "-nostats", output]
    return args


COMMAND_LIMIT = 30000       # ويندوز يرفض سطر أوامرٍ فوق ٣٢٧٦٧ حرفًا


def _as_script(args):
    """
    ينقل الرسم البياني إلى ملفٍّ إن طال الأمر. يرجع (الأمر، مسار الملف).

    ويندوز يرفض سطر أوامر أطول من ٣٢٧٦٧ حرفًا، ورسالته «اسم الملف أو
    الامتداد طويل جدًّا» - رسالةٌ لا تدلّ على السبب بحال. ومشروعٌ فيه أربعون
    قصّةً وخمسون طبقة يتجاوز الحدّ بسهولة، فيفشل تصديرٌ رسمُه البيانيّ سليم.
    FFmpeg يقرأ الرسم من ملفٍّ بـ -filter_complex_script، فينتقل الطولُ من
    سطر الأوامر إلى القرص حيث لا حدّ له.
    """
    if sum(len(a) + 1 for a in args) <= COMMAND_LIMIT:
        return args, None
    if "-filter_complex" not in args:
        return args, None
    spot = args.index("-filter_complex")
    handle, path = tempfile.mkstemp(prefix="wun_cut_graph_", suffix=".txt")
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(args[spot + 1])
    swapped = list(args)
    swapped[spot:spot + 2] = ["-filter_complex_script", path]
    return swapped, path


class ExportJob:
    """تشغيل التصدير مع تقدّم وإلغاء. بلا Qt: تُمرَّر ردود النداء."""

    def __init__(self, project, output, **options):
        self.project = project
        self.output = output
        self.args = build(project, output, **options)
        self.total = max(1, project.duration)
        self.process = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def run(self, on_progress=None):
        """يشغّل حتى الانتهاء. يرجع True عند النجاح."""
        args, script = _as_script(self.args)
        try:
            return self._spin(args, on_progress)
        finally:
            if script:
                try:
                    os.remove(script)
                except OSError:
                    pass

    def _spin(self, args, on_progress):
        self.process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=NO_WINDOW)

        errors = []
        drain = threading.Thread(
            target=lambda: errors.append(
                self.process.stderr.read().decode("utf-8", "replace")),
            daemon=True)
        drain.start()

        for raw in self.process.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("out_time_ms=") and on_progress:
                try:
                    micros = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                done = self.project.frames(max(0, micros) / 1e6)
                if on_progress(min(done, self.total), self.total) is False:
                    self.cancel()
                    break

        code = self.process.wait()
        drain.join(timeout=2)
        if self._cancelled:
            if os.path.exists(self.output):
                try:
                    os.remove(self.output)
                except OSError:
                    pass
            return False
        if code != 0:
            detail = (errors[0] if errors else "").strip().splitlines()
            raise ExportError(detail[-1] if detail else "فشل FFmpeg (%d)" % code)
        return True


def demo():
    """فحص ذاتي: بناء الأمر، ثم تصدير حقيقي والتحقّق من مدّته."""
    import io
    import json
    import re
    import sys
    import tempfile
    from fractions import Fraction

    sys.path.insert(0, os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from wun_cut.core.project import Clip, Editor, Project

    found = encoders()
    print("المرمّزات:", ", ".join("%s (%s)" % (n, l) for n, l in found) or "لا شيء")
    assert found, "لا يوجد أي مرمّز H.264"

    # --- بناء الأمر: فجوة تُملأ سوادًا لا تُطوى ---
    editor = Editor(Project(Fraction(30, 1), 640, 360))
    editor.append("video", Clip("a.mp4", 0, 30))
    late = editor.append("video", Clip("b.mp4", 0, 30))
    editor.move(late, 90)               # فجوة 30 إطارًا بينهما
    args = build(editor.project, "out.mp4")
    graph = args[args.index("-filter_complex") + 1]
    assert "color=c=black" in graph, "الفجوة لم تُملأ سوادًا"
    assert "concat=n=3" in graph, graph[:200]
    assert args[args.index("-c:v") + 1] == "libx264"
    print("بناء الأمر: ٣ مقاطع (اثنان وفجوة) ✓")

    # --- المسار الموسيقيّ: منزلقاته تصل إلى الأمر فعلًا ---
    #
    # مسارٌ يعرض منزلقات صوتٍ وتلاشٍ ثم يتجاهلها أسوأُ من مسارٍ بلا منزلقات:
    # المستخدم يسحب فيسمع الشيء نفسه ويظنّ الخطأ في سمعه.
    tune = Editor(Project(Fraction(30, 1), 640, 360))
    tune.append("video", Clip("a.mp4", 0, 90))
    song = tune.append("audio", Clip("song.mp3", 0, 90))
    tune.set_effect(song, "volume", 40)
    tune.set_effect(song, "fade_in", 1000)
    tune.set_effect(song, "fade_out", 2000)
    tune.set_effect(song, "speed", 150)
    built = build(tune.project, "out.mp4")
    music = built[built.index("-filter_complex") + 1]
    line = [row for row in music.split(";")
            if re.match(r"^\[\d+:a\]", row) and row.endswith("]")
            and "adelay" in row]
    assert len(line) == 1, "المسار الموسيقيّ لم يُبنَ: %s" % music[-200:]
    line = line[0]
    for piece in ("volume=0.4000", "afade=t=in", "afade=t=out", "atempo=",
                  "adelay="):
        assert piece in line, "%s غائبٌ عن المسار الموسيقيّ: %s" % (piece, line)
    # التلاشي بزمن الخرج لا زمن المصدر: ٩٠ إطارًا على ٣٠ = ٣ ثوانٍ
    assert "afade=t=out:st=1.0000:d=2.0000" in line, line
    print("المسار الموسيقيّ: صوتٌ وتلاشٍ وسرعة تصل إلى الأمر ✓")

    # --- ميلان الطبقة يصل إلى الأمر، ويوسّع اللوحة فلا تُقصّ الأركان ---
    lean = Editor(Project(Fraction(30, 1), 1280, 720))
    lean.append("video", Clip("base.mp4", 0, 90))
    deck = lean.project.add_layer("بطاقة")
    card = Clip("card.mp4", 0, 60)
    card.set_effect("layer_scale", 45)
    card.tilt = "tilt_in"
    lean.append(deck, card)
    lean.move(card, 15)
    drawn = build(lean.project, "out.mp4")
    tilted = drawn[drawn.index("-filter_complex") + 1]
    spin = [row for row in tilted.split(";") if "rotate=" in row]
    assert len(spin) == 1, "الميلان لم يصل: %s" % tilted[-220:]
    assert "fillcolor=none" in spin[0], spin[0]
    assert "hypot(iw,ih)" in spin[0], "اللوحة لم تتوسّع فستُقصّ الأركان"
    # وترتيبه بعد تثبيت الصيغة، وإلا دار إطارٌ بلا شفافية
    assert spin[0].index("format=yuva420p") < spin[0].index("rotate="), spin[0]
    card.tilt = ""
    plain_graph = build(lean.project, "out.mp4")
    plain_graph = plain_graph[plain_graph.index("-filter_complex") + 1]
    assert "rotate=" not in plain_graph, "الميلان ظهر بلا اختياره"
    print("ميلان الطبقة: زاويةٌ متحرّكة ولوحةٌ موسَّعة ✓")

    # وعلى المسار الأساس: هناك تميل اللوحةُ كلّها بأشرطتها، وهذا ما يعطي
    # شكلَ البطاقة في اللوحة العمودية
    base_lean = Editor(Project(Fraction(30, 1), 1080, 1920))
    shot = base_lean.append("video", Clip("v.mp4", 0, 60))
    shot.tilt = "sway"
    shot.motion = "zoom_in"
    made = build(base_lean.project, "out.mp4")
    text = made[made.index("-filter_complex") + 1]
    assert "rotate=" in text and "fillcolor=black" in text, text[:200]
    assert text.index("pad=") < text.index("rotate="),         "الميلان قبل الإدخال في اللوحة: ستميل الصورة بلا أشرطتها"
    assert text.index("rotate=") < text.index("overlay="),         "الميلان بعد الإزاحة: سيدور الموضع معه"
    # --- طبقةٌ مصدرُها بلا صوت لا تُنتج تسميةً معلّقة ---
    #
    # `[N:a?]` يتخطّى السلسلة حين يغيب التيّار فلا تُنتج تسميتُها، ثم يشير
    # إليها amix فيسقط الأمرُ كلُّه: «matches no streams». والنصّ المتحرّك
    # مقطعٌ بلا صوت، فكلُّ مشروعٍ فيه واحدٌ كان يفشل تصديرُه.
    shed = tempfile.mkdtemp(prefix="wun_cut_quiet_")
    try:
        noisy = os.path.join(shed, "loud.mp4")
        silent = os.path.join(shed, "quiet.mp4")
        subprocess.run(
            [tools.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2:r=30",
             "-f", "lavfi", "-i", "sine=f=440:d=2",
             "-shortest", noisy], check=True, creationflags=NO_WINDOW)
        subprocess.run(
            [tools.ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc2=s=160x90:d=1:r=30",
             "-an", silent], check=True, creationflags=NO_WINDOW)
        assert _has_audio(noisy) and not _has_audio(silent), "القراءة خاطئة"

        hush = Editor(Project(Fraction(30, 1), 640, 360))
        hush.append("video", Clip(noisy, 0, 60))
        over = hush.project.add_layer("نصّ")
        quiet = Clip(silent, 0, 30)
        quiet.set_effect("layer_scale", 50)
        hush.append(over, quiet)
        hush.move(quiet, 10)
        graph_text = build(hush.project, os.path.join(shed, "out.mp4"))
        graph_text = graph_text[graph_text.index("-filter_complex") + 1]
        # الطبقةُ الوحيدة بلا صوت، فلا يصحّ أن تُبنى لها سلسلةُ صوتٍ
        # أصلًا. رقمُ المدخل يتغيّر بتغيّر المشروع، فتُفحص التسميةُ نفسُها
        # لا رقمُها.
        assert "[y" not in graph_text, (
            "بُنيت سلسلةُ صوتٍ لطبقةٍ بلا صوت")
        print("طبقةٌ بلا صوت: بلا تسميةٍ معلّقة ✓")
    finally:
        shutil.rmtree(shed, ignore_errors=True)


    # --- الأمر الطويل ينتقل رسمُه إلى ملفّ ---
    #
    # ويندوز يرفض ما فوق ٣٢٧٦٧ حرفًا برسالةٍ عن «اسم ملفّ طويل»، فمشروعٌ
    # غنيّ يفشل تصديرُه بلا أن يفهم أحدٌ لماذا.
    heavy = Editor(Project(Fraction(60, 1), 1920, 1080))
    for step in range(40):
        shot = heavy.append("video", Clip("clip%02d.mp4" % step, 0, 120))
        shot.motion = "zoom_pan"                # التحريك يطيل تعابير scale
        shot.filter = "sepia"
        shot.trans = "circleopen"
        heavy.set_effect(shot, "contrast", 10)
    deck = heavy.project.add_layer("طبقة")
    for step in range(40):
        piece = Clip("badge%02d.png" % step, 0, 60)
        piece.set_effect("layer_scale", 20)
        heavy.append(deck, piece)
        heavy.move(piece, step * 120)
    big = build(heavy.project, "out.mp4")
    raw = sum(len(a) + 1 for a in big)
    assert raw > COMMAND_LIMIT, "المشروع الثقيل لم يتجاوز الحدّ: %d" % raw
    lean, script = _as_script(big)
    try:
        assert script and os.path.exists(script), "لم يُكتب ملفّ الرسم"
        assert "-filter_complex_script" in lean and "-filter_complex" not in lean
        assert sum(len(a) + 1 for a in lean) < COMMAND_LIMIT, "ما زال طويلًا"
        assert io.open(script, encoding="utf-8").read() ==             big[big.index("-filter_complex") + 1], "الرسم لم يُنقل كما هو"
        print("الأمر الطويل: %d حرفًا ← %d وملفُّ رسمٍ %d حرفًا ✓"
              % (raw, sum(len(a) + 1 for a in lean),
                 os.path.getsize(script)))
    finally:
        if script:
            os.remove(script)
    # والقصير يبقى كما هو
    plain, none_yet = _as_script(build(editor.project, "out.mp4"))
    assert none_yet is None and "-filter_complex" in plain

    try:
        build(Editor(Project()).project, "x.mp4")
    except ExportError:
        print("الخط الزمني الفارغ يرفع خطأ ✓")
    else:
        raise AssertionError("الخط الفارغ لم يرفع خطأ")

    # --- التأثيرات تصل إلى الرسم البياني ---
    assert _atempo(1.0) == []
    for factor in (0.25, 0.4, 0.5, 1.5, 2.0, 3.0, 4.0):
        links = _atempo(factor)
        product = 1.0
        for link in links:
            value = float(link.split("=")[1])
            assert 0.5 <= value <= 2.0, "حلقة خارج مدى atempo: %s" % link
            product *= value
        assert abs(product - factor) < 1e-6, (factor, links)
    assert _eq(Clip("a.mp4", 0, 1)) == [], "المقطع الخام أنتج مرشّح eq"

    fancy = Editor(Project(Fraction(30, 1), 640, 360))
    shot = fancy.append("video", Clip("a.mp4", 0, 60))
    for name, value in (("brightness", 20), ("saturation", -30),
                        ("speed", 400), ("volume", 50), ("fade_in", 500),
                        ("fade_out", 500)):
        fancy.set_effect(shot, name, value)
    text = build(fancy.project, "out.mp4")
    graph = text[text.index("-filter_complex") + 1]
    for needle in ("eq=brightness", "setpts=PTS/4", "atempo=2.0",
                   "volume=0.5000", "fade=t=in", "fade=t=out",
                   "afade=t=in", "afade=t=out"):
        assert needle in graph, "%s غائب عن الرسم البياني" % needle
    # السرعة ٤٠٠٪ تلتهم ٤ أضعاف زمن المصدر لتملأ ثانيتَي الخط
    assert "%.6f" % 8.0 in text, "قصّ المدخل لم يُضرب في السرعة"
    print("التأثيرات تصل إلى الرسم البياني: eq، سرعة، صوت، تلاشٍ ✓")

    # --- فجوة ثم انتقال: القاعدة الزمنية ---
    # concat يحوّل قاعدته إلى AVTB وxfade يشترط تطابق قاعدتَي مدخلَيه، فمشروعٌ
    # فيه فجوةٌ قبل مقاطعه كان يُسقط التصدير كلّه بلا أي ملف.
    gapped = Editor(Project(Fraction(30, 1), 320, 180))
    one = gapped.append("video", Clip("a.mp4", 0, 60))
    gapped.move(one, 30)                          # فجوة قبل الأول
    two = gapped.append("video", Clip("b.mp4", 0, 60))
    gapped.set_animation(two, "trans", "fade")
    text = build(gapped.project, "out.mp4")
    graph = text[text.index("-filter_complex") + 1]
    assert "xfade" in graph and "concat=n=2" in graph, graph[:200]
    assert graph.count("settb=AVTB") >= 2,         "طرفا xfade بلا توحيد القاعدة الزمنية: %s" % graph[:200]
    for part in graph.split(";"):
        if "xfade" in part:
            assert part.count("[q") or "settb" in part, part
    print("فجوة + انتقال: قاعدة زمنية موحّدة على الطرفين ✓")

    # --- صورة على المسار الأساس ---
    # الصورة إطارٌ واحد: بلا -loop تنتهي فورًا وبلا صوتٍ ينهار الخلط، وكان
    # إفلاتُ صورةٍ على المسار الرئيسي يُسقط التصدير كلّه.
    stills = Editor(Project(Fraction(30, 1), 320, 180))
    stills.append("video", Clip("photo.png", 0, 60))
    frames_args = build(stills.project, "out.mp4")
    assert "-loop" in frames_args, "الصورة على الأساس بلا حلقة"
    graph = frames_args[frames_args.index("-filter_complex") + 1]
    assert "[0:a?]" not in graph, "خلط صوتٍ لصورةٍ بلا صوت"
    assert "anullsrc" in graph, "الصورة بلا مسار صمت"
    print("صورة على المسار الأساس: حلقة وصمت ✓")

    # --- تصدير حقيقي ---
    if len(sys.argv) > 1:
        from wun_cut.core import media
        info = media.probe(sys.argv[1])
        project = Project(info.fps, 640, 360)
        editor = Editor(project)
        editor.append("video", Clip(info.path, 0, project.frames(2)))
        second = editor.append("video", Clip(info.path, 0, project.frames(2)))
        editor.move(second, project.frames(3))      # فجوة ثانية واحدة

        out = os.path.join(tempfile.gettempdir(), "wuncut_export.mp4")
        encoder = found[0][0]
        job = ExportJob(project, out, encoder=encoder, quality=60)
        seen = []
        assert job.run(on_progress=lambda d, t: seen.append(d)), "فشل التصدير"

        result = subprocess.run(
            [tools.ffprobe(), "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", out],
            capture_output=True, creationflags=NO_WINDOW)
        data = json.loads(result.stdout.decode("utf-8", "replace"))
        duration = float(data["format"]["duration"])
        kinds = {s["codec_type"] for s in data["streams"]}
        expected = project.seconds(project.duration)
        print("الناتج: %.2f ث (المتوقّع %.2f) | %s | تحديثات تقدّم %d"
              % (duration, expected, ", ".join(sorted(kinds)), len(seen)))
        assert abs(duration - expected) < 0.35, (duration, expected)
        assert kinds == {"video", "audio"}, kinds
        # مقطع قصير قد يصل فيه تحديث واحد فقط: المهم أن ينتهي عند النهاية
        assert seen, "لم يصل أي تقدّم"
        assert seen[-1] >= project.duration * 0.9, (seen[-1], project.duration)
        os.remove(out)

    print("core/export: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
