"""Long-term memory in SQLite (data/jarvis_memory.db).

Stores facts/preferences, conversation history, app usage, custom voice commands and routines.
Anything that looks like a password, key or token is refused.
"""
import datetime
import json
import re
import sqlite3
import threading

from .. import config

SENSITIVE = re.compile(
    r"\b(password|passwd|passcode|pwd|pin|otp|api[\s_-]?key|secret|token|private key|cvv|"
    r"credit card|card number|bank account|ssn|aadhaar|pan number)\b"
    r"|\bsk-[A-Za-z0-9_-]{8,}|\b[A-Za-z0-9+/_-]{32,}\b|\b\d{12,19}\b", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT UNIQUE, category TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, role TEXT, content TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS app_usage (name TEXT PRIMARY KEY, count INTEGER, last_used TEXT);
CREATE TABLE IF NOT EXISTS custom_commands (phrase TEXT PRIMARY KEY, command TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS routines (name TEXT PRIMARY KEY, steps TEXT, created TEXT);
"""


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _key(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']", " ", text.lower())).strip()


class SensitiveDataError(ValueError):
    pass


class Memory:
    def __init__(self, path=None):
        self.path = path or config.DATA_DIR / "jarvis_memory.db"
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def _q(self, sql, args=(), commit=False):
        with self._lock:
            cur = self._db.execute(sql, args)
            if commit:
                self._db.commit()
            return cur.fetchall()

    @staticmethod
    def check_safe(*texts):
        for t in texts:
            if t and SENSITIVE.search(t):
                raise SensitiveDataError("I don't store passwords, keys or other sensitive details.")

    # ---------- facts & preferences
    def remember(self, text, category="fact"):
        text = text.strip().rstrip(".")
        self.check_safe(text)
        self._q("INSERT OR REPLACE INTO facts (text, category, created) VALUES (?, ?, ?)",
                (text, category, _now()), commit=True)

    def facts(self, search=""):
        if search:
            return [r[0] for r in self._q("SELECT text FROM facts WHERE text LIKE ? ORDER BY id",
                                          (f"%{search}%",))]
        return [r[0] for r in self._q("SELECT text FROM facts ORDER BY id")]

    def forget(self, search):
        """Delete facts containing `search`. Returns the deleted facts."""
        gone = self.facts(search)
        if gone:
            self._q("DELETE FROM facts WHERE text LIKE ?", (f"%{search}%",), commit=True)
        return gone

    # ---------- conversation history
    def add_history(self, role, content):
        self._q("INSERT INTO history (role, content, ts) VALUES (?, ?, ?)", (role, content[:4000], _now()), commit=True)

    def recent_history(self, turns):
        rows = self._q("SELECT role, content FROM history ORDER BY id DESC LIMIT ?", (turns * 2,))
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def clear_history(self):
        self._q("DELETE FROM history", commit=True)

    # ---------- app usage
    def log_app(self, name):
        self._q("INSERT INTO app_usage (name, count, last_used) VALUES (?, 1, ?) "
                "ON CONFLICT(name) DO UPDATE SET count = count + 1, last_used = excluded.last_used",
                (name.lower(), _now()), commit=True)

    def top_apps(self, n=5):
        return [r[0] for r in self._q("SELECT name FROM app_usage ORDER BY count DESC LIMIT ?", (n,))]

    # ---------- custom voice commands
    def add_custom_command(self, phrase, command):
        self.check_safe(phrase, command)
        self._q("INSERT OR REPLACE INTO custom_commands VALUES (?, ?, ?)", (_key(phrase), command.strip(), _now()), commit=True)

    def custom_command(self, phrase):
        rows = self._q("SELECT command FROM custom_commands WHERE phrase = ?", (_key(phrase),))
        return rows[0][0] if rows else None

    def custom_commands(self):
        return self._q("SELECT phrase, command FROM custom_commands ORDER BY phrase")

    def delete_custom_command(self, phrase):
        found = self._q("SELECT 1 FROM custom_commands WHERE phrase = ?", (_key(phrase),))
        self._q("DELETE FROM custom_commands WHERE phrase = ?", (_key(phrase),), commit=True)
        return bool(found)

    # ---------- routines
    def save_routine(self, name, steps):
        self.check_safe(name, *steps)
        self._q("INSERT OR REPLACE INTO routines VALUES (?, ?, ?)", (_key(name), json.dumps(steps), _now()), commit=True)

    def routine(self, name):
        rows = self._q("SELECT steps FROM routines WHERE name = ?", (_key(name).removesuffix(" routine"),))
        return json.loads(rows[0][0]) if rows else None

    def routines(self):
        return [(n, json.loads(s)) for n, s in self._q("SELECT name, steps FROM routines ORDER BY name")]

    def delete_routine(self, name):
        name = _key(name).removesuffix(" routine")
        found = self._q("SELECT 1 FROM routines WHERE name = ?", (name,))
        self._q("DELETE FROM routines WHERE name = ?", (name,), commit=True)
        return bool(found)

    # ---------- summary for the AI prompt
    def prompt_context(self):
        parts = []
        facts = self.facts()[-25:]
        if facts:
            parts.append("Things you remember about the user: " + "; ".join(facts) + ".")
        apps = self.top_apps()
        if apps:
            parts.append("Their most used apps: " + ", ".join(apps) + ".")
        routines = [n for n, _ in self.routines()]
        if routines:
            parts.append("Saved routines: " + ", ".join(routines) + ".")
        return "\n".join(parts)
