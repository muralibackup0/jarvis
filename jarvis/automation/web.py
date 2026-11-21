"""Web: open sites, search (in the browser or in the background), and read pages for the AI to summarize."""
import html
import re
import webbrowser
from html.parser import HTMLParser
from urllib.parse import quote_plus

import requests

from ..core.registry import context, tool

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={}",
    "bing": "https://www.bing.com/search?q={}",
    "duckduckgo": "https://duckduckgo.com/?q={}",
}


def _url(u):
    u = u.strip()
    return u if re.match(r"https?://", u) else "https://" + u


@tool("Open a website or URL in the default browser.", url=("string", "URL or domain, e.g. 'github.com'"))
def open_website(url):
    webbrowser.open(_url(url))
    return "Opening the website."


@tool("Search the web in the browser so the user can see the results page.",
      query=("string", "Search terms"), engine=("string", "Search engine", list(SEARCH_ENGINES)))
def search_web(query, engine):
    webbrowser.open(SEARCH_ENGINES[engine].format(quote_plus(query)))
    return f"Here are the {engine.capitalize()} results for {query}."


@tool("Play the top YouTube video for a song, video or artist.", query=("string", "What to play"))
def play_youtube(query):
    try:
        page = requests.get(f"https://www.youtube.com/results?search_query={quote_plus(query)}", headers=UA, timeout=8).text
        vid = re.search(r'"videoId":"([\w-]{11})"', page)
        if vid:
            webbrowser.open(f"https://www.youtube.com/watch?v={vid.group(1)}")
            return f"Playing {query} on YouTube."
    except requests.RequestException:
        pass
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
    return f"Here's what YouTube has for {query}."


@tool("Open YouTube search results for a topic (without auto-playing).", query=("string", "What to search for"))
def search_youtube(query):
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
    return f"Here are YouTube results for {query}."


# ---------------------------------------------------------------- background search & reading

def search_results(query, limit=6):
    """Top web results via Bing's public RSS output (no API key, no browser needed)."""
    r = requests.get("https://www.bing.com/search", params={"q": query, "format": "rss", "count": limit},
                     headers=UA, timeout=10)
    r.raise_for_status()

    def field(item, tag):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", item, re.S)
        return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""

    results = []
    for item in re.findall(r"<item>(.*?)</item>", r.text, re.S)[:limit]:
        url = field(item, "link")
        if url.startswith("http"):
            results.append({"title": field(item, "title"), "url": url, "snippet": field(item, "description"),
                            "date": field(item, "pubDate")[:16]})
    return results


@tool("Search the internet in the background and get the top results (titles, links, snippets) to answer "
      "questions about news or current information.", query=("string", "Search terms"))
def web_search(query):
    try:
        results = search_results(query)
    except requests.RequestException as e:
        return f"The web search failed: {e}"
    if not results:
        return "The search returned no results."
    context["last_results"] = results
    return "\n".join(f"{i}. {r['title']} - {r['snippet']} ({r['url']})" for i, r in enumerate(results, 1))


@tool("Open one of the results from the last web_search in the browser.", number=("integer", "Result number, 1 = first"))
def open_search_result(number):
    results = context.get("last_results") or []
    if not 1 <= number <= len(results):
        return "I don't have that search result. Search for something first."
    webbrowser.open(results[number - 1]["url"])
    return f"Opening {results[number - 1]['title']}."


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe"}
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts, self.title, self._skip, self._in_title = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def fetch_text(url, max_chars=6000):
    r = requests.get(_url(url), headers=UA, timeout=12)
    r.raise_for_status()
    if "html" not in r.headers.get("content-type", "html"):
        return "", r.text[:max_chars]
    p = _TextExtractor()
    p.feed(r.text)
    text = re.sub(r"[ \t]+", " ", "".join(p.parts))
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 40]  # drop menus & buttons
    return p.title.strip(), "\n".join(lines)[:max_chars]


@tool("Download a web page and return its main text so it can be read, explained or summarized. "
      "Accepts a URL or a result number from the last web_search.", url=("string", "URL, or result number like '1'"))
def read_webpage(url):
    results = context.get("last_results") or []
    if url.strip().isdigit():
        if not 1 <= int(url) <= len(results):
            return "I don't have that search result. Search for something first."
        url = results[int(url) - 1]["url"]
    try:
        title, text = fetch_text(url)
    except requests.RequestException as e:
        return f"I couldn't load that page: {e}"
    if not text:
        return "The page had no readable text (it may need JavaScript or a login)."
    return f"Page title: {title}\n{text}"
