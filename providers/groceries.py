# providers/groceries.py
import requests, re
from bs4 import BeautifulSoup
import datetime

KEYWORDS = ["æg", "hakket oksekød", "græsk yoghurt", "blåbær", "søde kartofler", "sødekartofler", "hytteost", "peanut butter"]
RETAILS = {
    "netto": "https://netto.dk/tilbudsavis/",
    "rema1000": "https://rema1000.dk/tilbudsavis/",
    "lidl": "https://www.lidl.dk/tilbudsavis",
    "coop": "https://coop.dk/tilbudsavis",
    "bilka": "https://www.bilka.dk/tilbudsavis"
}

def _text_from_url(url):
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""

def fetch_groceries(cfg: dict, heading: str):
    """
    Quick scan for keywords in weekly ad pages for the main Danish chains.
    This is a light-weight fallback; the llm_search browsing-backed schema is preferred for exact prices.
    """
    today = datetime.date.today().isoformat()
    items = []
    for name, url in RETAILS.items():
        txt = _text_from_url(url).lower()
        if not txt:
            continue
        for kw in KEYWORDS:
            if kw in txt:
                # minimal rendering, encourage the LLM-search to produce exact price
                items.append({
                    "title": f"{kw} — {name.capitalize()}",
                    "rendered": f"<strong>{kw}</strong> appears in {name.capitalize()} weekly ad. <a href='{url}'>view ad</a> — discovered {today}",
                    "image_url": None
                })
    if not items:
        items.append({"title": heading, "rendered": "No grocery offers found by simple parser."})
    return {"heading": heading, "items": items}
