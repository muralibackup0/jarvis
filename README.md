# Jarvis — local voice assistant for Windows

Everything runs on your laptop: speech recognition (faster-whisper), voice (Windows SAPI),
and the AI brain (Ollama). No cloud API keys.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Local AI brain (needed for free-form / multi-step requests)
winget install Ollama.Ollama
ollama pull qwen2.5:3b
```

## Run

```powershell
.\jarvis.bat                # say "Jarvis, open Chrome"
.\jarvis.bat --no-wake      # no wake word needed
.\jarvis.bat --text         # type instead of speaking
.\jarvis.bat --model llama3.2:3b
```

After Jarvis answers you have 8 seconds to give a follow-up without saying "Jarvis".
Say "goodbye" to stop.

## How it works

1. **Fast path** ([jarvis/intents.py](jarvis/intents.py)) — common commands are matched instantly, no LLM.
2. **Local LLM** ([jarvis/brain.py](jarvis/brain.py)) — everything else goes to Ollama, which picks and
   chains tools ("open chrome and search for flights to Delhi", "how much RAM is Chrome using?").
3. **Tools** ([jarvis/tools.py](jarvis/tools.py)) — the actual actions. Add one with `@tool(...)` and the LLM
   can use it immediately.

Shutdown, restart, sleep and arbitrary PowerShell commands always ask for a spoken "yes" first.

## Things you can say

| Area | Examples |
|---|---|
| Apps | open Chrome / Spotify / VS Code / settings, close Notepad |
| Folders & files | open downloads, find file resume, open file report.pdf |
| Web | search for best laptops, play Believer on YouTube, open github.com |
| Sound & screen | volume 40, volume up, mute, brightness 70, dim the screen |
| Media | pause, next song, previous track |
| Windows & keys | minimize all, switch window, snap left, close window, type hello, press ctrl+s, scroll down, take a screenshot |
| System | battery, system status, lock the screen, shut down the computer, cancel shutdown |
| Productivity | take a note call mom, read my notes, set a timer for 10 minutes, what's on my clipboard |
| Anything else | questions, multi-step tasks, PowerShell tasks — handled by the local LLM |

## Tuning (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `JARVIS_MODEL` | `qwen2.5:3b` | Ollama model (`qwen2.5:7b` is smarter but slower) |
| `JARVIS_WHISPER` | `base.en` | `tiny.en` faster, `small.en` more accurate |
| `JARVIS_MIC_THRESHOLD` | auto | Set e.g. `0.02` if it triggers on background noise |
| `JARVIS_VOICE` | `david` | Part of an installed SAPI voice name (e.g. `zira`) |
