"""Sound, screen, keyboard, windows, power and system information."""
import ctypes
import datetime
import os
import re
import subprocess
import threading
import time

import psutil
import requests
from urllib.parse import quote_plus

from .. import config
from ..core.registry import context, tool
from .common import HOME, known_folder

user32 = ctypes.windll.user32


def _press_vk(vk, times=1):
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.01)


def _hotkey(*keys):
    import pyautogui
    pyautogui.hotkey(*keys)


# ---------------------------------------------------------------- sound & media

VK_MUTE, VK_VOL_DOWN, VK_VOL_UP = 0xAD, 0xAE, 0xAF
VK_NEXT, VK_PREV, VK_PLAY_PAUSE = 0xB0, 0xB1, 0xB3


@tool("Set system volume to an exact percentage.", level=("integer", "0 to 100"))
def set_volume(level):
    level = max(0, min(100, level))
    _press_vk(VK_VOL_DOWN, 50)
    _press_vk(VK_VOL_UP, round(level / 2))
    return f"Volume set to {level} percent."


@tool("Change the system volume.", direction=("string", "What to do", ["up", "down", "mute", "unmute"]))
def change_volume(direction):
    if direction in ("mute", "unmute"):
        _press_vk(VK_MUTE)
        return "Muted." if direction == "mute" else "Unmuted."
    _press_vk(VK_VOL_UP if direction == "up" else VK_VOL_DOWN, 5)
    return f"Volume {direction}."


@tool("Control media playback in any player or browser.",
      action=("string", "Playback action", ["play", "pause", "next", "previous"]))
def media_control(action):
    vk = {"next": VK_NEXT, "previous": VK_PREV}.get(action, VK_PLAY_PAUSE)
    _press_vk(vk)
    return {"next": "Next track.", "previous": "Previous track."}.get(action, "Done.")


# ---------------------------------------------------------------- screen

@tool("Set screen brightness to an exact percentage.", level=("integer", "0 to 100"))
def set_brightness(level):
    import screen_brightness_control as sbc
    level = max(0, min(100, level))
    sbc.set_brightness(level)
    return f"Brightness set to {level} percent."


@tool("Make the screen brighter or dimmer.", direction=("string", "Direction", ["up", "down"]))
def change_brightness(direction):
    import screen_brightness_control as sbc
    current = sbc.get_brightness()[0]
    new = max(0, min(100, current + (20 if direction == "up" else -20)))
    sbc.set_brightness(new)
    return f"Brightness is now {new} percent."


@tool("Take a screenshot of all screens and save it as a PNG.",
      location=("string", "Where to save it", ["pictures", "desktop", "documents", "downloads"]))
def take_screenshot(location):
    from PIL import ImageGrab
    base = known_folder(location) or HOME
    folder = base / "Jarvis Screenshots" if location == "pictures" else base
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot_{datetime.datetime.now():%Y%m%d_%H%M%S}.png"
    ImageGrab.grab(all_screens=True).save(path)
    if not path.exists():
        return "The screenshot could not be saved."
    where = "your Pictures, Jarvis Screenshots folder" if location == "pictures" else f"your {location}"
    return f"Screenshot saved to {where} as {path.name}."


# ---------------------------------------------------------------- keyboard & windows

KEY_ALIASES = {"control": "ctrl", "windows": "win", "window": "win", "escape": "esc",
               "return": "enter", "delete": "del", "spacebar": "space", "page up": "pageup",
               "page down": "pagedown", "option": "alt", "plus": "+"}


@tool("Type text at the current cursor position, as if typed on the keyboard.", text=("string", "Text to type"))
def type_text(text):
    import pyperclip
    old = pyperclip.paste()
    pyperclip.copy(text)
    _hotkey("ctrl", "v")
    time.sleep(0.3)
    pyperclip.copy(old)
    return "Typed it."


@tool("Press a key or keyboard shortcut, e.g. 'enter', 'ctrl+s', 'alt+tab', 'win+e'.",
      keys=("string", "Keys joined with +"))
def press_keys(keys):
    import pyautogui
    parts = [KEY_ALIASES.get(k.strip().lower(), k.strip().lower())
             for k in re.split(r"\s*\+\s*|\s+plus\s+|\s+and\s+", keys) if k.strip()]
    bad = [p for p in parts if p not in pyautogui.KEYBOARD_KEYS]
    if bad:
        return f"I don't know the key {bad[0]}."
    pyautogui.hotkey(*parts)
    return f"Pressed {keys}."


