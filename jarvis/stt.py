import queue
import time
from collections import deque

import numpy as np
import sounddevice as sd

from . import config

SAMPLE_RATE = 16000
BLOCK_MS = 30
BLOCK = SAMPLE_RATE * BLOCK_MS // 1000

# Phrases Whisper tends to hallucinate from background noise.
NOISE_TEXTS = {"", "you", "thank you", "thanks for watching", "bye", ".", "uh", "um", "hmm"}


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


class Listener:
    def __init__(self):
        from faster_whisper import WhisperModel

        print(f"Loading speech model '{config.WHISPER_MODEL}' (first run downloads it)...")
        self.model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        self.silence_blocks = int(config.SILENCE_SECONDS * 1000 / BLOCK_MS)
        self.max_blocks = int(config.MAX_UTTERANCE_SECONDS * 1000 / BLOCK_MS)
        self.threshold = config.MIC_THRESHOLD

    def calibrate(self, seconds=1.5):
        if self.threshold:
            return
        print("Calibrating microphone - stay quiet for a moment...")
        audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        self.threshold = max(_rms(audio[:, 0]) * 3.0, 0.008)
        print(f"Mic threshold set to {self.threshold:.4f}")

    def record(self, timeout=None):
        """Block until someone speaks, then return audio up to the trailing silence."""
        blocks = queue.Queue()

        def callback(indata, frames, t, status):
            blocks.put(indata[:, 0].copy())

        preroll = deque(maxlen=10)
        frames, speaking, silent, loud_run = [], False, 0, 0
        start = time.time()
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=BLOCK, callback=callback):
            while True:
                try:
                    block = blocks.get(timeout=0.5)
                except queue.Empty:
                    continue
                loud = _rms(block) > self.threshold
                if not speaking:
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
        audio = np.concatenate(frames)
        return audio if len(audio) >= SAMPLE_RATE * 0.3 else None

    def transcribe(self, audio):
        segments, _ = self.model.transcribe(
            audio, language="en", beam_size=1, vad_filter=True,
            initial_prompt="Jarvis, open Chrome. Set volume to 50. Play music on YouTube.",
        )
        text = " ".join(s.text for s in segments).strip()
        return "" if text.lower().strip(" .!?,") in NOISE_TEXTS else text

    def listen(self, timeout=None):
        audio = self.record(timeout)
        return self.transcribe(audio) if audio is not None else ""
