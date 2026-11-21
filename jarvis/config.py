"""Settings. Override any of these in jarvis_config.json (see jarvis_config.example.json)
or with JARVIS_* environment variables. Secrets (API keys) are read from the environment only."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"          # memory database + logs (git-ignored)
LOG_DIR = DATA_DIR / "logs"

# ---- identity
USER_NAME = ""                    # e.g. "Murali" - used in the AI's prompt
ADDRESS = "sir"                   # how Jarvis addresses you ("" to disable)

# ---- wake word & listening
# Name variants Whisper commonly produces when you say "Jarvis". "Hey Jarvis" also works.
WAKE_WORDS = ["jarvis", "jervis", "javis", "jarvas", "charvis", "travis", "jarvish"]
FOLLOWUP_SECONDS = 8              # follow-ups without the wake word after a reply
SILENCE_SECONDS = 0.8             # silence that ends an utterance
MAX_UTTERANCE_SECONDS = 15
MIC_THRESHOLD = None              # fixed RMS threshold (e.g. 0.02); None = auto-calibrate
WHISPER_MODEL = "base.en"         # tiny.en (fast) / base.en / small.en (accurate)

# ---- voice output (Windows SAPI)
VOICE_HINT = "david"              # part of an installed voice name: david (male), zira, mark...
TTS_RATE = 1                      # -10 .. 10
TTS_VOLUME = 100                  # 0 .. 100
MAX_SPOKEN_CHARS = 450            # longer answers are printed in full, spoken in short
ESC_INTERRUPTS_SPEECH = True      # press Esc while Jarvis talks to stop it

# ---- AI brain
AI_BACKEND = "auto"               # auto | ollama | openai | none
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"       # any tool-capable model: qwen2.5:1.5b (low RAM), qwen2.5:7b, llama3.1:8b
OLLAMA_NUM_CTX = 6144             # context window; lower uses less RAM
OPENAI_BASE_URL = "https://api.openai.com/v1"   # any OpenAI-compatible server works
OPENAI_MODEL = "gpt-4o-mini"
HISTORY_TURNS = 10                # past exchanges sent to the AI for context

# ---- safety
# The AI may only call registered tools. Raw PowerShell is off unless you enable it,
# and even then every command is read out and needs a spoken "yes".
ALLOW_SHELL_COMMANDS = False

EXIT_PHRASES = ["goodbye", "bye", "exit", "quit", "stop listening", "go offline", "shut yourself down"]

# ---- overrides -------------------------------------------------------------
_SECRET_KEYS = {"OPENAI_API_KEY"}


def _coerce(value, current):
    if isinstance(current, bool):
        return str(value).lower() in ("1", "true", "yes", "on")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if isinstance(current, float) or (current is None and str(value).replace(".", "", 1).isdigit()):
        return float(value)
    if isinstance(current, list):
        return value if isinstance(value, list) else [v.strip() for v in str(value).split(",")]
    return value


def _load_overrides():
    g = globals()
    cfg_file = ROOT / "jarvis_config.json"
    if cfg_file.exists():
        for k, v in json.loads(cfg_file.read_text(encoding="utf-8")).items():
            k = k.upper()
            if k in _SECRET_KEYS:
                print(f"[config] ignoring {k} in jarvis_config.json - set it as an environment variable instead")
            elif k in g and not k.startswith("_"):
                g[k] = _coerce(v, g[k])
    for k in list(g):
        env = os.environ.get(f"JARVIS_{k}")
        if env is not None and k.isupper():
            g[k] = _coerce(env, g[k])


_load_overrides()
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