WINDOW_ACTIONS = {
    "minimize all": ("win", "d"), "show desktop": ("win", "d"), "switch": ("alt", "tab"),
    "maximize": ("win", "up"), "minimize": ("win", "down"), "close": ("alt", "f4"),
    "snap left": ("win", "left"), "snap right": ("win", "right"), "task view": ("win", "tab"),
}


@tool("Manage the active window.", action=("string", "Window action", list(WINDOW_ACTIONS)))
def window_action(action):
    _hotkey(*WINDOW_ACTIONS[action])
    return "Done."


BROWSER_TABS = {"new": ("ctrl", "t"), "close": ("ctrl", "w"), "next": ("ctrl", "tab"),
                "previous": ("ctrl", "shift", "tab"), "reopen": ("ctrl", "shift", "t"),
                "refresh": ("f5",), "back": ("alt", "left"), "forward": ("alt", "right")}


@tool("Manage tabs in the browser window that is in front.", action=("string", "Tab action", list(BROWSER_TABS)))
def browser_tab(action):
    _hotkey(*BROWSER_TABS[action])
    return {"new": "New tab.", "close": "Tab closed.", "reopen": "Reopened the last tab."}.get(action, "Done.")


@tool("Scroll the current window.", direction=("string", "Direction", ["up", "down"]))
def scroll(direction):
    import pyautogui
    pyautogui.scroll(600 if direction == "up" else -600)
    return "Scrolled."


@tool("Read the text currently on the clipboard.")
def read_clipboard():
    import pyperclip
    text = pyperclip.paste().strip()
    return f"Your clipboard says: {text[:1500]}" if text else "The clipboard is empty."


# ---------------------------------------------------------------- power

@tool("Lock the computer.")
def lock_screen():
    user32.LockWorkStation()
    return "Locking the computer."


@tool("Put the computer to sleep.", dangerous=True)
def sleep_computer():
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    return "Going to sleep."


@tool("Shut down the computer in 15 seconds (can be cancelled).", dangerous=True)
def shutdown_computer():
    r = subprocess.run(["shutdown", "/s", "/t", "15"], capture_output=True, text=True)
    return "Shutting down in 15 seconds. Say cancel shutdown to stop it." if r.returncode == 0 else f"Shutdown failed: {r.stderr.strip()}"


@tool("Restart the computer in 15 seconds (can be cancelled).", dangerous=True)
def restart_computer():
    r = subprocess.run(["shutdown", "/r", "/t", "15"], capture_output=True, text=True)
    return "Restarting in 15 seconds. Say cancel shutdown to stop it." if r.returncode == 0 else f"Restart failed: {r.stderr.strip()}"


@tool("Cancel a pending shutdown or restart.")
def cancel_shutdown():
    r = subprocess.run(["shutdown", "/a"], capture_output=True)
    return "Shutdown cancelled." if r.returncode == 0 else "There was no shutdown scheduled."


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
    state = "charging" if b.power_plugged else "on battery"
    left = ""
    if not b.power_plugged and b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN):
        left = f", about {b.secsleft // 3600} hours {b.secsleft % 3600 // 60} minutes left"
    return f"Battery is at {round(b.percent)} percent and {state}{left}."


@tool("Get CPU, memory and disk usage.")
def system_status():
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
    return (f"CPU is at {cpu:.0f} percent, memory at {mem.percent:.0f} percent "
            f"({mem.available / 1e9:.1f} gigabytes free), and {disk.free / 1e9:.0f} gigabytes free on the main drive.")


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


@tool("Set a timer or reminder that speaks when done.",
      minutes=("number", "Minutes from now"), label=("string", "What to remind about, or empty"))
def set_timer(minutes, label):
    if not 0 < minutes <= 24 * 60:
        return "Timers can be from a few seconds up to 24 hours."
    msg = f"Reminder: {label}." if label else "Your timer is done."
    speaker = context.get("speaker")
    t = threading.Timer(minutes * 60, lambda: speaker.say(msg) if speaker else print(msg))
    t.daemon = True
    t.start()
    nice = f"{minutes:g} minute{'s' if minutes != 1 else ''}"
    return f"Okay, I'll remind you in {nice}."


@tool("Run a PowerShell command and return its output. Only when no other tool fits; the user must approve it.",
      dangerous=True, hidden=not config.ALLOW_SHELL_COMMANDS, command=("string", "PowerShell command"))
def run_command(command):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True,
                           text=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW)
        out = (r.stdout + r.stderr).strip()
        status = "succeeded" if r.returncode == 0 else f"failed with exit code {r.returncode}"
        return f"The command {status}. " + (out[-1500:] if out else "No output.")
    except subprocess.TimeoutExpired:
        return "The command took too long and was stopped."
