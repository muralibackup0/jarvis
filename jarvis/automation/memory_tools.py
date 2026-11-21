"""Voice access to long-term memory, custom commands and routines."""
import re

from ..core.memory import SensitiveDataError
from ..core.registry import context, tool


def _mem():
    return context["memory"]


@tool("Remember a fact or preference about the user for future conversations "
      "(e.g. 'my favourite browser is Chrome'). Never use for passwords or secrets.",
      fact=("string", "The fact, written as a full sentence about the user"))
def remember(fact):
    try:
        _mem().remember(fact, "preference" if re.search(r"\b(prefer|favou?rite|like|love|hate)\b", fact, re.I) else "fact")
    except SensitiveDataError as e:
        return str(e)
    return "Got it, I'll remember that."


@tool("List what Jarvis remembers about the user, optionally filtered by a word.",
      search=("string", "Word to filter by, or empty for everything"))
def list_memories(search):
    facts = _mem().facts(search)
    if not facts:
        return "I don't have any memories about that yet." if search else "I don't remember anything about you yet."
    return f"I remember {len(facts)} thing{'s' if len(facts) != 1 else ''}: " + "; ".join(facts) + "."


@tool("Delete remembered facts that contain a word or phrase.", dangerous=True,
      search=("string", "Word or phrase identifying what to forget"))
def forget_memory(search):
    if not search.strip():
        return "Tell me what to forget."
    gone = _mem().forget(search)
    return f"Forgot: {'; '.join(gone)}." if gone else f"I don't have any memories about {search}."


@tool("Erase the stored conversation history (remembered facts are kept).", dangerous=True)
def clear_conversation_history():
    _mem().clear_history()
    return "Conversation history cleared."


@tool("Create a custom voice command: when the user says the phrase, run the given command instead.",
      phrase=("string", "Trigger phrase, e.g. 'movie time'"),
      command=("string", "What to do, in plain words, e.g. 'open netflix and set volume to 80'"))
def add_custom_command(phrase, command):
    if not phrase or not command:
        return "I need both a trigger phrase and a command."
    try:
        _mem().add_custom_command(phrase, command)
    except SensitiveDataError as e:
        return str(e)
    return f"Done. When you say {phrase}, I'll {command}."


@tool("List the user's custom voice commands.")
def list_custom_commands():
    cmds = _mem().custom_commands()
    return ("Your custom commands: " + "; ".join(f"'{p}' runs '{c}'" for p, c in cmds) + ".") if cmds \
        else "You don't have any custom commands yet."


@tool("Delete a custom voice command.", phrase=("string", "Trigger phrase to delete"))
def delete_custom_command(phrase):
    return f"Deleted the command {phrase}." if _mem().delete_custom_command(phrase) else f"There's no command called {phrase}."


def split_steps(steps):
    parts = re.split(r"\s*(?:;|\n|,\s*(?:and\s+)?then\s+|,\s*|\s+and then\s+|\s+then\s+)\s*", steps)
    return [p.strip(" .") for p in parts if p.strip(" .")]


@tool("Save a routine: a named list of commands run one after another (e.g. 'morning' = open gmail; weather; battery).",
      name=("string", "Routine name"), steps=("string", "Commands separated by semicolons"))
def create_routine(name, steps):
    parts = split_steps(steps)
    if not name or not parts:
        return "A routine needs a name and at least one step."
    try:
        _mem().save_routine(name, parts)
    except SensitiveDataError as e:
        return str(e)
    return f"Saved the {name} routine with {len(parts)} step{'s' if len(parts) != 1 else ''}. Say 'run {name} routine' to start it."


@tool("Run a saved routine by name.", name=("string", "Routine name"))
def run_routine(name):
    steps = _mem().routine(name)
    if steps is None:
        return f"I don't have a routine called {name}."
    router, speaker = context["router"], context.get("speaker")
    done = 0
    for step in steps:
        reply = router.handle(step, depth=1)
        if speaker and reply:
            speaker.say(reply)
        done += 1
    return f"The {name} routine is complete, {done} step{'s' if done != 1 else ''} done."


@tool("List saved routines and their steps.")
def list_routines():
    rs = _mem().routines()
    return ("Your routines: " + "; ".join(f"{n}: {', '.join(s)}" for n, s in rs) + ".") if rs \
        else "You don't have any routines yet."


@tool("Delete a saved routine.", dangerous=True, name=("string", "Routine name"))
def delete_routine(name):
    return f"Deleted the {name} routine." if _mem().delete_routine(name) else f"There's no routine called {name}."
