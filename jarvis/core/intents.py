"""Instant, LLM-free matching for common commands. Anything not matched goes to the AI brain.

Polite and casual phrasings are normalised first, so "Open Notepad", "Jarvis, launch my Notepad"
and "Can you open Notepad for me?" all become the same command.
"""
import re

LEAD_FILLERS = (r"^(?:(?:hey|hi|hello|ok|okay|so|um|uh|now|alright|"
                r"jarvis|jervis|javis|please|kindly|just|quickly|go ahead and|"
                r"can you|could you|would you|will you|can u|would you mind|"
                r"i want you to|i need you to|i'd like you to|i would like you to|"
                r"i want to|i need to|i'd like to|let's|lets|help me)[\s,]+)+")
TRAIL_FILLERS = r"(?:[\s,]+(?:please|for me|now|right now|quickly|jarvis|thanks|thank you|asap))+$"

_PC = r"(?:the\s+|my\s+)?(?:computer|laptop|pc|system|machine)"
_BROWSER = r"(?:(?:in|on) (?:the |my )?(?:browser|chrome|edge|firefox)\s*)?"


def _ss_location(m):
    return {"location": (m[1] or "pictures").lower()}


# Patterns that are safe even when the sentence contains "and" / "then".
PRIORITY = [
    (r"^(?:take (?:a |an )?)?(?:screenshot|screen shot|snapshot)(?: (?:and )?(?:save (?:it )?)?(?:to|on|in) (?:the |my )?(desktop|pictures|documents|downloads))?$"
     r"|^capture (?:the |my )?screen(?: (?:to|on) (?:the |my )?(desktop|pictures|documents|downloads))?$",
     "take_screenshot", lambda m: {"location": (m[1] or m[2] or "pictures").lower()}),
    (r"^(?:when(?:ever)?|if) i say ['\"]?(.+?)['\"]?(?:\s*,\s*|\s+(?:you should|then|please)\s+)(?:you should |then |please )?(.+)$",
     "add_custom_command", lambda m: {"phrase": m[1], "command": m[2]}),
    (r"^(?:create|make|add|save|set up) (?:a |my )?(?:new )?routine (?:called |named )?['\"]?(.+?)['\"]?(?::|,| that| to| with| which)\s+(.+)$",
     "create_routine", lambda m: {"name": m[1], "steps": m[2]}),
    (r"^(?:remember|don't forget|never forget) (?:that )?(.+)$", "remember", lambda m: {"fact": m[1]}),
    (r"^(?:take a note|note down|write down|make a note|add a note)(?: that)?[:,]? (.+)$", "take_note", lambda m: {"text": m[1]}),
    (r"^type (.+)$", "type_text", lambda m: {"text": m[1]}),
    (r"^(?:run|start|do|execute|begin|activate) (?:my |the )?(.+?) routine$", "run_routine", lambda m: {"name": m[1]}),
    (r"^(?:switch to |enable |turn on |activate |enter |start |go (?:in)?to )?(?:cyber ?security|security|hacker|pentest(?:ing)?|vapt) mode(?: on)?$",
     "set_mode", lambda m: {"mode": "security"}),
    (r"^(?:switch to |back to |return to |go back to )?(?:normal|assistant|default|standard) mode$"
     r"|^(?:exit|disable|turn off|leave|stop) (?:cyber ?security|security|hacker|pentest(?:ing)?|vapt) mode$",
     "set_mode", lambda m: {"mode": "assistant"}),
]

