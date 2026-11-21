"""Routes one user command: custom commands -> routines -> fast intents -> AI brain.

Every action goes through execute(), which enforces the allowlist, validates arguments,
asks for confirmation on dangerous actions and writes the action log.
"""
from .. import config
from ..utils.logger import get_logger
from . import intents, registry
from .ai_engine import AIEngine
from .memory import Memory

log = get_logger("router")

EXIT = object()


class Router:
    def __init__(self, confirm, memory=None):
        """confirm(question) -> bool is supplied by the UI (voice, text or GUI)."""
        self.confirm = confirm
        self.memory = memory or Memory()
        self.ai = AIEngine(self.execute, self.memory)
        registry.context.update(router=self, memory=self.memory, ai=self.ai)

    # ---------------------------------------------------------------- actions
    def execute(self, name, args):
        try:
            t, clean = registry.validate(name, args)
        except ValueError as e:
            log.warning("REJECTED %s %r: %s", name, args, e)
            return f"Not done: {e}."
        if t["hidden"]:
            log.warning("BLOCKED hidden tool %s %r", name, clean)
            return f"Not done: {name.replace('_', ' ')} is disabled in my safety settings."
        shown = ", ".join(f"{k}={v!r}" for k, v in clean.items())
        print(f"  -> {name}({shown})")
        if t["dangerous"]:
            detail = "; ".join(str(v) for v in clean.values() if v not in ("", None))
            question = f"Should I {name.replace('_', ' ')}{': ' + detail if detail else ''}? Say yes or no."
            if not self.confirm(question):
                log.info("DECLINED %s(%s)", name, shown)
                return "The user said no, so it was not done."
        try:
            result = str(t["fn"](**clean))
            log.info("ACTION %s(%s) -> %s", name, shown, result[:300])
            return result
        except ModuleNotFoundError as e:
            log.error("MISSING DEPENDENCY for %s: %s", name, e)
            return (f"That needs the Python package {e.name}, which isn't installed. "
                    f"Run install.ps1 or: pip install -r requirements.txt")
        except Exception as e:
            log.exception("FAILED %s(%s)", name, shown)
            return f"That failed: {e}"

    # ---------------------------------------------------------------- commands
    def handle(self, text, depth=0):
        """Handle one command and return the reply text, or EXIT."""
        command = intents.normalize(text)
        if not command:
            return None
        low = command.lower()
        if depth == 0 and low in config.EXIT_PHRASES:
            return EXIT
        log.info("USER %s", text)

        reply = None
        if depth < 3:
            mapped = self.memory.custom_command(low)
            if mapped:
                log.info("CUSTOM '%s' -> '%s'", low, mapped)
                return self.handle(mapped, depth + 1)
            if self.memory.routine(low) is not None:
                reply = self.execute("run_routine", {"name": low})

        if reply is None:
            ai_ok = self.ai.available()
            hit = intents.match(command, allow_compound=not ai_ok)
            if hit:
                reply = self.execute(*hit)
            elif ai_ok:
                try:
                    reply = self.ai.ask(command)
                except Exception as e:
                    log.exception("AI failure")
                    reply = f"My AI brain ran into a problem: {e}"
            else:
                reply = ("I don't recognise that command, and my AI brain is offline, so I can't work it out. "
                         f"{self.ai.status_text}")

        if depth == 0:
            self.memory.add_history("user", command)
            self.memory.add_history("assistant", reply)
        log.info("JARVIS %s", reply[:300])
        return reply
