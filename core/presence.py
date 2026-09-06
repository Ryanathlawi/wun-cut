"""
حالة ديسكورد: أن يظهر «يحرّر في وِن كَت» في ملفّ المستخدم.

ديسكورد يفتح قناةً محلّيّة اسمها discord-ipc-0، وبروتوكولها بسيط: أربعة
بايتات لرمز العملية، وأربعة لطول الحمولة، ثم JSON. فلا حاجة إلى مكتبةٍ
خارجية - المكتبة القياسية تكفي، والاعتماد الأقلّ أقلُّ ما يُصان.

كلُّ شيءٍ هنا يجري في خيطٍ خادم: القناةُ تُقرأ قراءةً حاجزة، وقراءةٌ حاجزة
في خيط الواجهة تُجمّد المحرّر إن تباطأ ديسكورد أو أُغلق في اللحظة الخطأ.
والفشل صامتٌ دائمًا: حالةٌ في ديسكورد لا تستحقّ أن تكسر محرّرًا.
"""

from __future__ import annotations

import json
import os
import queue
import struct
import threading
import time

# معرّف التطبيق في بوّابة مطوّري ديسكورد. ليس سرًّا: كلُّ لعبةٍ تعرض حالتها
# تحمل معرّفها في ملفّها. ومتغيّر البيئة يسبقه، ليُجرَّب معرّفٌ آخر بلا بناء.
CLIENT_ID = os.environ.get("WUN_CUT_DISCORD_ID", "1546038616218669168")

# ديسكورد يكتب فوق الحالة اسمَ التطبيق المسجّل في البوّابة، وهو هناك
# «Wun Studio». فيُرسل الاسم صراحةً مع كل حالة ليظهر البرنامج باسمه هو.
APP_NAME = "Wun Cut"

# اسم الصورة كما رُفعت في البوّابة (Rich Presence ← Art Assets). أي اسمٍ
# غير مطابقٍ يجعل ديسكورد يُسقط الصورة بصمت: لا خطأ، ولا صورة.
LARGE_IMAGE = "wun_cut_icon_512"

PIPE = r"\\.\pipe\discord-ipc-%d" if os.name == "nt" else "%s/discord-ipc-%d"
HANDSHAKE, FRAME, CLOSE = 0, 1, 2
RETRY = 30.0                    # ثوانٍ قبل إعادة المحاولة بعد فشل الاتّصال


def _pipes():
    """المسارات المحتملة للقناة. ديسكورد يرقّمها ٠..٩ حسب عدد نسخه."""
    if os.name == "nt":
        for slot in range(10):
            yield r"\\.\pipe\discord-ipc-%d" % slot
        return
    root = (os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR")
            or "/tmp")
    for slot in range(10):
        yield os.path.join(root, "discord-ipc-%d" % slot)


def _pack(op, payload):
    body = json.dumps(payload).encode("utf-8")
    return struct.pack("<II", op, len(body)) + body


class Presence:
    """
    يعرض حالةً في ديسكورد. آمنٌ حين يكون ديسكورد مغلقًا أو المعرّف فارغًا.

    الاستعمال:
        presence = Presence()
        presence.start()
        presence.show("مشروعي", "١٢ مقطعًا")
        ...
        presence.close()
    """

    def __init__(self, client_id=None):
        # None تعني «خذ الثابت»، والفراغ يعني «بلا معرّفٍ عمدًا»
        self.client_id = CLIENT_ID if client_id is None else client_id
        self._pipe = None
        self._orders = queue.Queue()
        self._worker = None
        self._stop = threading.Event()
        self.started_at = int(time.time())
        self.last_error = ""

    # ------------------------------------------------------------ الاتّصال

    def _open(self):
        for path in _pipes():
            try:
                pipe = open(path, "r+b", buffering=0)
            except OSError:
                continue
            try:
                pipe.write(_pack(HANDSHAKE,
                                 {"v": 1, "client_id": str(self.client_id)}))
                head = pipe.read(8)
                if len(head) < 8:
                    raise OSError("ردٌّ ناقص")
                _op, size = struct.unpack("<II", head)
                answer = json.loads(pipe.read(size).decode("utf-8") or "{}")
                if answer.get("code"):
                    raise OSError(answer.get("message") or "رُفض المعرّف")
                self._pipe = pipe
                self.last_error = ""
                return True
            except Exception as problem:
                self.last_error = str(problem)
                try:
                    pipe.close()
                except OSError:
                    pass
                return False
        self.last_error = "لا توجد قناة ديسكورد"
        return False

    def _ask(self, activity):
        """يرسل حالةً ويرجع ما ردّ به ديسكورد، أو None عند التعذّر."""
        if self._pipe is None:
            return None
        try:
            self._pipe.write(_pack(FRAME, {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": activity},
                "nonce": "%d" % time.time_ns()}))
            head = self._pipe.read(8)
            if len(head) < 8:
                return None
            _op, size = struct.unpack("<II", head)
            answer = json.loads(self._pipe.read(size).decode("utf-8") or "{}")
            return answer.get("data") or {}
        except Exception as problem:
            self.last_error = str(problem)
            return None

    def _send(self, activity):
        if self._pipe is None:
            return False
        payload = {"cmd": "SET_ACTIVITY",
                   "args": {"pid": os.getpid(), "activity": activity},
                   "nonce": "%d" % time.time_ns()}
        try:
            self._pipe.write(_pack(FRAME, payload))
            head = self._pipe.read(8)
            if len(head) == 8:
                _op, size = struct.unpack("<II", head)
                self._pipe.read(size)
            return True
        except Exception as problem:
            self.last_error = str(problem)
            self._drop()
            return False

    def _drop(self):
        if self._pipe is not None:
            try:
                self._pipe.close()
            except OSError:
                pass
        self._pipe = None

    # -------------------------------------------------------------- الخيط

    def _serve(self):
        wait_until = 0.0
        activity = None
        while not self._stop.is_set():
            try:
                order = self._orders.get(timeout=0.5)
                activity = order
            except queue.Empty:
                pass
            if activity is None:
                continue
            if self._pipe is None:
                if time.time() < wait_until:
                    continue
                if not self._open():
                    wait_until = time.time() + RETRY
                    continue
            self._send(activity)

    def start(self):
        """يبدأ الخيط الخادم. بلا معرّفٍ لا يبدأ شيء."""
        if not self.client_id or self._worker is not None:
            return False
        self._worker = threading.Thread(target=self._serve, daemon=True,
                                        name="discord-presence")
        self._worker.start()
        return True

    # -------------------------------------------------------------- الحالة

    def build(self, title, note="", elapsed=True):
        activity = {"type": 0, "name": APP_NAME, "details": title[:128],
                    "assets": {"large_image": LARGE_IMAGE,
                               "large_text": APP_NAME}}
        if note:
            activity["state"] = note[:128]
        if elapsed:
            activity["timestamps"] = {"start": self.started_at}
        return activity

    def show(self, title, note=""):
        """يعرض حالةً. يُبتلع الطلب بصمت إن لم يبدأ الخيط."""
        if self._worker is None:
            return False
        self._orders.put(self.build(title, note))
        return True

    def close(self):
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None
        self._drop()


