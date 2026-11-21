"""The tool allowlist. Only functions registered here can be run - by voice or by the AI.

    @tool("What it does", dangerous=False, level=("integer", "0 to 100"),
          mode=("string", "One of these", ["a", "b"]))

dangerous=True  -> Jarvis asks for a spoken "yes" before running it.
hidden=True     -> not offered to the AI and refused if the AI asks for it anyway.
"""
TOOLS = {}

# Shared runtime objects (router, memory, speaker, ai) - filled in by main at startup.
context = {}

MAX_TEXT = 8000


def tool(description, dangerous=False, hidden=False, **params):
    def deco(fn):
        spec = {}
        for name, p in params.items():
            ty, desc, *rest = p
            spec[name] = {"type": ty, "description": desc, "enum": rest[0] if rest else None}
        TOOLS[fn.__name__] = {"fn": fn, "description": description, "dangerous": dangerous,
                              "hidden": hidden, "params": spec}
        return fn
    return deco


def schemas():
    out = []
    for name, t in TOOLS.items():
        if t["hidden"]:
            continue
        props = {}
        for p, s in t["params"].items():
            props[p] = {"type": s["type"], "description": s["description"]}
            if s["enum"]:
                props[p]["enum"] = s["enum"]
        out.append({"type": "function", "function": {
            "name": name, "description": t["description"],
            "parameters": {"type": "object", "properties": props, "required": list(props)},
        }})
    return out


def validate(name, args):
    """Return (tool, clean_args) or raise ValueError with a speakable reason."""
    t = TOOLS.get(name)
    if not t:
        raise ValueError(f"{name} is not an action I'm allowed to perform")
    args = args if isinstance(args, dict) else {}
    clean = {}
    for p, s in t["params"].items():
        v, ty = args.get(p), s["type"]
        try:
            if ty == "integer":
                v = int(float(str(v).strip().rstrip("%")))
            elif ty == "number":
                v = float(str(v).strip())
            elif ty == "boolean":
                v = v if isinstance(v, bool) else str(v).strip().lower() in ("true", "yes", "1", "y")
            else:
                v = "" if v is None else str(v).strip()
                if len(v) > MAX_TEXT:
                    raise ValueError(f"{p} is too long")
        except (TypeError, ValueError):
            raise ValueError(f"I need a valid {ty} for {p.replace('_', ' ')}, got {v!r}")
        if s["enum"]:
            options = [e.lower() for e in s["enum"]]
            if str(v).lower() not in options:
                raise ValueError(f"{p.replace('_', ' ')} must be one of: {', '.join(s['enum'])}")
            v = str(v).lower()
        clean[p] = v
    return t, clean
