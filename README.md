# J.A.R.V.I.S. — local AI assistant for Windows

A voice assistant that runs on your laptop: offline speech recognition (Whisper), a local AI brain
(Ollama) that plans and chains actions, long-term memory (SQLite), Windows control, web search and
reading, and a cybersecurity mode. No cloud account needed; OpenAI is optional.

## Install

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1            # 16 GB+ RAM with room to spare
powershell -ExecutionPolicy Bypass -File install.ps1 -Model qwen2.5:1.5b   # low free RAM
```

The installer creates `.venv`, installs packages, offers to install Ollama, downloads the AI and
speech models, creates `jarvis_config.json` and runs the system check.

Manual install:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
winget install Ollama.Ollama
ollama pull qwen2.5:3b
```

## Run

| Shell | Command |
|---|---|
| Command Prompt / PowerShell | `jarvis.bat` (or double-click it) |
| Git Bash / WSL / zsh | `./jarvis.sh` |

Options: `--text` (type instead of speak), `--no-wake` (no wake word), `--mute`, `--check`
(system check), `--model qwen2.5:1.5b`, `--backend ollama|openai|none`.

Say **"Hey Jarvis"** (or just "Jarvis") followed by a command. After a reply you have 8 seconds for a
follow-up without the wake word. Press **Esc** to interrupt Jarvis while it's speaking. Say
**"goodbye"** to stop.

## What you can say

Phrasing is flexible: "Open Notepad", "Jarvis, launch my Notepad" and "Can you open Notepad for me?"
all work. Common commands run instantly; everything else goes to the AI brain.

| Area | Examples |
|---|---|
| Apps | open Chrome / Spotify / VS Code / settings, close Notepad, what are my most used apps |
| Windows | minimize all, maximize, snap left, switch window, task view, close window |
| Sound & screen | volume 40, volume up, mute, brightness 70, dim the screen |
| Media | pause, next song, play Believer on YouTube |
| System | battery, system status, what's using my RAM, lock the screen, shut down / restart / sleep (asks first), cancel shutdown |
| Files | find my latest PDF, open my latest download, largest files in Downloads, create a folder called Projects on desktop, find file resume, delete / rename / move a file (asks first, deletes go to Recycle Bin), empty the recycle bin (asks first) |
| Screenshots | take a screenshot, take a screenshot and save it to Desktop |
| Browser | search for X, search Bing for X, search YouTube for X, open github.com, new tab, close tab, reopen tab, refresh |
| Web research (AI) | "search the web for today's cybersecurity news and summarise it", "read the first result" |
| Keyboard | type hello world, press ctrl+s |
| Memory | remember that my favourite browser is Chrome, what do you remember about me, forget Chrome (asks first), clear conversation history |
| Custom commands | when I say movie time, open netflix and set volume to 80 |
| Routines | create a routine called morning: open gmail; what's the weather; battery — then "run my morning routine" |
| Productivity | take a note call mom, read my notes, set a timer for 10 minutes, what's on my clipboard |
| Security mode | switch to cybersecurity mode, look up CVE-2021-44228, analyse the log file access.log, build an nmap service scan for 192.168.1.0/24, draft a VAPT report for these findings…, exit security mode |

## How it works

```
main.py                      voice / text loop, wake word, confirmations, --check
jarvis/
  config.py                  settings (+ jarvis_config.json, JARVIS_* env vars)
  core/
    router.py                custom commands -> routines -> fast intents -> AI; runs every action
    intents.py               instant regex commands + phrase normalisation
    ai_engine.py             Ollama / OpenAI-compatible tool-calling loop, modes, prompts
    registry.py              tool allowlist, schemas, argument validation
    memory.py                SQLite: facts, history, app usage, custom commands, routines
  voice/  stt.py tts.py      Whisper + adaptive noise threshold; SAPI voice with Esc interrupt
  automation/                apps, system, files, web, memory_tools  (all tools live here)
  cybersecurity/security.py  CVE lookup (NVD), log analysis, Nmap builder, reports, mode switch
  utils/  logger.py deps.py  action log, dependency checks
```

Add an ability by writing a function with `@tool(...)` in any `automation` module; the router and
the AI can use it immediately.

## Safety

- The AI can only call registered tools (allowlist). Unknown tools and invalid arguments are rejected.
- Shutdown, restart, sleep, delete/move/rename files, emptying the Recycle Bin, forgetting memories
  and deleting routines all need a spoken **yes**. Silence or anything unclear counts as no.
- Deleted files go to the Recycle Bin. Main folders (Desktop, Documents…) can't be deleted.
- Raw PowerShell for the AI is **off** (`ALLOW_SHELL_COMMANDS`). If enabled, every command is
  read out and must be confirmed.
- Memory refuses passwords, API keys, tokens, card numbers and similar.
- API keys come only from environment variables, never from config files.
- Nmap commands are built, never run. Security help is limited to systems you're authorised to test.
- Every action, refusal and error is logged in `data/logs/jarvis.log`.
- Jarvis only reports success when the tool result confirms it.

## Configuration

Copy `jarvis_config.example.json` to `jarvis_config.json` (the installer does this) and edit:

| Key | Default | Notes |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5:3b` | `qwen2.5:1.5b` for low RAM, `qwen2.5:7b` for smarter |
| `OLLAMA_NUM_CTX` | `6144` | lower = less RAM |
| `AI_BACKEND` | `auto` | `auto` tries Ollama then OpenAI |
| `OPENAI_MODEL` / `OPENAI_BASE_URL` | `gpt-4o-mini` | any OpenAI-compatible server (LM Studio, Groq…) |
| `WHISPER_MODEL` | `base.en` | `tiny.en` faster, `small.en` more accurate |
| `VOICE_HINT` / `TTS_RATE` / `TTS_VOLUME` | `david` / `1` / `100` | male voice by default |
| `ADDRESS` / `USER_NAME` | `sir` / empty | how Jarvis addresses you |
| `MIC_THRESHOLD` | auto | e.g. `0.02` if background noise triggers it |
| `ALLOW_SHELL_COMMANDS` | `false` | let the AI propose PowerShell (always confirmed) |

OpenAI (optional): `setx OPENAI_API_KEY "sk-..."`, then set `AI_BACKEND` to `openai` (or leave
`auto` as a fallback when Ollama is down).

Your data (`data/jarvis_memory.db`, logs) stays on your laptop and is git-ignored.

## Troubleshooting

| Problem | Fix |
|---|---|
| `missing some Python packages` | `.venv\Scripts\python.exe -m pip install -r requirements.txt` |
| "AI brain is offline" | Install Ollama (`winget install Ollama.Ollama`), then `ollama pull qwen2.5:3b`. Jarvis starts the Ollama server itself. |
| AI answers take minutes | Not enough free RAM, so the model is being paged to disk. Close browsers/apps, or use `qwen2.5:1.5b`. `.\jarvis.bat --check` shows free memory. |
| Doesn't hear the wake word | Speak after "Listening...", check the mic in Windows Sound settings, try `WHISPER_MODEL: small.en` |
| Triggers on background noise | Set `MIC_THRESHOLD` to `0.02`–`0.04` |
| Screenshot fails | `pip install pillow` (now in requirements) |
| `./jarvis.bat: @echo: not found` | You're in Git Bash/WSL — use `./jarvis.sh` |
| Brightness doesn't change | External monitors may not support software brightness |
| Something went wrong | See `data/logs/jarvis.log` |
