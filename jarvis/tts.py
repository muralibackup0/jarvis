import queue
import re
import threading

from . import config


def clean_for_speech(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*#`_>|]", "", text)
    text = re.sub(r"https?://\S+", "a link", text)
    return re.sub(r"\s+", " ", text).strip()


class Speaker:
    """Speaks through Windows SAPI on one dedicated COM thread, so timers can talk safely too."""

    def __init__(self, muted=False):
        self.muted = muted
        self._queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        voice.Rate = config.TTS_RATE
        voices = voice.GetVoices()
        for i in range(voices.Count):
            if config.VOICE_HINT.lower() in voices.Item(i).GetDescription().lower():
                voice.Voice = voices.Item(i)
                break
        while True:
            text, done = self._queue.get()
            try:
                voice.Speak(text)
            except Exception as e:
                print(f"[tts error] {e}")
            done.set()

    def say(self, text, wait=True):
        text = clean_for_speech(str(text))
        if not text:
            return
        print(f"Jarvis: {text}")
        if self.muted:
            return
        done = threading.Event()
        self._queue.put((text, done))
        if wait:
            done.wait()