PATTERNS = [
    # power
    (rf"^(?:shut ?down|power off|turn off|switch off) {_PC}$", "shutdown_computer", lambda m: {}),
    (rf"^(?:restart|reboot) {_PC}$", "restart_computer", lambda m: {}),
    (rf"^(?:put {_PC} to sleep|sleep mode|{_PC} sleep|sleep {_PC})$", "sleep_computer", lambda m: {}),
    (r"^(?:cancel|abort|stop) (?:the )?(?:shutdown|restart|reboot)$", "cancel_shutdown", lambda m: {}),
    (rf"^lock(?: {_PC}| (?:the |my )?screen| it| up)?$", "lock_screen", lambda m: {}),
    # volume
    (r"^(?:set |change |turn |put )?(?:the )?(?:system )?volume (?:to |at )?(\d+)(?: ?%| percent)?$", "set_volume", lambda m: {"level": m[1]}),
    (r"^(?:volume up|(?:turn|increase|raise|pump) (?:up )?(?:the )?volume(?: up)?|louder|make it louder)$", "change_volume", lambda m: {"direction": "up"}),
    (r"^(?:volume down|(?:turn|decrease|lower|reduce) (?:down )?(?:the )?volume(?: down)?|quieter|make it quieter)$", "change_volume", lambda m: {"direction": "down"}),
    (r"^(?:mute|silence)(?: (?:the )?(?:volume|sound|audio|speakers?|computer|laptop))?$", "change_volume", lambda m: {"direction": "mute"}),
    (r"^unmute(?: (?:the )?(?:volume|sound|audio|speakers?|computer|laptop))?$", "change_volume", lambda m: {"direction": "unmute"}),
    # brightness
    (r"^(?:set |change |turn |put )?(?:the )?(?:screen )?brightness (?:to |at )?(\d+)(?: ?%| percent)?$", "set_brightness", lambda m: {"level": m[1]}),
    (r"^(?:brightness up|(?:increase|raise|turn up) (?:the )?(?:screen )?brightness|brighter|make (?:the screen |it )?brighter)$", "change_brightness", lambda m: {"direction": "up"}),
    (r"^(?:brightness down|(?:decrease|lower|reduce|turn down) (?:the )?(?:screen )?brightness|dimmer|dim (?:the )?screen|make (?:the screen |it )?dimmer)$", "change_brightness", lambda m: {"direction": "down"}),
    # media
    (r"^(?:next|skip)(?: (?:song|track|video))?$|^play (?:the )?next (?:song|track|video)$", "media_control", lambda m: {"action": "next"}),
    (r"^previous(?: (?:song|track|video))?$|^play (?:the )?previous (?:song|track|video)$", "media_control", lambda m: {"action": "previous"}),
    (r"^(?:pause|resume|play|stop|continue)(?: (?:the )?(?:music|song|video|media|playback))?$", "media_control", lambda m: {"action": "pause"}),
    (r"^(?:search youtube for|search on youtube for|youtube search(?: for)?|find on youtube) (.+)$|^(?:search|find) (?:for )?(.+?) on youtube$",
     "search_youtube", lambda m: {"query": m[1] or m[2]}),
    (r"^play (.+?)(?: on youtube| song| video)?$", "play_youtube", lambda m: {"query": m[1]}),
    # web
    (r"^(?:look up|lookup|explain|check|what is) (cve[-\s]?\d{4}[-\s]?\d{4,7})$", "lookup_cve", lambda m: {"cve_id": m[1]}),
    (r"^(?:search|look up)(?: for)? (.+?) on (google|bing|duckduckgo)$", "search_web", lambda m: {"query": m[1], "engine": m[2].lower()}),
    (r"^(?:search|google|look up|search the web for|search google for)(?: for)? (.+?)(?: on (?:the web|the internet|the browser))?$",
     "search_web", lambda m: {"query": m[1], "engine": "google"}),
    (r"^bing (.+)$|^search bing for (.+)$", "search_web", lambda m: {"query": m[1] or m[2], "engine": "bing"}),
    (r"^(?:go to|open|visit) ((?:https?://)?[\w-]+(?:\.[\w-]+)+(?:/\S*)?)$", "open_website", lambda m: {"url": m[1]}),
    (r"^open (?:the )?(first|second|third|fourth|fifth|\d) (?:result|link)$", "open_search_result",
     lambda m: {"number": {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}.get(m[1].lower(), m[1])}),
    # browser tabs
    (rf"^(?:open )?(?:a )?new tab{_BROWSER}$", "browser_tab", lambda m: {"action": "new"}),
    (r"^close (?:this |the |current )?tab$", "browser_tab", lambda m: {"action": "close"}),
    (r"^(?:next|switch) tab$|^(?:go to |switch to )?(?:the )?next tab$", "browser_tab", lambda m: {"action": "next"}),
    (r"^(?:go to |switch to )?(?:the )?previous tab$", "browser_tab", lambda m: {"action": "previous"}),
    (r"^(?:reopen|restore) (?:the )?(?:last |closed |last closed )?tab$", "browser_tab", lambda m: {"action": "reopen"}),
    (r"^(?:refresh|reload)(?: (?:the |this )?page)?$", "browser_tab", lambda m: {"action": "refresh"}),
    (r"^go back$", "browser_tab", lambda m: {"action": "back"}),
    # windows
    (r"^(?:close|exit) (?:this |the |current |active )?window$|^close (?:this|it)$", "window_action", lambda m: {"action": "close"}),
    (r"^(?:minimi[sz]e (?:all|everything|all windows)|show (?:the |my )?desktop|go to (?:the )?desktop)$", "window_action", lambda m: {"action": "minimize all"}),
    (r"^(?:maximi[sz]e)(?: (?:this|the|it))?(?: ?window)?$", "window_action", lambda m: {"action": "maximize"}),
    (r"^(?:minimi[sz]e)(?: (?:this|the|it))?(?: ?window)?$", "window_action", lambda m: {"action": "minimize"}),
    (r"^switch(?: the)? (?:window|windows|apps?)$|^alt tab$", "window_action", lambda m: {"action": "switch"}),
    (r"^snap (?:(?:this|the) window )?(?:to the )?(left|right)$", "window_action", lambda m: {"action": f"snap {m[1].lower()}"}),
    (r"^(?:show )?task view$|^show (?:all )?(?:open )?windows$", "window_action", lambda m: {"action": "task view"}),
    (r"^scroll (up|down)$", "scroll", lambda m: {"direction": m[1].lower()}),
    (r"^press (.+)$", "press_keys", lambda m: {"keys": m[1]}),
    # files & folders
    (r"^(?:empty|clear|clean) (?:the |my )?(?:recycle bin|trash|bin)$", "empty_recycle_bin", lambda m: {}),
    (r"^(?:create|make) (?:a )?(?:new )?folder (?:called |named )?(.+?)(?: (?:on|in) (?:the |my )?(desktop|documents|downloads|pictures|music|videos))?$",
     "create_folder", lambda m: {"name": m[1], "location": (m[2] or "desktop").lower()}),
    (r"^(open|find|show|get|locate|where is|what is|what's) (?:me )?(?:my |the )?(?:latest|newest|most recent|last|recent) "
     r"(?:downloaded )?([\w.]+?)(?: files?)?(?: (?:in|from) (?:my |the )?(desktop|documents|downloads|pictures|music|videos))?$",
     "latest_file", lambda m: {"kind": m[2], "folder": (m[3] or "").lower(), "open_it": m[1].lower() == "open"}),
    (r"^(?:find|show|list|what are|get)(?: me)? (?:the |my )?(?:largest|biggest|heaviest) files(?: (?:in|on) (?:my |the )?(.+?))?$",
     "largest_files", lambda m: {"folder": (m[1] or "downloads").lower()}),
    (r"^(?:find|search for|locate|where is) (?:the |a |my )?file (?:called |named )?(.+)$", "find_file", lambda m: {"name": m[1]}),
    # apps
    (r"^(?:open|launch|start|run|fire up|bring up|load) (?:up )?(.+)$", "open_app", lambda m: {"name": m[1]}),
    (r"^(?:close|quit|kill|terminate|shut|exit) (?:down )?(.+)$", "close_app", lambda m: {"name": m[1]}),
    (r"^(?:what are )?(?:my )?(?:most used|frequent|favou?rite) apps$", "frequent_apps", lambda m: {}),
    # info
    (r"^(?:what(?:'s| is) the )?time(?: is it)?(?: now)?$|^what time is it(?: now)?$|^tell me the time$", "get_time", lambda m: {}),
    (r"^(?:what(?:'s| is) )?(?:the |today's )?date(?: today)?$|^what day is (?:it|today)$|^tell me the date$", "get_date", lambda m: {}),
    (r"^(?:what(?:'s| is) (?:the |my )?)?battery(?: level| status| percentage| life)?$|^how much (?:battery|charge).*$|^check (?:my |the )?(?:laptop |computer |pc |system )?battery(?: level| status)?$|^is (?:my |the )?(?:laptop|computer) charging$",
     "battery_status", lambda m: {}),
    (r"^(?:system status|system info|(?:check )?(?:cpu|ram|memory)(?: usage)?|how(?:'s| is) (?:my |the )?(?:system|computer|laptop|pc)(?: doing)?|check (?:my )?system)$", "system_status", lambda m: {}),
    (r"^(?:what(?:'s| is) )?(?:using|eating|hogging) (?:all )?(?:my |the )?(?:memory|ram)$|^top processes$", "top_processes", lambda m: {}),
    (r"^(?:what(?:'s| is) (?:the )?)?weather(?: (?:like )?(?:in|at|for) (.+?))?(?: today| now)?$|^how(?:'s| is) the weather(?: (?:in|at) (.+?))?$",
     "get_weather", lambda m: {"city": m[1] or m[2] or ""}),
    (r"^(?:read|show|tell me)(?: me)? (?:my |the )?notes$", "read_notes", lambda m: {}),
    (r"^(?:read|what's on|what is on) (?:my |the )?clipboard$", "read_clipboard", lambda m: {}),
    (r"^set (?:a )?timer (?:for )?(\d+(?:\.\d+)?) (minutes?|seconds?|hours?)$", "set_timer",
     lambda m: {"minutes": float(m[1]) * {"s": 1 / 60, "m": 1, "h": 60}[m[2][0].lower()], "label": ""}),
    # memory & routines
    (r"^what do you (?:remember|know) about me$|^(?:list|show) (?:my |your )?memories$|^what do you remember$", "list_memories", lambda m: {"search": ""}),
    (r"^forget (?:that |about )?(.+)$", "forget_memory", lambda m: {"search": m[1]}),
    (r"^(?:clear|delete|erase) (?:our |the |my )?(?:conversation|chat) history$", "clear_conversation_history", lambda m: {}),
    (r"^(?:list|show|what are) (?:my )?routines$", "list_routines", lambda m: {}),
    (r"^(?:list|show|what are) (?:my )?custom commands$", "list_custom_commands", lambda m: {}),
    # security
]

COMPILED_PRIORITY = [(re.compile(p, re.I), n, b) for p, n, b in PRIORITY]
COMPILED = [(re.compile(p, re.I), n, b) for p, n, b in PATTERNS]


def normalize(text):
    text = re.sub(r"\s+", " ", text or "").strip().strip(" .!?,")
    for _ in range(2):
        text = re.sub(LEAD_FILLERS, "", text, flags=re.I)
        text = re.sub(TRAIL_FILLERS, "", text, flags=re.I).strip(" .!?,")
    return text


def match(text, allow_compound=False):
    """Return (tool_name, args) for a simple command, or None."""
    t = normalize(text)
    for rx, name, build in COMPILED_PRIORITY:
        m = rx.match(t)
        if m:
            return name, build(m)
    if not allow_compound and re.search(r"\b(and|then|after that|also)\b|,", t, re.I):
        return None  # multi-step request: let the AI plan it
    for rx, name, build in COMPILED:
        m = rx.match(t)
        if m:
            return name, build(m)
    return None
