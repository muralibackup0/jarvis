"""Small helpers shared by the automation modules."""
import os
import re
import winreg
from pathlib import Path

HOME = Path.home()
FOLDER_NAMES = ("desktop", "documents", "downloads", "pictures", "music", "videos")
_SHELL_KEYS = {"desktop": "Desktop", "documents": "Personal", "pictures": "My Pictures",
               "music": "My Music", "videos": "My Video",
               "downloads": "{374DE290-123F-4565-9164-39C4925E467B}"}


def known_folder(name):
    """Resolve 'downloads', 'my documents', 'desktop' (incl. OneDrive-redirected) to a Path."""
    name = re.sub(r"^(my|the)\s+", "", (name or "").lower().strip()).removesuffix(" folder").strip()
    if name in ("home", "user", "profile", "user folder"):
        return HOME
    if name in ("document",):
        name = "documents"
    if name in ("download",):
        name = "downloads"
    if name not in FOLDER_NAMES:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            p = Path(os.path.expandvars(winreg.QueryValueEx(k, _SHELL_KEYS[name])[0]))
            if p.exists():
                return p
    except OSError:
        pass
    p = HOME / name.capitalize()
    return p if p.exists() else None


def clean_name(name):
    name = (name or "").lower().strip(" .!?")
    name = re.sub(r"^(the|my|a|an)\s+", "", name)
    return re.sub(r"\s+(app|application|program|software|folder|window|browser)$", "", name).strip()


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
