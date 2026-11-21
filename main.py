"""J.A.R.V.I.S. - a local AI voice assistant for Windows.

  python main.py              voice mode: say "Hey Jarvis, <command>" or "Jarvis, <command>"
  python main.py --no-wake    voice mode, every utterance is a command
  python main.py --text       type commands instead of speaking (still talks back)
  python main.py --check      check dependencies, microphone and AI brain
"""
import argparse
import re
import sys
import threading
import time

from jarvis import config
from jarvis.utils import deps


def parse_args():
    ap = argparse.ArgumentParser(description="Jarvis local AI voice assistant")
    ap.add_argument("--text", action="store_true", help="type commands instead of speaking")
    ap.add_argument("--mute", action="store_true", help="don't speak replies (print only)")
    ap.add_argument("--no-wake", action="store_true", help="no wake word needed")
    ap.add_argument("--check", action="store_true", help="run the system check and exit")
    ap.add_argument("--model", help=f"Ollama model (default {config.OLLAMA_MODEL})")
    ap.add_argument("--backend", choices=["auto", "ollama", "openai", "none"], help="AI backend")
    return ap.parse_args()


class Jarvis:
    YES = re.compile(r"\b(yes|yeah|yep|yup|sure|do it|go ahead|confirm(ed)?|affirmative|proceed|okay|ok)\b", re.I)
    NO = re.compile(r"\b(no|nope|don't|do not|cancel|stop|abort|negative|wait)\b", re.I)

    def __init__(self, args):
        from jarvis import automation  # noqa: F401  (registers all tools)
        from jarvis.core.registry import context
        from jarvis.core.router import Router
        from jarvis.voice.tts import Speaker

        self.args = args
        self.speaker = Speaker(muted=args.mute)
        self.router = Router(confirm=self.confirm)
        context["speaker"] = self.speaker
        self.wake_rx = re.compile(
            rf"\b(?:(?:hey|hi|ok|okay|yo)[\s,]+)?(?:{'|'.join(map(re.escape, config.WAKE_WORDS))})\b[\s,.!?]*(.*)",
            re.I | re.S)
        self.listener = None
        if not args.text:
            from jarvis.voice.stt import Listener
            self.listener = Listener(is_busy=self.speaker.is_busy)
        from jarvis.automation.apps import start_apps
        threading.Thread(target=start_apps, daemon=True).start()  # warm the app index

    # ---------------------------------------------------------------- input
    def hear(self, prompt="You: ", timeout=None):
        if self.args.text:
            try:
                return input(prompt).strip()
            except EOFError:
                return "exit"
        text = self.listener.listen(timeout=timeout)
        if text:
            print(f"You: {text}")
        return text

    def confirm(self, question):
        self.speaker.say(question)
        for _ in range(2):
            answer = self.hear("Confirm (yes/no): ", timeout=8)
            if not answer:
                break
            if self.NO.search(answer):
                return False
            if self.YES.search(answer):
                return True
            self.speaker.say("Sorry, was that a yes or a no?")
        self.speaker.say("I'll take that as a no.")
        return False

    # ---------------------------------------------------------------- loop
    def respond(self, command):
        """Returns False when the user asked Jarvis to stop."""
        from jarvis.core.router import EXIT
        reply = self.router.handle(command)
        if reply is EXIT:
            self.speaker.say(f"Goodbye{', ' + config.ADDRESS if config.ADDRESS else ''}.")
            return False
        if reply:
            self.speaker.say(reply)
        return True

    def greeting(self):
        hour = time.localtime().tm_hour
        part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
        who = f", {config.ADDRESS}" if config.ADDRESS else ""
        brain = "" if self.router.ai.available() else " My AI brain is offline, so I'll stick to basic commands."
        return f"Good {part}{who}. Jarvis is online.{brain}"

    def run(self):
        ai = self.router.ai
        if not ai.available():
            print(f"[warn] AI brain offline: {ai.status_text}\n       Basic commands still work.")
        else:
            print(f"[ai] {ai.status_text}")

        if self.args.text:
            self.speaker.say(self.greeting())
            while self.respond(self.hear()):
                pass
            return

        self.listener.calibrate()
        self.speaker.say(self.greeting() + ("" if self.args.no_wake else ' Say "Hey Jarvis" when you need me.'))
        print("Listening... (press Esc to interrupt Jarvis while it's speaking, Ctrl+C to quit)")
        followup_until = 0.0
        while True:
            text = self.hear()
            if not text:
                continue
            m = self.wake_rx.search(text)
            if self.args.no_wake or time.time() < followup_until:
                command = m[1] if m else text
            elif m:
                command = m[1].strip()
                if not command:
                    self.speaker.say("Yes?")
                    command = self.hear(timeout=7)
                    if not command:
                        continue
            else:
                continue  # no wake word - not talking to Jarvis
            if not self.respond(command):
                return
            followup_until = time.time() + config.FOLLOWUP_SECONDS


def main():
    args = parse_args()
    if args.model:
        config.OLLAMA_MODEL = args.model
    if args.backend:
        config.AI_BACKEND = args.backend

    missing = deps.missing_packages(voice=not args.text)
    if missing and not args.check:
        print("Jarvis is missing some Python packages:")
        for pip, why in missing:
            print(f"  - {pip} ({why})")
        print(f"Fix: {deps.FIX}\n(or run install.ps1). Use --check for a full report.")
        sys.exit(1)

    if args.check:
        from jarvis import automation  # noqa: F401
        from jarvis.core.ai_engine import AIEngine
        from jarvis.core.memory import Memory
        ok = deps.report(AIEngine(lambda n, a: "", Memory()), voice=True)
        sys.exit(0 if ok else 1)

    try:
        Jarvis(args).run()
    except KeyboardInterrupt:
        print("\nBye.")


if __name__ == "__main__":
    main()
