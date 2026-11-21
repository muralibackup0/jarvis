"""Actions Jarvis can perform. Each tool returns a short sentence that is spoken back.

Add a new ability by writing a function and decorating it with @tool - it becomes
available to the local LLM automatically.
"""
import ctypes
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import webbrowser
import winreg
from pathlib import Path
from urllib.parse import quote_plus

import psutil
import requests

TOOLS = {}
notify = print  # replaced by main with the speaker, so timers can talk


def tool(description, dangerous=False, **params):
    """params: name=(json_type, description). Dangerous tools need a spoken yes first."""
    def deco(fn):
        TOOLS[fn.__name__] = {"fn": fn, "description": description, "params": params, "dangerous": dangerous}
        return fn
    return deco


def schemas():
    return [{
        "type": "function",
        "function": {
            "name": name,
            "description": t["description"],
            "parameters": {
                "type": "object",
                "properties": {p: {"type": ty, "description": d} for p, (ty, d) in t["params"].items()},
                "required": list(t["params"]),
            },
        },
    } for name, t in TOOLS.items()]


# ---------------------------------------------------------------- helpers

user32 = ctypes.windll.user32
HOME = Path.home()


def _press_vk(vk, times=1):
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.01)


def _known_folder(name):
    name = name.lower().strip()
    if name in ("home", "user", "profile"):
        return HOME
    for base in (HOME, HOME / "OneDrive"):
        p = base / name.capitalize()
        if p.exists():
            return p
    return None


def _clean_name(name):
    name = name.lower().strip(" .!?")
    name = re.sub(r"^(the|my|a)\s+", "", name)
    return re.sub(r"\s+(app|application|program|folder|window|browser)$", "", name).strip()


def _exe_path(exe):
    found = shutil.which(exe)
    if found:
        return found
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}.exe"
            with winreg.OpenKey(hive, key) as k:
                return winreg.QueryValue(k, None)
        except OSError:
            pass
    return None


_start_apps = None
_start_apps_lock = threading.Lock()


def start_apps():
    """Installed apps from the Start menu (desktop + Store apps): {lower name: AppID}."""
    global _start_apps
    with _start_apps_lock:
        if _start_apps is None:
            try:
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                    capture_output=True, text=True, timeout=30,
                    creationflags=subprocess.CREATE_NO_WINDOW).stdout
                data = json.loads(out) if out.strip() else []
                if isinstance(data, dict):
                    data = [data]
                _start_apps = {a["Name"].lower(): a["AppID"] for a in data if a.get("Name")}
            except Exception as e:
                print(f"[apps] couldn't index Start menu apps: {e}")
                _start_apps = {}
        return _start_apps


def _match_start_app(name):
    apps = start_apps()
    if name in apps:
        return name
    starts = [a for a in apps if a.startswith(name)]
    if starts:
        return min(starts, key=len)
    contains = [a for a in apps if re.search(rf"\b{re.escape(name)}\b", a)]
    if contains:
        return min(contains, key=len)
    close = difflib.get_close_matches(name, list(apps), n=1, cutoff=0.75)
    return close[0] if close else None


# ---------------------------------------------------------------- apps & websites

SYSTEM_APPS = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "command prompt": "cmd", "cmd": "cmd", "terminal": "wt", "windows terminal": "wt",
    "powershell": "powershell", "file explorer": "explorer", "explorer": "explorer",
    "files": "explorer", "task manager": "taskmgr", "control panel": "control",
    "registry editor": "regedit", "snipping tool": "snippingtool",
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "brave": "brave", "vs code": "code", "vscode": "code",
    "visual studio code": "code", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "outlook": "outlook",
}

URI_APPS = {
    "settings": "ms-settings:", "wifi settings": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth", "bluetooth settings": "ms-settings:bluetooth",
    "display settings": "ms-settings:display", "sound settings": "ms-settings:sound",
    "camera": "microsoft.windows.camera:", "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:", "clock": "ms-clock:", "alarms": "ms-clock:",
    "photos": "ms-photos:", "calendar": "outlookcal:",
}

WEBSITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "gmail": "https://mail.google.com", "google drive": "https://drive.google.com",
    "maps": "https://maps.google.com", "google maps": "https://maps.google.com",
    "github": "https://github.com", "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
    "twitter": "https://x.com", "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com", "amazon": "https://www.amazon.in",
    "wikipedia": "https://www.wikipedia.org", "stack overflow": "https://stackoverflow.com",
    "claude": "https://claude.ai",
}

