"""Instant, LLM-free matching for common commands. Anything not matched goes to the local LLM."""
import re

FILLERS = r"^(?:(?:hey|ok|okay|please|can you|could you|would you|will you|i want you to|kindly)[\s,]+)+"

_PC = r"(?:the\s+)?(?:computer|laptop|pc|system)"

PATTERNS = [
    # power
    (rf"^(?:shut ?down|power off|turn off) {_PC}$", "shutdown_computer", lambda m: {}),
    (rf"^(?:restart|reboot) {_PC}$", "restart_computer", lambda m: {}),
    (rf"^(?:put {_PC} to sleep|sleep mode|{_PC} sleep)$", "sleep_computer", lambda m: {}),
    (r"^(?:cancel|abort|stop) (?:the )?(?:shutdown|restart)$", "cancel_shutdown", lambda m: {}),
    (rf"^lock(?: {_PC}| (?:the )?screen)?$", "lock_screen", lambda m: {}),
    # volume
    (r"^(?:set |change |turn )?(?:the )?volume (?:to |at )?(\d+)(?: ?%| percent)?$", "set_volume", lambda m: {"level": m[1]}),
    (r"^(?:volume up|(?:turn|increase|raise) (?:up )?(?:the )?volume(?: up)?|louder)$", "change_volume", lambda m: {"direction": "up"}),
    (r"^(?:volume down|(?:turn|decrease|lower|reduce) (?:down )?(?:the )?volume(?: down)?|quieter)$", "change_volume", lambda m: {"direction": "down"}),
    (r"^(?:mute|silence)(?: (?:the )?(?:volume|sound|audio))?$", "change_volume", lambda m: {"direction": "mute"}),
    (r"^unmute(?: (?:the )?(?:volume|sound|audio))?$", "change_volume", lambda m: {"direction": "unmute"}),
    # brightness
    (r"^(?:set |change )?(?:the )?(?:screen )?brightness (?:to |at )?(\d+)(?: ?%| percent)?$", "set_brightness", lambda m: {"level": m[1]}),
    (r"^(?:brightness up|(?:increase|raise|turn up) (?:the )?brightness|brighter)$", "change_brightness", lambda m: {"direction": "up"}),
    (r"^(?:brightness down|(?:decrease|lower|reduce|turn down) (?:the )?brightness|dimmer|dim (?:the )?screen)$", "change_brightness", lambda m: {"direction": "down"}),
    # media
    (r"^(?:next|skip)(?: (?:song|track|video))?$", "media_control", lambda m: {"action": "next"}),
    (r"^previous(?: (?:song|track|video))?$", "media_control", lambda m: {"action": "previous"}),
    (r"^(?:pause|resume|play|stop)(?: (?:the )?(?:music|song|video|media))?$", "media_control", lambda m: {"action": "pause"}),
    (r"^play (.+?)(?: on youtube)?$", "play_youtube", lambda m: {"query": m[1]}),
    # web
    (r"^(?:search|google|look up)(?: for)? (.+?)(?: on (?:google|the web|the internet))?$", "search_web", lambda m: {"query": m[1]}),
    (r"^(?:go to|open) ((?:https?://)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?)$", "open_website", lambda m: {"url": m[1]}),
    # windows
    (r"^(?:close|exit) (?:this |the |current )?window$|^close (?:this|it)$", "window_action", lambda m: {"action": "close"}),
    (r"^(?:minimi[sz]e (?:all|everything)|show (?:the )?desktop)$", "window_action", lambda m: {"action": "minimize all"}),
    (r"^(?:maximi[sz]e)(?: (?:this|the)? ?window)?$", "window_action", lambda m: {"action": "maximize"}),
    (r"^(?:minimi[sz]e)(?: (?:this|the)? ?window)?$", "window_action", lambda m: {"action": "minimize"}),
    (r"^switch(?: the)? (?:window|windows|apps?)$", "window_action", lambda m: {"action": "switch"}),
    (r"^scroll (up|down)$", "scroll", lambda m: {"direction": m[1]}),
    (r"^(?:take a |take )?screenshot$|^capture (?:the )?screen$", "take_screenshot", lambda m: {}),
    (r"^type (.+)$", "type_text", lambda m: {"text": m[1]}),
    (r"^press (.+)$", "press_keys", lambda m: {"keys": m[1]}),
    # apps
    (r"^(?:open|launch|start|run) (.+)$", "open_app", lambda m: {"name": m[1]}),
    (r"^(?:close|quit|kill) (.+)$", "close_app", lambda m: {"name": m[1]}),
    # info
    (r"^(?:what(?:'s| is) the )?time(?: is it)?(?: now)?$|^what time is it(?: now)?$", "get_time", lambda m: {}),
    (r"^(?:what(?:'s| is) )?(?:the |today's )?date(?: today)?$|^what day is (?:it|today)$", "get_date", lambda m: {}),
    (r"^(?:what(?:'s| is) (?:the |my )?)?battery(?: level| status| percentage)?$|^how much battery.*$", "battery_status", lambda m: {}),
    (r"^(?:system status|system info|how(?:'s| is) (?:my |the )?(?:system|computer|laptop|pc)(?: doing)?)$", "system_status", lambda m: {}),
    (r"^(?:what(?:'s| is) (?:the )?)?weather(?: (?:like )?(?:in|at|for) (.+?))?(?: today| now)?$", "get_weather", lambda m: {"city": m[1] or ""}),
    (r"^(?:take a note|note down|remember that|write down|make a note)[:,]? (.+)$", "take_note", lambda m: {"text": m[1]}),
    (r"^(?:read|show)(?: me)? (?:my )?notes$", "read_notes", lambda m: {}),
    (r"^read (?:my |the )?clipboard$", "read_clipboard", lambda m: {}),
    (r"^(?:find|search for|locate) (?:the |a |my )?file (?:called |named )?(.+)$", "find_file", lambda m: {"name": m[1]}),
    (r"^set (?:a )?timer (?:for )?(\d+(?:\.\d+)?) minutes?$", "set_timer", lambda m: {"minutes": m[1], "label": ""}),
]

COMPILED = [(re.compile(p, re.I), name, build) for p, name, build in PATTERNS]


def normalize(text):
    text = text.strip().strip(" .!?,")
    text = re.sub(FILLERS, "", text, flags=re.I)
    text = re.sub(r"[\s,]+please$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" .!?,")


def match(text, allow_compound=False):
    """Return (tool_name, args) for a simple command, or None."""
    t = normalize(text)
    if not allow_compound and re.search(r"\b(and|then|after that)\b", t, re.I):
        return None  # multi-step request: let the LLM plan it
    for rx, name, build in COMPILED:
        m = rx.match(t)
        if m:
            return name, build(m)
    return None
