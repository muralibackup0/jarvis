import os

# Name variants Whisper commonly produces when you say "Jarvis".
WAKE_WORDS = ("jarvis", "jervis", "javis", "jarvas", "charvis", "travis", "jarvish")

# Local LLM (Ollama). qwen2.5 has reliable tool-calling and runs fine on CPU.
OLLAMA_URL = os.environ.get("JARVIS_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("JARVIS_MODEL", "qwen2.5:3b")

# Speech-to-text. tiny.en = fastest, base.en = good balance, small.en = most accurate.
WHISPER_MODEL = os.environ.get("JARVIS_WHISPER", "base.en")

# After Jarvis answers, keep listening this long without needing the wake word.
FOLLOWUP_SECONDS = 8

# Seconds of silence that end an utterance, and the longest utterance allowed.
SILENCE_SECONDS = 0.8
MAX_UTTERANCE_SECONDS = 15

# Optional fixed mic threshold (RMS, e.g. 0.02). Empty = auto-calibrate at startup.
MIC_THRESHOLD = float(os.environ["JARVIS_MIC_THRESHOLD"]) if os.environ.get("JARVIS_MIC_THRESHOLD") else None

# Voice: SAPI rate is -10..10; VOICE_HINT picks the first installed voice whose name contains it.
TTS_RATE = 1
VOICE_HINT = os.environ.get("JARVIS_VOICE", "david")

EXIT_PHRASES = ("goodbye", "bye", "exit", "quit", "stop listening", "go offline", "shut yourself down")
