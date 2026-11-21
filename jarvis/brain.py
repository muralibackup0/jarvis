"""Local LLM (Ollama) that decides which tools to call for free-form requests."""
import datetime
import json

import requests

from . import config, tools

SYSTEM_PROMPT = """You are Jarvis, a voice assistant running locally on the user's Windows laptop.
You control the laptop through the provided tools. Rules:
- When the user asks you to do something on the computer, call the right tool(s). For multi-step
  requests, call tools one after another until the whole request is done.
- Your replies are spoken aloud: answer in one or two short sentences, no markdown, lists or emojis.
- Never claim you did something unless a tool result confirms it.
- For general questions (facts, explanations, math, advice) just answer briefly without tools.
- Prefer specific tools over run_command; use run_command only when nothing else fits.
Current date and time: {now}."""


class Brain:
    def __init__(self, execute):
        self.execute = execute  # callable(name, args) -> str
        self.history = []
        self.tool_schemas = tools.schemas()

    def available(self):
        try:
            tags = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3).json()
        except requests.RequestException:
            return False, "Ollama isn't running."
        names = [m["name"] for m in tags.get("models", [])]
        want = config.OLLAMA_MODEL
        if not any(n == want or n == f"{want}:latest" or n.split(":")[0] == want for n in names):
            return False, f"Model {want} isn't downloaded. Run: ollama pull {want}"
        return True, ""

    def _chat(self, messages):
        r = requests.post(f"{config.OLLAMA_URL}/api/chat", timeout=180, json={
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "tools": self.tool_schemas,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.2},
        })
        r.raise_for_status()
        return r.json()["message"]

    def ask(self, text):
        system = {"role": "system", "content": SYSTEM_PROMPT.format(now=datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p"))}
        messages = [system, *self.history[-10:], {"role": "user", "content": text}]
        reply = ""
        for _ in range(6):
            msg = self._chat(messages)
            messages.append(msg)
            calls = msg.get("tool_calls") or []
            if not calls:
                reply = (msg.get("content") or "").strip()
                break
            for call in calls:
                fn = call.get("function", {})
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result = self.execute(fn.get("name", ""), args)
                messages.append({"role": "tool", "tool_name": fn.get("name", ""), "content": str(result)})
        else:
            reply = "I did what I could, but that took too many steps."
        reply = reply or "Done."
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
        return reply
