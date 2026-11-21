"""Jarvis - a local voice assistant for Windows.

  python main.py              voice mode, say "Jarvis, <command>"
  python main.py --no-wake    voice mode, every utterance is a command
  python main.py --text       type commands instead of speaking (still talks back)
  python main.py --text --mute
"""
import argparse
import re
import sys
import threading
import time

from jarvis import config, intents, tools
from jarvis.brain import Brain
from jarvis.tts import Speaker

WAKE_RX = re.compile(rf"\b(?:hey\s+|ok\s+)?(?:{'|'.join(config.WAKE_WORDS)})\b[\s,.!?]*(.*)", re.I | re.S)
YES_RX = re.compile(r"\b(yes|yeah|yep|sure|do it|go ahead|confirm|affirmative|okay|ok)\b", re.I)


class Jarvis:
    def __init__(self, args):
        self.args = args
        self.speaker = Speaker(muted=args.mute)
        tools.notify = lambda msg: self.speaker.say(msg)
        self.listener = None
        if not args.text:
            from jarvis.stt import Listener
            self.listener = Listener()
        self.brain = Brain(self.execute)
        self.brain_ok, why = self.brain.available()
        if not self.brain_ok:
            print(f"[warn] Local AI unavailable: {why}\n       Simple commands still work; free-form requests need Ollama.")
        threading.Thread(target=tools.start_apps, daemon=True).start()  # warm the app index

    # ---------- input
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
        answer = self.hear("Confirm (yes/no): ", timeout=8)
        return bool(answer and YES_RX.search(answer) and not re.search(r"\b(no|don't|cancel|stop)\b", answer, re.I))

    # ---------- actions
    def execute(self, name, args):
        t = tools.TOOLS.get(name)
        if not t:
            return f"Unknown tool {name}."
        clean = {}
        for p, (ty, _) in t["params"].items():
            v = args.get(p, "")
            try:
                clean[p] = int(float(v)) if ty == "integer" else float(v) if ty == "number" else ("" if v is None else str(v))
            except (TypeError, ValueError):
                return f"Invalid value for {p}: {v}"
        print(f"  -> {name}({', '.join(f'{k}={v!r}' for k, v in clean.items())})")
        if t["dangerous"]:
            detail = f": {clean['command']}" if "command" in clean else ""
            if not self.confirm(f"Are you sure you want me to {name.replace('_', ' ')}{detail}?"):
                return "The user declined, so it was not done."
        try:
            return t["fn"](**clean)
        except Exception as e:
            return f"That failed: {e}"

    def handle(self, command):
        """Run one command. Returns False when the user wants Jarvis to stop."""
        command = command.strip()
        if not command:
            return True
        if intents.normalize(command).lower() in config.EXIT_PHRASES:
            self.speaker.say("Goodbye.")
            return False
        hit = intents.match(command, allow_compound=not self.brain_ok)
        if hit:
            self.speaker.say(self.execute(*hit))
        elif self.brain_ok:
            try:
                self.speaker.say(self.brain.ask(command))
            except Exception as e:
                self.speaker.say(f"My local AI ran into a problem: {e}")
        else:
            self.speaker.say("I don't know that command yet, and my local AI model isn't running.")
        return True

    # ---------- loops
    def run(self):
        if self.args.text:
            self.speaker.say("Jarvis online. Type a command.")
            while self.handle(self.hear()):
                pass
            return

        self.listener.calibrate()
        wake = "" if self.args.no_wake else ' Say "Jarvis" followed by a command.'
        self.speaker.say(f"Jarvis online.{wake}")
        followup_until = 0.0
        while True:
            text = self.hear()
            if not text:
                continue
            m = WAKE_RX.search(text)
            if self.args.no_wake or time.time() < followup_until:
                command = m[1] if m else text
            elif m:
                command = m[1].strip()
                if not command:
                    self.speaker.say("Yes?")
                    command = self.hear(timeout=6)
                    if not command:
                        continue
            else:
                continue  # no wake word - not talking to us
            if not self.handle(command):
                return
            followup_until = time.time() + config.FOLLOWUP_SECONDS


def main():
    ap = argparse.ArgumentParser(description="Jarvis local voice assistant")
    ap.add_argument("--text", action="store_true", help="type commands instead of speaking")
    ap.add_argument("--mute", action="store_true", help="don't speak replies (print only)")
    ap.add_argument("--no-wake", action="store_true", help="no wake word needed")
    ap.add_argument("--model", help=f"Ollama model (default {config.OLLAMA_MODEL})")
    args = ap.parse_args()
    if args.model:
        config.OLLAMA_MODEL = args.model
    try:
        Jarvis(args).run()
    except KeyboardInterrupt:
        print("\nBye.")
    sys.exit(0)


if __name__ == "__main__":
    main()
