"""Open and close applications, folders and websites."""
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

import psutil

from ..core.registry import context, tool
from .common import clean_name, known_folder

SYSTEM_APPS = {
    "notepad": "notepad", "calculator": "calc", "calc": "calc", "paint": "mspaint",
    "command prompt": "cmd", "cmd": "cmd", "terminal": "wt", "windows terminal": "wt",
    "powershell": "powershell", "file explorer": "explorer", "explorer": "explorer",
    "files": "explorer", "task manager": "taskmgr", "control panel": "control",
    "registry editor": "regedit", "snipping tool": "snippingtool",
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "firefox": "firefox", "brave": "brave", "vs code": "code", "vscode": "code",
    "visual studio code": "code", "code": "code", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "outlook": "outlook",
}

URI_APPS = {
    "settings": "ms-settings:", "wifi settings": "ms-settings:network-wifi", "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth", "bluetooth settings": "ms-settings:bluetooth",
    "display settings": "ms-settings:display", "sound settings": "ms-settings:sound",
    "battery settings": "ms-settings:batterysaver", "windows update": "ms-settings:windowsupdate",
    "camera": "microsoft.windows.camera:", "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:", "clock": "ms-clock:", "alarms": "ms-clock:",
    "photos": "ms-photos:", "calendar": "outlookcal:", "recycle bin": "shell:RecycleBinFolder",
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
    "claude": "https://claude.ai", "chatgpt": "https://chatgpt.com",
    "hack the box": "https://www.hackthebox.com", "tryhackme": "https://tryhackme.com",
    "portswigger": "https://portswigger.net/web-security", "exploit db": "https://www.exploit-db.com",
}

PROCESS_NAMES = {
    "chrome": "chrome", "google chrome": "chrome", "edge": "msedge", "microsoft edge": "msedge",
    "vs code": "code", "vscode": "code", "visual studio code": "code", "word": "winword",
    "excel": "excel", "powerpoint": "powerpnt", "calculator": "CalculatorApp",
    "task manager": "Taskmgr", "paint": "mspaint", "terminal": "WindowsTerminal",
    "command prompt": "cmd", "spotify": "Spotify", "whatsapp": "WhatsApp", "teams": "ms-teams",
    "settings": "SystemSettings", "photos": "Photos", "burp": "BurpSuiteCommunity",
    "burp suite": "BurpSuiteCommunity", "wireshark": "Wireshark",
}
PROTECTED_PROCESSES = {"explorer", "svchost", "csrss", "winlogon", "lsass", "python", "pythonw",
                       "services", "smss", "wininit", "dwm", "system", "ollama", "ollama app"}


def _exe_path(exe):
    found = shutil.which(exe)
    if found:
        return found
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}.exe") as k:
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


def match_start_app(name):
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


def _log_usage(name):
    mem = context.get("memory")
    if mem:
        mem.log_app(name)


@tool("Open an application, a folder (downloads, documents, desktop...) or a well-known website by name.",
      name=("string", "App, folder or site name, e.g. 'chrome', 'downloads', 'spotify', 'youtube'"))
def open_app(name):
    n = clean_name(name)
    if not n:
        return "Which app should I open?"
    folder = known_folder(n)
    if folder:
        os.startfile(folder)
        return f"Opening your {n} folder."
    if n in URI_APPS:
        os.startfile(URI_APPS[n])
        _log_usage(n)
        return f"Opening {n}."
    if n in SYSTEM_APPS:
        path = _exe_path(SYSTEM_APPS[n])
        if path:
            subprocess.Popen([path], creationflags=subprocess.DETACHED_PROCESS)
            _log_usage(n)
            return f"Opening {n}."
    match = match_start_app(n)
    if match:
        subprocess.Popen(["explorer", f"shell:AppsFolder\\{start_apps()[match]}"])
        _log_usage(match)
        return f"Opening {match}."
    if n in WEBSITES:
        webbrowser.open(WEBSITES[n])
        _log_usage(n)
        return f"Opening {n}."
    if re.fullmatch(r"[\w-]+(\.[\w-]+)+(/\S*)?", n):
        webbrowser.open("https://" + n)
        return f"Opening {n}."
    return f"I couldn't find an app called {name}."


@tool("Close a running application by name. Apps get a normal close request first so they can ask to save.",
      name=("string", "App name, e.g. 'chrome', 'notepad', 'spotify'"))
def close_app(name):
    n = clean_name(name)
    target = PROCESS_NAMES.get(n, n).lower().removesuffix(".exe")
    if target in PROTECTED_PROCESSES:
        return f"I won't close {name}, it's needed by the system."
    names = {p.info["name"] for p in psutil.process_iter(["name"]) if p.info["name"]}
    stems = {x.lower().removesuffix(".exe"): x for x in names}
    if target not in stems:
        close = difflib.get_close_matches(target, list(stems), n=1, cutoff=0.8)
        if not close or close[0] in PROTECTED_PROCESSES:
            return f"{name} doesn't seem to be running."
        target = close[0]
    exe = stems[target]
    subprocess.run(["taskkill", "/im", exe], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(1.5)
    if any(p.info["name"] == exe for p in psutil.process_iter(["name"])):
        subprocess.run(["taskkill", "/im", exe, "/f"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(0.5)
        if any(p.info["name"] == exe for p in psutil.process_iter(["name"])):
            return f"I tried, but {name} is still running."
    return f"Closed {name}."


@tool("List the user's most frequently used apps.")
def frequent_apps():
    mem = context.get("memory")
    apps = mem.top_apps(8) if mem else []
    return "Your most used apps are " + ", ".join(apps) + "." if apps else "I haven't tracked any app usage yet."