def demo():
    """فحص ذاتي: التأطير صحيح، والفشل صامت، والاتّصال يُجرَّب فعلًا."""
    # --- التأطير: أربعة للرمز وأربعة للطول ثم JSON ---
    raw = _pack(HANDSHAKE, {"v": 1, "client_id": "x"})
    op, size = struct.unpack("<II", raw[:8])
    assert op == HANDSHAKE and size == len(raw) - 8, (op, size)
    assert json.loads(raw[8:].decode("utf-8"))["v"] == 1
    print("التأطير: رمز %d · طول %d ✓" % (op, size))

    # --- بلا معرّف: لا يبدأ شيء ولا يُرمى خطأ ---
    quiet = Presence(client_id="")
    assert quiet.start() is False, "بدأ بلا معرّف"
    assert quiet.show("شيء") is False, "أرسل بلا خيط"
    quiet.close()
    print("بلا معرّف: صامتٌ تمامًا ✓")

    # --- الحالة المبنيّة تحمل ما يعرضه ديسكورد ---
    made = Presence(client_id="1").build("يحرّر مشروعًا", "١٢ مقطعًا")
    assert made["details"] == "يحرّر مشروعًا" and made["state"] == "١٢ مقطعًا"
    assert made["timestamps"]["start"] > 0
    # بلا هذا السطر يكتب ديسكورد «Wun Studio» فوق الحالة
    assert made["name"] == APP_NAME, made.get("name")
    assert made["assets"]["large_image"] == LARGE_IMAGE
    long_one = Presence(client_id="1").build("ط" * 400)
    assert len(long_one["details"]) == 128, "لم يُقصّ العنوان الطويل"
    print("الحالة: باسم «%s» وتُقصّ عند ١٢٨ حرفًا ✓" % made["name"])

    # --- الاتّصال الحقيقيّ: معرّفٌ وهميّ يجب أن يُرفض لا أن يُقبل ---
    probe = Presence(client_id="000000000000000000")
    opened = probe._open()
    if probe.last_error == "لا توجد قناة ديسكورد":
        print("ديسكورد غير مشغّل: تُخطّى تجربة الاتّصال")
    else:
        assert not opened, "قُبل معرّفٌ وهميّ!"
        assert "Client ID" in probe.last_error or probe.last_error, \
            probe.last_error
        print("الاتّصال: القناة تردّ «%s» ✓" % probe.last_error)
    probe.close()

    # --- ديسكورد يقبل الصورة فعلًا؟ ---
    #
    # اسمٌ لا يطابق المرفوع في البوّابة يُسقط بصمتٍ تامّ: الردّ ناجح والصورة
    # غائبة. فلا يكشفه فحصٌ محلّيّ، ولا بدّ من سؤال ديسكورد نفسه.
    live = Presence()
    if live.client_id and live._open():
        shown = live._ask(live.build("فحص", "فحص"))
        if shown is None:
            print("لم يردّ ديسكورد بالحالة: يُخطّى")
        else:
            assert shown.get("name") == APP_NAME, shown.get("name")
            got = (shown.get("assets") or {}).get("large_image")
            assert got, ("أسقط ديسكورد الصورة: لا صورةَ باسم «%s» في البوّابة"
                         % LARGE_IMAGE)
            print("ديسكورد الحيّ: الاسم «%s» · الصورة مقبولة ✓" % shown["name"])
    else:
        print("ديسكورد غير مشغّل: يُخطّى الفحص الحيّ")
    live.close()

    print("core/presence: كل الفحوص سليمة")


if __name__ == "__main__":
    demo()
