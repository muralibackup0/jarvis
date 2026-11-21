"""Find, open, create and manage files and folders.

Destructive actions (move, rename, delete, empty recycle bin) are marked dangerous so Jarvis
asks first, and deletion always goes to the Recycle Bin so it can be undone.
"""
import ctypes
import datetime
import os
import re
import time
from pathlib import Path

from ..core.registry import tool
from .common import FOLDER_NAMES, HOME, human_size, known_folder

SKIP_DIRS = {"node_modules", "__pycache__", "venv", ".venv", ".git", "AppData", "$RECYCLE.BIN"}

CATEGORY_EXTS = {
    "pdf": {".pdf"}, "document": {".docx", ".doc", ".pdf", ".txt", ".odt", ".rtf"},
    "word": {".docx", ".doc"}, "excel": {".xlsx", ".xls", ".csv"}, "spreadsheet": {".xlsx", ".xls", ".csv"},
    "presentation": {".pptx", ".ppt"}, "powerpoint": {".pptx", ".ppt"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"}, "photo": {".jpg", ".jpeg", ".png", ".heic"},
    "picture": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}, "screenshot": {".png"},
    "video": {".mp4", ".mkv", ".avi", ".mov", ".webm"}, "music": {".mp3", ".wav", ".flac", ".m4a", ".aac"},
    "song": {".mp3", ".wav", ".flac", ".m4a"}, "zip": {".zip", ".rar", ".7z"}, "archive": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "installer": {".exe", ".msi"}, "python": {".py"}, "code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rs"},
    "text": {".txt", ".md", ".log"}, "log": {".log", ".txt"},
}


def _walk(folders, seconds=8):
    deadline = time.time() + seconds
    for d in folders:
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if not x.startswith(".") and x not in SKIP_DIRS]
            for f in files:
                yield Path(root) / f
            if time.time() > deadline:
                return


def _folders(folder):
    if folder:
        p = known_folder(folder) or Path(os.path.expandvars(folder))
        return [p] if p.is_dir() else []
    return [p for p in (known_folder(x) for x in FOLDER_NAMES) if p]


def _exts(kind):
    kind = (kind or "").lower().strip().lstrip(".").removesuffix(" file").removesuffix(" files")
    if len(kind) > 3 and kind.endswith("s"):
        kind = kind[:-1]
    if not kind or kind in ("file", "download", "any"):
        return None
    return CATEGORY_EXTS.get(kind) or {"." + kind}


def find_paths(name, limit=5):
    pattern = name.lower().strip()
    out = []
    for p in _walk(_folders("")):
        if pattern in p.name.lower():
            out.append(p)
            if len(out) >= limit:
                break
    return out


def resolve(path_or_name, want_dir=None):
    """Turn a full path, a known folder name or a file name into an existing Path (or None)."""
    s = (path_or_name or "").strip().strip('"')
    if not s:
        return None
    folder = known_folder(s)
    if folder:
        return folder
    p = Path(os.path.expandvars(os.path.expanduser(s)))
    if p.is_absolute() and p.exists():
        return p
    for cand in find_paths(s, limit=20):
        if want_dir is None or cand.is_dir() == want_dir:
            return cand
    return None


@tool("Search for files by name in Desktop, Documents, Downloads, Pictures, Music and Videos.",
      name=("string", "Part of the file name"))
def find_file(name):
    found = find_paths(name)
    if not found:
        return f"I couldn't find any file named {name}."
    return f"Found {len(found)}: " + "; ".join(str(p) for p in found)


@tool("Open a file or folder by full path or by (part of) its name.", name=("string", "Path or file name"))
def open_file(name):
    p = resolve(name)
    if not p:
        return f"I couldn't find {name}."
    os.startfile(p)
    return f"Opening {p.name}."


@tool("Find the most recently modified file of a kind (e.g. pdf, image, video, document, zip) and optionally open it.",
      kind=("string", "Extension or kind: pdf, docx, image, video, document, zip, or 'any'"),
      folder=("string", "downloads, documents, desktop... or empty for all"),
      open_it=("boolean", "Open the file after finding it"))