PROCESS_NAMES = {
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "vs code": "code", "vscode": "code", "visual studio code": "code", "word": "winword",
    "excel": "excel", "powerpoint": "powerpnt", "calculator": "CalculatorApp",
    "task manager": "Taskmgr", "paint": "mspaint", "terminal": "WindowsTerminal",
    "command prompt": "cmd", "spotify": "Spotify", "whatsapp": "WhatsApp", "teams": "ms-teams",
    "settings": "SystemSettings", "photos": "Photos",
}
PROTECTED_PROCESSES = {"explorer", "svchost", "csrss", "winlogon", "lsass", "python", "pythonw",
                       "services", "smss", "wininit", "dwm", "system"}


@tool("Open an application, folder (downloads, documents, desktop...) or well-known website by name.",
      name=("string", "App, folder or site name, e.g. 'chrome', 'downloads', 'spotify', 'youtube'"))
def open_app(name):
    n = _clean_name(name)
    folder = _known_folder(n)
    if folder:
        os.startfile(folder)
        return f"Opening your {n} folder."
    if n in URI_APPS:
        os.startfile(URI_APPS[n])
        return f"Opening {n}."
    if n in SYSTEM_APPS:
        path = _exe_path(SYSTEM_APPS[n])
        if path:
            subprocess.Popen([path], creationflags=subprocess.DETACHED_PROCESS)
            return f"Opening {n}."
    match = _match_start_app(n)
    if match:
        subprocess.Popen(["explorer", f"shell:AppsFolder\\{start_apps()[match]}"])
        return f"Opening {match}."
    if n in WEBSITES:
        webbrowser.open(WEBSITES[n])
        return f"Opening {n}."
    if re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", n):
        return open_website(n)
    return f"I couldn't find an app called {name}."


@tool("Close a running application by name. Apps get a normal close request so they can ask to save.",
      name=("string", "App name, e.g. 'chrome', 'notepad', 'spotify'"))
