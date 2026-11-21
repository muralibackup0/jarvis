"""Voice output through Windows SAPI on one dedicated COM thread (so timers can talk safely too).

- Press Esc while Jarvis is talking to interrupt it (config.ESC_INTERRUPTS_SPEECH).
- Long answers are printed in full but only the first part is spoken.
- `is_busy()` lets the microphone ignore Jarvis's own voice.
"""
import ctypes
import queue
import re
import threading
import time

from .. import config

SVSF_ASYNC, SVSF_PURGE = 1, 2
VK_ESCAPE = 0x1B
ECHO_GUARD_SECONDS = 0.5   # ignore the mic briefly after speaking (room echo)


def clean_for_speech(text):
    text = re.sub(r"```.*?```", " (code shown on screen) ", text, flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)          # markdown links
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^\s*[-*\d.]+\s+", "", text, flags=re.M)        # list bullets
    text = re.sub(r"[*#`_>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def shorten(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[:end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + "...") + " The full answer is on screen."


class Speaker:
    def __init__(self, muted=False, on_state=None):
        self.muted = muted
        self.on_state = on_state or (lambda speaking: None)   # GUI hook
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._speaking = False
        self._last_end = 0.0
        self.ready = threading.Event()
        self.voice_name = ""
        threading.Thread(target=self._worker, daemon=True).start()

    # ---------------------------------------------------------------- public
    def say(self, text, wait=True):
        full = str(text or "").strip()
        if not full:
            return
        print(f"Jarvis: {full}")
        if self.muted:
            return
        spoken = shorten(clean_for_speech(full), config.MAX_SPOKEN_CHARS)
        if not spoken:
            return
        done = threading.Event()
        self._queue.put((spoken, done))
        if wait:
            done.wait()

    def stop(self):
        """Interrupt the current sentence and drop anything queued."""
        self._stop.set()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()[1].set()
            except queue.Empty:
                break

    def is_busy(self):
        return self._speaking or time.time() - self._last_end < ECHO_GUARD_SECONDS

    # ---------------------------------------------------------------- worker
    def _worker(self):
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        voice.Rate = max(-10, min(10, int(config.TTS_RATE)))
        voice.Volume = max(0, min(100, int(config.TTS_VOLUME)))
        voices = voice.GetVoices()
        for i in range(voices.Count):
            if config.VOICE_HINT.lower() in voices.Item(i).GetDescription().lower():
                voice.Voice = voices.Item(i)
                break
        self.voice_name = voice.Voice.GetDescription()
        self.ready.set()
        user32 = ctypes.windll.user32
        while True:
            text, done = self._queue.get()
            self._stop.clear()
            self._speaking = True
            self.on_state(True)
            try:
                voice.Speak(text, SVSF_ASYNC)
                while not voice.WaitUntilDone(80):
                    esc = config.ESC_INTERRUPTS_SPEECH and user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000
                    if self._stop.is_set() or esc:
                        voice.Speak("", SVSF_ASYNC | SVSF_PURGE)
                        print("  (interrupted)")
                        break
            except Exception as e:
                print(f"[tts error] {e}")
            self._speaking = False
            self._last_end = time.time()
            self.on_state(False)
            done.set()
