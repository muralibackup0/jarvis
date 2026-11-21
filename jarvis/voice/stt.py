"""Microphone listening + Whisper speech recognition, fully offline.

Noise handling: the speech threshold is calibrated at startup and then follows the room's
background level. Audio is ignored while Jarvis is speaking so it never answers itself.
"""
import queue
import time
from collections import deque

import numpy as np

from .. import config

SAMPLE_RATE = 16000
BLOCK_MS = 30
BLOCK = SAMPLE_RATE * BLOCK_MS // 1000

# Phrases Whisper tends to hallucinate from background noise.
NOISE_TEXTS = {"", "you", "thank you", "thanks for watching", "thank you for watching", "bye", ".",
               "uh", "um", "hmm", "oh", "so", "okay", "the", "i", "subtitles by the amara.org community"}


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


class Listener:
    def __init__(self, is_busy=lambda: False, on_level=None):
        from faster_whisper import WhisperModel

        print(f"Loading speech model '{config.WHISPER_MODEL}' (first run downloads it)...")
        self.model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        self.silence_blocks = int(config.SILENCE_SECONDS * 1000 / BLOCK_MS)
        self.max_blocks = int(config.MAX_UTTERANCE_SECONDS * 1000 / BLOCK_MS)
        self.base_threshold = config.MIC_THRESHOLD
        self.ambient = None
        self.is_busy = is_busy            # True while Jarvis is talking
        self.on_level = on_level or (lambda level, speaking: None)   # GUI waveform hook
        self.stopped = False

    @property
    def threshold(self):
        dynamic = (self.ambient or 0) * 3.0
        return max(self.base_threshold or 0.008, dynamic)

    def calibrate(self, seconds=1.5):
        import sounddevice as sd
        if config.MIC_THRESHOLD:
            return
        print("Calibrating microphone - stay quiet for a moment...")
        audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        self.ambient = _rms(audio[:, 0])
        self.base_threshold = max(self.ambient * 3.0, 0.008)
        print(f"Mic threshold set to {self.base_threshold:.4f}")

    def record(self, timeout=None):
        """Block until someone speaks, then return audio up to the trailing silence (or None)."""
        import sounddevice as sd
        blocks = queue.Queue()

        def callback(indata, frames, t, status):
            blocks.put(indata[:, 0].copy())

        preroll = deque(maxlen=10)
        frames, speaking, silent, loud_run = [], False, 0, 0
        start = time.time()
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=BLOCK, callback=callback):
            while not self.stopped:
                try:
                    block = blocks.get(timeout=0.5)
                except queue.Empty:
                    continue
                if self.is_busy():
                    frames, speaking, silent, loud_run = [], False, 0, 0
                    preroll.clear()
                    start = time.time()
                    continue
                level = _rms(block)
                loud = level > self.threshold
                self.on_level(level, speaking)
                if not speaking:
                    if not loud:  # track background noise so the threshold adapts
                        self.ambient = level if self.ambient is None else 0.995 * self.ambient + 0.005 * level
                    preroll.append(block)
                    loud_run = loud_run + 1 if loud else 0
                    if loud_run >= 2:  # ignore single clicks
                        speaking = True
                        frames.extend(preroll)
                    elif timeout and time.time() - start > timeout:
                        return None
                else:
                    frames.append(block)
                    silent = 0 if loud else silent + 1
                    if silent >= self.silence_blocks or len(frames) >= self.max_blocks:
                        break
        if not frames:
            return None
        audio = np.concatenate(frames)
        return audio if len(audio) >= SAMPLE_RATE * 0.3 else None

    def transcribe(self, audio):
        try:
            segments, _ = self.model.transcribe(
                audio, language="en", beam_size=1, vad_filter=True,
                initial_prompt="Hey Jarvis, open Chrome. Set volume to 50. Play music on YouTube.",
            )
            segments = [s for s in segments if s.no_speech_prob < 0.6]
        except Exception as e:
            print(f"[speech recognition error] {e}")
            return ""
        text = " ".join(s.text for s in segments).strip()
        return "" if text.lower().strip(" .!?,") in NOISE_TEXTS else text

    def listen(self, timeout=None):
        audio = self.record(timeout)
        return self.transcribe(audio) if audio is not None else ""
