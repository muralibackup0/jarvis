"""Checks that everything Jarvis needs is installed and explains how to fix what isn't."""
import importlib.util
import sys

from .. import config

PACKAGES = [  # (import name, pip name, what it's for, needed for voice mode only)
    ("faster_whisper", "faster-whisper", "speech recognition", True),
    ("sounddevice", "sounddevice", "microphone input", True),
    ("numpy", "numpy", "audio processing", True),
    ("comtypes", "comtypes", "Jarvis's voice", False),
    ("psutil", "psutil", "battery, CPU and app control", False),
    ("requests", "requests", "AI brain and web access", False),
    ("pyautogui", "pyautogui", "keyboard and window control", False),
    ("PIL", "pillow", "screenshots", False),
    ("pyperclip", "pyperclip", "typing and clipboard", False),
    ("screen_brightness_control", "screen-brightness-control", "brightness control", False),
    ("send2trash", "send2trash", "safe deletion to the Recycle Bin", False),
]

FIX = r".venv\Scripts\python.exe -m pip install -r requirements.txt"


def missing_packages(voice=True):
    return [(pip, why) for mod, pip, why, voice_only in PACKAGES
            if (voice or not voice_only) and importlib.util.find_spec(mod) is None]


def check_microphone():
    try:
        import sounddevice as sd
        dev = sd.query_devices(kind="input")
        return True, dev["name"]
    except Exception as e:
        return False, f"No microphone found ({e}). Plug one in or enable it in Windows Sound settings."


def report(ai_engine=None, voice=True):
    """Print a full health check. Returns True when the essentials are OK."""
    ok_all = True
    print("\nJARVIS SYSTEM CHECK")
    print(f"  {'OK ' if sys.version_info >= (3, 10) else 'BAD'} Python {sys.version.split()[0]}")
    missing = missing_packages(voice)
    for mod, pip, why, voice_only in PACKAGES:
        if voice_only and not voice:
            continue
        bad = any(p == pip for p, _ in missing)
        print(f"  {'BAD' if bad else 'OK '} {pip:<27} {why}")
    if missing:
        ok_all = False
        print(f"      Fix: {FIX}")
    if voice:
        ok, msg = check_microphone()
        print(f"  {'OK ' if ok else 'BAD'} microphone: {msg}")
        ok_all &= ok
    try:
        import psutil
        free = psutil.virtual_memory().available / 1e9
        need = 1.5 if "1.5b" in config.OLLAMA_MODEL else 3.0 if "3b" in config.OLLAMA_MODEL else 6.0
        warn = free < need
        print(f"  {'WARN' if warn else 'OK '} free RAM: {free:.1f} GB (model {config.OLLAMA_MODEL} wants ~{need:g} GB)")
        if warn:
            print("      AI answers will be slow. Close some apps, or set OLLAMA_MODEL to qwen2.5:1.5b.")
    except ImportError:
        pass
    if ai_engine is not None:
        ok = ai_engine.available(force=True)
        print(f"  {'OK ' if ok else 'WARN'} AI brain: {ai_engine.status_text}")
        if not ok:
            print("      Simple commands still work. For the AI brain run install.ps1, or:\n"
                  f"      winget install Ollama.Ollama   then   ollama pull {config.OLLAMA_MODEL}")
    print(f"  OK  shell commands for the AI: {'enabled (always confirmed)' if config.ALLOW_SHELL_COMMANDS else 'disabled'}")
    print(f"  OK  data folder: {config.DATA_DIR}\n")
    return ok_all
