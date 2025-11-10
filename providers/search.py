import re, time, requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from . import Item, Section

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0 Safari/537.36"}

import json

def _ddg(query: str, max_results: int = 5):
    """Return a list of result URLs using DuckDuckGo's JSON API."""
    url = "https://api.duckduckgo.com/?" + urlencode({
        "q": query,
        "format": "json",
        "no_html": 1,
        "skip_disambig": 1
    })
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    data = r.json()
    out = []
    for topic in data.get("RelatedTopics", []):
        if isinstance(topic, dict) and "FirstURL" in topic:
            out.append(topic["FirstURL"])
        if len(out) >= max_results:
            break
    return out



def _title_summary(url: str):
    r = requests.get(url, headers=UA, timeout=15)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "html.parser")
    title = (s.title.string if s.title and s.title.string else "").strip()
    if not title:
        m = s.find("meta", attrs={"property":"og:title"}) or s.find("meta", attrs={"name":"title"})
        if m and m.get("content"): title = m["content"].strip()
    desc = ""
    m = s.find("meta", attrs={"name":"description"}) or s.find("meta", attrs={"property":"og:description"})
    if m and m.get("content"): desc = m["content"].strip()
    if not desc:
        for p in s.select("p"):
            txt = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
            if 60 <= len(txt) <= 240:
                desc = txt; break
    if len(desc) > 220: desc = desc[:217].rstrip() + "…"
    if not title: title = url.split("/")[2]
    return title, desc

def fetch(cfg: dict, heading: str) -> Section:
    query = cfg["query"]
    max_results = int(cfg.get("max_results", 5))
    limit = int(cfg.get("limit", 5))
    render = cfg.get("render", "{title} — {url}")
    allow = set(d.lower() for d in cfg.get("allow_domains", []) or [])
    deny  = set(d.lower() for d in cfg.get("deny_domains", []) or [])

    items: list[Item] = []
    for u in _ddg(query, max_results=max_results):
        dom = u.split("/")[2].lower()
        if allow and not any(dom.endswith(a) for a in allow): continue
        if deny  and any(dom.endswith(d) for d in deny): continue
        try:
            title, summary = _title_summary(u)
            it: Item = {"title": title, "url": u, "summary": summary}
            it["rendered"] = render.format(title=title, url=u, summary=summary or "")
            items.append(it)
            time.sleep(0.8)  # polite
        except Exception:
            continue
        if len(items) >= limit: break
    return {"heading": heading, "items": items}