def latest_file(kind, folder, open_it):
    exts = _exts(kind)
    newest, newest_t = None, 0
    for p in _walk(_folders(folder)):
        if exts and p.suffix.lower() not in exts:
            continue
        try:
            t = p.stat().st_mtime
        except OSError:
            continue
        if t > newest_t:
            newest, newest_t = p, t
    if not newest:
        return f"I couldn't find any {kind or ''} files.".replace("  ", " ")
    when = datetime.datetime.fromtimestamp(newest_t).strftime("%d %B at %I:%M %p")
    if open_it:
        os.startfile(newest)
        return f"Opening {newest.name}, last changed {when}."
    return f"Your latest {kind} is {newest.name} in {newest.parent}, last changed {when}."


@tool("List the largest files in a folder.", folder=("string", "downloads, documents, desktop... or a full path"))
def largest_files(folder):
    dirs = _folders(folder or "downloads")
    if not dirs:
        return f"I couldn't find the folder {folder}."
    sizes = []
    for p in _walk(dirs, seconds=15):
        try:
            sizes.append((p.stat().st_size, p))
        except OSError:
            pass
    top = sorted(sizes, reverse=True)[:5]
    if not top:
        return "That folder is empty."
    return "Largest files: " + "; ".join(f"{p.name} ({human_size(s)})" for s, p in top) + "."


@tool("Create a new folder.", name=("string", "Folder name"),
      location=("string", "desktop, documents, downloads... or a full path"))
def create_folder(name, location):
    safe = re.sub(r'[<>:"/\\|?*]', "", name).strip(" .")
    if not safe:
        return "That isn't a valid folder name."
    base = _folders(location or "desktop")
    if not base:
        return f"I couldn't find the location {location}."
    path = base[0] / safe
    if path.exists():
        return f"A folder called {safe} already exists there."
    path.mkdir(parents=True)
    return f"Created the folder {safe} in {base[0].name}."


@tool("Rename a file or folder.", dangerous=True, path=("string", "Full path or name of the file"),
      new_name=("string", "New name (keep the extension for files)"))
def rename_file(path, new_name):
    src = resolve(path)
    if not src:
        return f"I couldn't find {path}."
    safe = re.sub(r'[<>:"/\\|?*]', "", new_name).strip(" .")
    if src.is_file() and not Path(safe).suffix:
        safe += src.suffix
    dst = src.with_name(safe)
    if dst.exists():
        return f"Something called {safe} already exists there."
    src.rename(dst)
    return f"Renamed {src.name} to {dst.name}."


@tool("Move a file or folder into another folder.", dangerous=True,
      path=("string", "Full path or name of the file"), destination=("string", "Folder: desktop, documents... or full path"))
def move_file(path, destination):
    import shutil
    src = resolve(path)
    if not src:
        return f"I couldn't find {path}."
    dst_dir = _folders(destination)
    if not dst_dir:
        return f"I couldn't find the folder {destination}."
    dst = dst_dir[0] / src.name
    if dst.exists():
        return f"{src.name} already exists in {dst_dir[0].name}."
    shutil.move(str(src), str(dst))
    return f"Moved {src.name} to {dst_dir[0].name}."


@tool("Delete a file or folder by moving it to the Recycle Bin (recoverable).", dangerous=True,
      path=("string", "Full path or name of the file"))
def delete_file(path):
    from send2trash import send2trash
    target = resolve(path)
    if not target:
        return f"I couldn't find {path}."
    if target in [HOME, *(known_folder(x) for x in FOLDER_NAMES)]:
        return "I won't delete one of your main folders."
    send2trash(str(target))
    return f"Moved {target.name} to the Recycle Bin."


@tool("Permanently empty the Recycle Bin.", dangerous=True)
def empty_recycle_bin():
    # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND - Jarvis already asked.
    res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)
    if res in (0, -2147418113):  # S_OK, or E_UNEXPECTED when it was already empty
        return "The Recycle Bin is empty."
    return f"Windows couldn't empty the Recycle Bin (error {res})."


NOTES_FILE = (known_folder("documents") or HOME) / "Jarvis Notes.txt"


@tool("Save a note to the user's notes file.", text=("string", "The note"))
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
