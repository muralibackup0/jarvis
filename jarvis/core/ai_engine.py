"""The AI brain: a local LLM (Ollama) or any OpenAI-compatible API that plans and calls tools."""
import datetime
import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests

from .. import config
from ..utils.logger import get_logger
from . import registry

log = get_logger("ai")

BASE_PROMPT = """You are J.A.R.V.I.S., the personal AI assistant living on {user}'s Windows laptop.
Personality: calm, warm, quietly witty and very competent, like a loyal British butler who is also a brilliant engineer.{address}

How you work:
- To do anything on the computer, call tools. For multi-step requests call tools one step at a time and use each result.
- Only say something succeeded when a tool result confirms it. If a tool fails or the user declines, say so plainly.
- Answer general knowledge questions directly. Use web_search only for news, current events, prices or other things that change, then read_webpage on the best result if needed, and summarise.
- Never guess file paths; find them with tools. Never ask for, repeat or store passwords, API keys or other secrets.
- If a request is ambiguous, ask one short clarifying question.
- When the user tells you a lasting preference or personal fact, store it with remember.
- Your words are spoken aloud: {length} No markdown, bullet points, emojis or raw URLs.
- Each user message starts with a [Context] line (time, memories). Use it, but never read it out.
{mode}"""

ASSISTANT_MODE = ""
SECURITY_MODE = """
CYBERSECURITY MODE is active. You are also a senior penetration tester and security analyst (OSCP/OSWE level).
- Explain vulnerabilities, OWASP Top 10 issues, CVEs (use lookup_cve), Burp Suite findings and attack chains clearly,
  with impact, root cause and concrete remediation.
- Build Nmap commands with build_nmap_command, analyse logs with analyze_log_file, and write reports with save_report
  (write the full report in the content field, then give a two-sentence spoken summary).
- Only help with systems the user owns or is explicitly authorised to assess. If a request targets third-party systems
  without authorisation, decline and explain why."""

# Requests that need a real action or real data from the laptop - answering these without a tool is a guess.
ACTION_RX = re.compile(
    r"^(?:please\s+)?(?:open|launch|start|close|find|locate|search|look up|check|show|list|set|turn|change|"
    r"create|make|delete|remove|rename|move|take|play|pause|type|press|mute|unmute|lock|run|read|analy[sz]e|"
    r"get|tell me (?:my|the) (?:battery|cpu|ram|memory|disk|weather|latest|largest)|how much (?:battery|ram|memory|disk)|"
    r"what(?:'s| is) (?:my|on my) )", re.I)

LENGTHS = {
    "assistant": "keep replies to one to three short sentences.",
    "security": "keep replies to at most five sentences; put longer material into save_report.",
}