def close_app(name):
    n = _clean_name(name)
    target = PROCESS_NAMES.get(n, n).lower().removesuffix(".exe")
    if target in PROTECTED_PROCESSES:
        return f"I won't close {name}, it's a system process."
    names = {p.info["name"] for p in psutil.process_iter(["name"]) if p.info["name"]}
    stems = {x.lower().removesuffix(".exe"): x for x in names}
    if target not in stems:
        close = difflib.get_close_matches(target, list(stems), n=1, cutoff=0.8)
        if not close or close[0] in PROTECTED_PROCESSES:
            return f"{name} doesn't seem to be running."
        target = close[0]
    subprocess.run(["taskkill", "/im", stems[target]], capture_output=True,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(1.5)
    still = any(p.info["name"] == stems[target] for p in psutil.process_iter(["name"]))
    if still:
        subprocess.run(["taskkill", "/im", stems[target], "/f"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    return f"Closed {name}."


@tool("Open a website or URL in the default browser.", url=("string", "URL or domain, e.g. 'github.com'"))
def open_website(url):
    if not re.match(r"https?://", url):
        url = "https://" + url.strip()
    webbrowser.open(url)
    return "Opening the website."


@tool("Search Google for something and open the results in the browser.", query=("string", "Search terms"))
def search_web(query):
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
    return f"Here are the results for {query}."


@tool("Play a song or video on YouTube.", query=("string", "Song, video or artist to play"))
def play_youtube(query):
    try:
        html = requests.get(f"https://www.youtube.com/results?search_query={quote_plus(query)}",
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=8).text
        vid = re.search(r'"videoId":"([\w-]{11})"', html)
        if vid:
            webbrowser.open(f"https://www.youtube.com/watch?v={vid.group(1)}")
            return f"Playing {query} on YouTube."
    except requests.RequestException:
        pass
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
    return f"Here's what YouTube has for {query}."


# ---------------------------------------------------------------- sound, screen, media

VK_MUTE, VK_VOL_DOWN, VK_VOL_UP = 0xAD, 0xAE, 0xAF
VK_NEXT, VK_PREV, VK_PLAY_PAUSE = 0xB0, 0xB1, 0xB3


@tool("Set system volume to an exact percentage.", level=("integer", "0 to 100"))
def set_volume(level):
    level = max(0, min(100, int(level)))
    _press_vk(VK_VOL_DOWN, 50)
    _press_vk(VK_VOL_UP, round(level / 2))
    return f"Volume set to {level} percent."


@tool("Change volume: 'up', 'down', 'mute' or 'unmute'.", direction=("string", "up, down, mute or unmute"))
def change_volume(direction):
    d = direction.lower()
    if d in ("mute", "unmute"):
        _press_vk(VK_MUTE)
        return "Muted." if d == "mute" else "Unmuted."
    _press_vk(VK_VOL_UP if d == "up" else VK_VOL_DOWN, 5)
    return f"Volume {'up' if d == 'up' else 'down'}."


@tool("Set screen brightness to an exact percentage.", level=("integer", "0 to 100"))
def set_brightness(level):
    import screen_brightness_control as sbc
    level = max(0, min(100, int(level)))
    sbc.set_brightness(level)
    return f"Brightness set to {level} percent."


@tool("Change screen brightness 'up' or 'down'.", direction=("string", "up or down"))
def change_brightness(direction):
    import screen_brightness_control as sbc
    current = sbc.get_brightness()[0]
    new = max(0, min(100, current + (20 if direction.lower() == "up" else -20)))
    sbc.set_brightness(new)
    return f"Brightness is now {new} percent."


@tool("Control media playback: 'play', 'pause', 'next' or 'previous'.", action=("string", "play, pause, next or previous"))
def media_control(action):
    a = action.lower()
    vk = VK_NEXT if a in ("next", "skip") else VK_PREV if a in ("previous", "back") else VK_PLAY_PAUSE
    _press_vk(vk)
    return {VK_NEXT: "Next track.", VK_PREV: "Previous track."}.get(vk, "Done.")


# ---------------------------------------------------------------- keyboard & windows

KEY_ALIASES = {"control": "ctrl", "windows": "win", "window": "win", "escape": "esc",
               "return": "enter", "delete": "del", "spacebar": "space", "page up": "pageup",
               "page down": "pagedown", "option": "alt"}


@tool("Type text at the current cursor position, as if typed on the keyboard.", text=("string", "Text to type"))
def type_text(text):
    import pyautogui
    import pyperclip
    old = pyperclip.paste()
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    pyperclip.copy(old)
    return "Typed it."


@tool("Press a key or keyboard shortcut, e.g. 'enter', 'ctrl+s', 'alt+tab', 'win+e'.",
      keys=("string", "Keys joined with +"))
def press_keys(keys):
    import pyautogui
    parts = [KEY_ALIASES.get(k.strip().lower(), k.strip().lower()) for k in re.split(r"\s*\+\s*|\s+plus\s+", keys)]
    pyautogui.hotkey(*parts)
    return f"Pressed {keys}."


@tool("Manage windows: 'minimize all', 'show desktop', 'switch', 'maximize', 'minimize', 'close', 'snap left', 'snap right'.",
      action=("string", "Window action"))
def window_action(action):
    import pyautogui
    combos = {
        "minimize all": ("win", "d"), "show desktop": ("win", "d"), "switch": ("alt", "tab"),
        "maximize": ("win", "up"), "minimize": ("win", "down"), "close": ("alt", "f4"),
        "snap left": ("win", "left"), "snap right": ("win", "right"),
    }
    combo = combos.get(action.lower())
    if not combo:
        return f"I don't know the window action {action}."
    pyautogui.hotkey(*combo)
    return "Done."


@tool("Scroll the current window 'up' or 'down'.", direction=("string", "up or down"))
def scroll(direction):
    import pyautogui
    pyautogui.scroll(600 if direction.lower() == "up" else -600)
    return "Scrolled."


@tool("Take a screenshot and save it to Pictures/Jarvis.")
def take_screenshot():
    import pyautogui
    folder = (_known_folder("pictures") or HOME) / "Jarvis"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
    pyautogui.screenshot().save(path)
    return "Screenshot saved in your Pictures, Jarvis folder."


@tool("Read the text currently on the clipboard.")
def read_clipboard():
    import pyperclip
    text = pyperclip.paste().strip()
    return f"Your clipboard says: {text[:500]}" if text else "The clipboard is empty."


# ---------------------------------------------------------------- system power

@tool("Lock the computer.")
def lock_screen():
    user32.LockWorkStation()
    return "Locking the computer."


@tool("Put the computer to sleep.", dangerous=True)
def sleep_computer():
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    return "Going to sleep."


@tool("Shut down the computer (in 15 seconds, can be cancelled).", dangerous=True)
def shutdown_computer():
    subprocess.run(["shutdown", "/s", "/t", "15"])
    return "Shutting down in 15 seconds. Say cancel shutdown to stop it."


@tool("Restart the computer (in 15 seconds, can be cancelled).", dangerous=True)
def restart_computer():
    subprocess.run(["shutdown", "/r", "/t", "15"])
    return "Restarting in 15 seconds. Say cancel shutdown to stop it."


@tool("Cancel a pending shutdown or restart.")
def cancel_shutdown():
    subprocess.run(["shutdown", "/a"], capture_output=True)
    return "Shutdown cancelled."


# ---------------------------------------------------------------- information

@tool("Get the current time.")
def get_time():
    return f"It's {datetime.datetime.now():%I:%M %p}.".replace(" 0", " ")


@tool("Get today's date.")
def get_date():
    return f"Today is {datetime.datetime.now():%A, %d %B %Y}."


@tool("Get battery percentage and charging status.")
def battery_status():
    b = psutil.sensors_battery()
    if not b:
        return "I couldn't find a battery."
    state = "charging" if b.power_plugged else "not charging"
    left = ""
    if not b.power_plugged and b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
        left = f", about {b.secsleft // 3600} hours {b.secsleft % 3600 // 60} minutes left"
    return f"Battery is at {round(b.percent)} percent and {state}{left}."


@tool("Get CPU, memory and disk usage.")
def system_status():
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
    return (f"CPU is at {cpu:.0f} percent, memory at {mem:.0f} percent, "
            f"and {disk.free / 1e9:.0f} gigabytes free on the main drive.")


@tool("List the apps using the most memory right now.")
def top_processes():
    usage = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        if p.info["memory_info"] and p.info["name"]:
            n = p.info["name"].removesuffix(".exe")
            usage[n] = usage.get(n, 0) + p.info["memory_info"].rss
    top = sorted(usage.items(), key=lambda x: -x[1])[:5]
    return "Top memory users: " + ", ".join(f"{n} {b / 1e6:.0f} megabytes" for n, b in top) + "."


@tool("Get the current weather. Needs internet.", city=("string", "City name, or empty for current location"))
def get_weather(city):
    try:
        r = requests.get(f"https://wttr.in/{quote_plus(city or '')}?format=%l:+%C,+%t,+humidity+%h", timeout=8)
        return r.text.strip().replace("+", "") if r.ok else "I couldn't get the weather."
    except requests.RequestException:
        return "I couldn't reach the weather service."


# ---------------------------------------------------------------- files & notes

SEARCH_DIRS = ("desktop", "documents", "downloads", "pictures", "music", "videos")


def _find(name, limit=5, seconds=6):
    pattern = name.lower()
    results, deadline = [], time.time() + seconds
    for d in filter(None, (_known_folder(x) for x in SEARCH_DIRS)):
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "__pycache__", "venv", ".venv")]
            for f in files:
                if pattern in f.lower():
                    results.append(Path(root) / f)
                    if len(results) >= limit:
                        return results
            if time.time() > deadline:
                return results
    return results


@tool("Search for files by name in Desktop, Documents, Downloads, Pictures, Music and Videos.",
      name=("string", "Part of the file name"))
def find_file(name):
    found = _find(name)
    if not found:
        return f"I couldn't find any file named {name}."
    return f"Found {len(found)}: " + "; ".join(str(p) for p in found)


@tool("Open a file by full path or by (part of) its name.", name=("string", "Path or file name"))
def open_file(name):
    p = Path(name)
    if not p.exists():
        found = _find(name, limit=1)
        if not found:
            return f"I couldn't find {name}."
        p = found[0]
    os.startfile(p)
    return f"Opening {p.name}."


NOTES_FILE = (_known_folder("documents") or HOME) / "Jarvis Notes.txt"


@tool("Save a note for the user.", text=("string", "The note"))
def take_note(text):
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M}] {text}\n")
    return "Noted."


@tool("Read the user's most recent notes.")
def read_notes():
    if not NOTES_FILE.exists():
        return "You don't have any notes yet."
    lines = NOTES_FILE.read_text(encoding="utf-8").strip().splitlines()[-5:]
    return "Your latest notes: " + ". ".join(re.sub(r"^\[.*?\]\s*", "", l) for l in lines)


@tool("Set a timer or reminder that speaks when done.",
      minutes=("number", "Minutes from now"), label=("string", "What to remind about, or empty"))
def set_timer(minutes, label):
    minutes = float(minutes)
    msg = f"Reminder: {label}." if label else "Your timer is done."
    threading.Timer(minutes * 60, lambda: notify(msg)).start()
    nice = f"{minutes:g} minute{'s' if minutes != 1 else ''}"
    return f"Okay, I'll remind you in {nice}."


@tool("Run a PowerShell command on the computer and return its output. Use only when no other tool fits.",
      dangerous=True, command=("string", "PowerShell command"))
def run_command(command):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True,
                           text=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        out = (r.stdout + r.stderr).strip()
        return out[-1500:] if out else "The command finished with no output."
    except subprocess.TimeoutExpired:
        return "The command took too long and was stopped."