class OllamaBackend:
    name = "ollama"

    def __init__(self):
        self.model = config.OLLAMA_MODEL
        self._tried_start = False

    def _start_server(self):
        """If Ollama is installed but not running, start it once in the background."""
        if self._tried_start:
            return
        self._tried_start = True
        exe = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if exe.exists():
            log.info("starting ollama serve")
            subprocess.Popen([str(exe), "serve"], creationflags=subprocess.CREATE_NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(4)

    def available(self):
        for attempt in range(2):
            try:
                tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3).json()
                break
            except requests.RequestException:
                if attempt == 0 and not self._tried_start:
                    self._start_server()
                    continue
                return False, "Ollama isn't running. Install it from ollama.com or run install.ps1."
        names = [m["name"] for m in tags.get("models", [])]
        if not any(n == self.model or n == f"{self.model}:latest" for n in names):
            hint = f" Installed models: {', '.join(names)}." if names else ""
            return False, f"The model {self.model} isn't downloaded. Run: ollama pull {self.model}.{hint}"
        return True, f"Ollama ({self.model})"

    def chat(self, messages, tools):
        r = requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=240, json={
            "model": self.model, "messages": messages, "tools": tools, "stream": False,
            "keep_alive": "30m", "options": {"temperature": 0.3, "num_ctx": config.OLLAMA_NUM_CTX},
        })
        r.raise_for_status()
        msg = r.json()["message"]
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            fn = c.get("function", {})
            calls.append({"id": str(i), "name": fn.get("name", ""), "args": _parse_args(fn.get("arguments"))})
        return {"role": "assistant", "content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or []}, \
            msg.get("content") or "", calls

    def tool_message(self, call, result):
        return {"role": "tool", "tool_name": call["name"], "content": result}


class OpenAIBackend:
    name = "openai"

    def __init__(self):
        self.key = os.environ.get("OPENAI_API_KEY", "")
        self.model = config.OPENAI_MODEL

    def available(self):
        return (True, f"OpenAI-compatible API ({self.model})") if self.key else (False, "OPENAI_API_KEY is not set.")

    def chat(self, messages, tools):
        r = requests.post(f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions", timeout=120,
                          headers={"Authorization": f"Bearer {self.key}"},
                          json={"model": self.model, "messages": messages, "tools": tools, "temperature": 0.3})
        if r.status_code >= 400:
            raise RuntimeError(f"API error {r.status_code}: {r.text[:200]}")
        msg = r.json()["choices"][0]["message"]
        raw_calls = msg.get("tool_calls") or []
        calls = [{"id": c["id"], "name": c["function"]["name"], "args": _parse_args(c["function"].get("arguments"))}
                 for c in raw_calls]
        out = {"role": "assistant", "content": msg.get("content")}
        if raw_calls:
            out["tool_calls"] = raw_calls
        return out, msg.get("content") or "", calls

    def tool_message(self, call, result):
        return {"role": "tool", "tool_call_id": call["id"], "content": result}


def _parse_args(args):
    if isinstance(args, dict):
        return args
    try:
        return json.loads(args or "{}")
    except json.JSONDecodeError:
        return {}


def _calls_in_text(content):
    """Small local models sometimes write a tool call as JSON text instead of a real call."""
    m = re.search(r"\{.*\"name\"\s*:\s*\"(\w+)\".*\}", content or "", re.S)
    if not m or m.group(1) not in registry.TOOLS:
        return []
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [{"id": "0", "name": obj["name"], "args": obj.get("arguments") or obj.get("parameters") or {}}]


class AIEngine:
    def __init__(self, execute, memory):
        self.execute = execute          # callable(name, args) -> str
        self.memory = memory
        self.mode = "assistant"
        self.backend = None
        self.status_text = "not checked"
        self._checked_at = 0

    def _candidates(self):
        choice = config.AI_BACKEND.lower()
        if choice == "none":
            return []
        if choice == "ollama":
            return [OllamaBackend()]
        if choice == "openai":
            return [OpenAIBackend()]
        return [OllamaBackend(), OpenAIBackend()]

    def available(self, force=False):
        """Pick the first working backend. Re-checks every 30 s while down, so starting Ollama later just works."""
        if not force and self.backend and time.time() - self._checked_at < 300:
            return True
        if not force and not self.backend and time.time() - self._checked_at < 30:
            return False
        self._checked_at = time.time()
        reasons = []
        for b in self._candidates():
            ok, msg = b.available()
            if ok:
                if not self.backend or self.backend.name != b.name:
                    log.info("AI backend: %s", msg)
                self.backend, self.status_text = b, msg
                return True
            reasons.append(msg)
        self.backend = None
        self.status_text = " ".join(reasons) or "AI is disabled in the config."
        return False

    def system_prompt(self):
        address = f' Address the user as "{config.ADDRESS}" now and then, not in every sentence.' if config.ADDRESS else ""
        return BASE_PROMPT.format(
            user=config.USER_NAME or "the user", address=address, length=LENGTHS[self.mode],
            mode=SECURITY_MODE if self.mode == "security" else ASSISTANT_MODE)

    def context_line(self):
        """Changing details go in the user turn, so the system prompt + tools stay identical
        between requests and Ollama can reuse its prompt cache (much faster on CPU)."""
        now = datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p")
        mem = self.memory.prompt_context().replace("\n", " ")
        return f"[Context: {now}. {mem}]".replace(". ]", "]")

    def ask(self, text):
        if not self.available():
            raise RuntimeError(self.status_text)
        messages = [{"role": "system", "content": self.system_prompt()},
                    *self.memory.recent_history(config.HISTORY_TURNS),
                    {"role": "user", "content": f"{self.context_line()}\n{text}"}]
        tools = registry.schemas()
        used_tools, nudged = False, False
        for _ in range(8):
            try:
                assistant_msg, content, calls = self.backend.chat(messages, tools)
            except requests.RequestException as e:
                self.backend = None
                self._checked_at = 0
                raise RuntimeError(f"I lost contact with the AI model: {e}") from e
            if not calls and self.backend.name == "ollama":
                calls = _calls_in_text(content)
                if calls:
                    content = ""
            messages.append(assistant_msg)
            if not calls:
                if not used_tools and not nudged and ACTION_RX.match(text):
                    # Small models sometimes "answer" an action without doing it. Push back once.
                    nudged = True
                    log.info("no tool used for action request, nudging the model")
                    messages.append({"role": "user", "content":
                                     "You did not call any tool, so nothing was actually done or checked. "
                                     "Call the right tool now. Do not answer from guesses."})
                    continue
                return content.strip() or "Done."
            used_tools = True
            for call in calls:
                result = self.execute(call["name"], call["args"])
                messages.append(self.backend.tool_message(call, str(result)))
        return "I did what I could, but that took more steps than I'm allowed."
