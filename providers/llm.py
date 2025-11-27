# providers/llm.py
import os
import json
import hashlib
import re
import datetime
from typing import Any, Dict, List, Optional
from openai import OpenAI


HISTORY_PATH = os.path.join("data", "history.json")
TODAY = datetime.date.today().isoformat()

# ----------------- helpers -----------------

def _load_hist():
    if not os.path.exists(HISTORY_PATH):
        return {"math_hashes": [], "bible_refs": [], "last_horoscope_date": ""}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"math_hashes": [], "bible_refs": [], "last_horoscope_date": ""}

def _save_hist(hist: dict):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def _client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)

def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    # strip fenced json
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    if m:
        text = m.group(1)
    # attempt parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # fallback: find first {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        cand = text[start:end+1]
        # remove trailing commas if any
        cand = re.sub(r",\s*}", "}", cand)
        cand = re.sub(r",\s*]", "]", cand)
        try:
            return json.loads(cand)
        except Exception:
            return None
    return None

def _is_recent(date_str: str, days: int = 7) -> bool:
    """Return True if date_str (YYYY-MM-DD) is within `days` days of today.
    If date_str is empty, return False (we require a date for verifiability)."""
    if not date_str:
        return False
    try:
        d = datetime.date.fromisoformat(date_str)
        return (datetime.date.today() - d).days <= days
    except Exception:
        return False

# ----------------- OpenAI wrappers -----------------

def _call_chat(messages: List[dict], model="gpt-4o-mini", temp=0.7) -> str:
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temp
        )
        text = resp.choices[0].message.content.strip()
        print("DEBUG: LLM raw output prefix:", text[:140].replace("\n"," ") + "...")
        return text
    except Exception as e:
        print("ERROR contacting OpenAI (chat):", e)
        return ""

def _call_web_search(system_prompt: str, user_prompt: str, model="gpt-4o-mini", temp=0.2) -> str:
    """
    Use OpenAI Responses API with the web_search_preview_2025_03_11 tool.
    """
    client = _client()
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            tools=[{"type": "web_search_preview_2025_03_11"}],
            temperature=temp
        )

        if hasattr(resp, "output_text") and resp.output_text:
            text = resp.output_text.strip()
            print("DEBUG SEARCH OUTPUT:", text[:300].replace("\n"," ") + "...")
            return text

        # fallback - assemble content blocks
        chunks = []
        for block in getattr(resp, "output", []) or []:
            if isinstance(block, dict):
                content = block.get("content")
                if isinstance(content, str):
                    chunks.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("text"):
                            chunks.append(part.get("text"))
                        elif isinstance(part, str):
                            chunks.append(part)
        text = "\n".join([c for c in chunks if c]).strip()
        print("DEBUG SEARCH OUTPUT (fallback):", text[:300].replace("\n"," ") + "...")
        return text
    except Exception as e:
        print("ERROR contacting OpenAI (web_search):", e)
        return ""

# ----------------- Agents -----------------

def llm_math(cfg: dict, heading: str):
    hist = _load_hist()
    seen = set(hist.get("math_hashes", []))

    system = (
        "You are a precise instructor. Produce concise daily problems for a CS/AI student. "
        "Wrap ALL mathematical expressions in $...$ for LaTeX rendering (e.g., $x^2 + y^2 = z^2$). "
        "Use proper LaTeX syntax: exponents with ^{}, fractions with \\frac{}{}, etc. "
        "Return STRICT JSON: {\"math\":[{\"problem\":\"...\",\"tip\":\"...\"}, {\"problem\":\"...\",\"tip\":\"...\"}]}"
    )

    user = (
        "Generate 2-3 problems with mathematical expressions properly wrapped in $...$. "
        "Avoid duplicates. Existing SHA1 hashes: "
        + ", ".join(list(seen)[-20:])  # Only show last 20 to keep prompt manageable
    )

    txt = _call_chat(
        [{"role":"system","content":system},
         {"role":"user","content":user}],
        model="gpt-4o-mini",
        temp=0.35
    )

    data = _extract_json(txt) or {}
    problems = data.get("math") or []

    items = []
    new_hashes = []

    # Ensure we get exactly 2 problems: one computational, one proof
    if len(problems) >= 2:
        problems = problems[:2]  # Take only first 2
    
    problem_types = ["Computational Problem", "Proof Problem"]
    
    for idx, obj in enumerate(problems):
        prob = (obj.get("problem") or "").strip()
        tip  = (obj.get("tip") or "").strip()
        if not prob:
            continue

        h = _sha(prob.lower())
        if h in seen:
            continue
        new_hashes.append(h)

        # Label problems by type
        title = problem_types[idx] if idx < len(problem_types) else "Math"
        
        # Keep LaTeX expressions with $...$ in the rendered HTML
        items.append({
            "title": title,
            "rendered": f"{prob}<br><em>Tip:</em> {tip}"
        })

    if not items:
        return {"heading": heading, "items":[{"title":"Math (fallback)", "rendered": txt}]}

    hist["math_hashes"] = (hist.get("math_hashes", []) + new_hashes)[-200:]
    _save_hist(hist)

    return {"heading": heading, "items": items}

def llm_bible(cfg: dict, heading: str):
    hist = _load_hist()
    recent = hist.get("bible_refs", [])
    system = (
        "Return a 1-3 verse King James Version Bible excerpt (public domain). Return STRICT JSON: {\"bible\":{\"reference\":\"...\",\"text\":\"...\"}}"
    )
    user = "Provide one short verse (1–3 verses). Avoid these refs: " + ", ".join(recent[-20:])
    txt = _call_chat([{"role":"system","content":system},{"role":"user","content":user}], model="gpt-4o-mini", temp=0.2)
    data = _extract_json(txt) or {}
    b = data.get("bible") or {}
    ref = (b.get("reference") or "").strip()
    text = (b.get("text") or "").strip()
    if not ref or not text:
        return {"heading": heading, "items":[{"title":"Bible (fallback)", "rendered": txt or "No verse."}]}
    hist["bible_refs"] = (recent + [ref])[-60:]
    _save_hist(hist)
    return {"heading": heading, "items":[{"title": ref, "rendered": f"{ref} — {text}"}]}

def llm_horoscope(cfg: dict, heading: str):
    hist = _load_hist()
    today = datetime.date.today().isoformat()

    system = (
        "You are a precise, psychologically grounded astrologer. "
        "Base interpretations on this birth data: 21 Oct 1990, 16:07, Odense, Denmark. "
        "Focus on natal themes consistent with late-Libra Sun, likely water-rising, Venus/Mercury influence. "
        "Include CURRENT TRANSITS and how they interact with the natal placements. "
        "Return STRICT JSON ONLY:\n"
        "{\"horoscope\":{\"daily\":\"...\",\"week\":\"...\"}}"
    )

    user = (
        "Provide a grounded daily interpretation (80–120 words) and a 1-line guidance for the week. "
        "No mystical exaggeration — psychological astrology only. "
        "Birth data again: 21 Oct 1990, 16:07 Odense Denmark."
    )

    txt = _call_chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": user}],
        model="gpt-4o-mini",
        temp=0.35
    )

    data = _extract_json(txt) or {}
    h = data.get("horoscope") or {}
    daily = (h.get("daily") or "").strip()
    week = (h.get("week") or "").strip()

    if not daily:
        return {"heading": heading, "items": [{"title": "Horoscope (fallback)", "rendered": txt}]}

    hist["last_horoscope_date"] = today
    _save_hist(hist)
    return {"heading": heading, "items": [{"title": "Today", "rendered": f"{daily}<br><br><strong>Week:</strong> {week}"}]}

# ----------------- Search-driven agent -----------------

def llm_search(cfg: dict, heading: str):
    """
    Live web search using the OpenAI web_search_preview tool.
    Supports schema: grocery_prices, mma_news, science_spirit, good_news, bullets.
    """
    schema = cfg.get("schema", "bullets")
    query = cfg.get("query", "")
    purpose = cfg.get("purpose", "")
    model = cfg.get("model", "gpt-4o-mini")

    # Strict system prompts for each schema
    if schema == "grocery_prices":
        sys = (
            "You are a live web researcher for Danish grocery prices. "
            "Search for CURRENT offers (valid this week) for these specific items:\n"
            "- Æg (eggs)\n"
            "- Hakket oksekød (ground beef)\n"
            "- Peanut butter\n"
            "- Kylling (chicken)\n"
            "- Hakket kylling (ground chicken)\n"
            "- Græsk yoghurt (Greek yogurt)\n\n"
            "Find the CHEAPEST current prices across Danish supermarkets (Netto, Rema 1000, Føtex, Bilka, Lidl, Aldi, etc.).\n"
            "Return STRICT JSON: {\"grocery_prices\":[{\"item\":\"...\",\"store\":\"...\",\"price_dkk\":123.45,"
            "\"observed_date\":\"YYYY-MM-DD\",\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}\n"
            "Only include items that are currently on sale/discount this week."
        )
    elif schema == "mma_news":
        sys = (
            "You are an MMA researcher. Return STRICT JSON with events from today or last 3 days: "
            "{\"mma\":[{\"event\":\"...\",\"date\":\"YYYY-MM-DD\",\"headline\":\"...\",\"detail\":\"...\",\"odds\":\"...\",\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}"
        )
    elif schema == "science_spirit":
        sys = (
            "Find recent peer-reviewed or preprint works linking quantum/information and consciousness/spirituality. "
            "Return STRICT JSON: {\"studies\":[{\"title\":\"...\",\"authors\":\"...\",\"venue_or_institution\":\"...\",\"date\":\"YYYY-MM-DD\",\"summary\":\"...\",\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}"
        )
    elif schema == "good_news":
        sys = (
            "Return optimistic/positive world news from today or the last 3 days in STRICT JSON: "
            "{\"news\":[{\"headline\":\"...\",\"date\":\"YYYY-MM-DD\",\"what_happened\":\"...\",\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}"
        )
    else:
        sys = "Return compact verifiable bullets with https URLs in JSON: {\"bullets\":[\"...\",\"...\"]}"

    user = f"Search query: {query}\nPurpose: {purpose}\nToday: {TODAY}"

    # call web search
    raw = _call_web_search(sys, user, model=model, temp=0.15)
    data = _extract_json(raw) or {}
    items: List[Dict[str, Any]] = []

    def add_it(title: str, rendered: str, img: Optional[str] = None):
        items.append({"title": title, "rendered": rendered, "image_url": img or None})

    # parse schemas
    if schema == "grocery_prices":
        for g in (data.get("grocery_prices") or []):
            item = (g.get("item") or "").strip()
            store = (g.get("store") or "").strip()
            price = g.get("price_dkk")
            date = (g.get("observed_date") or "").strip()
            url = (g.get("source_url") or "").strip()
            img = (g.get("image_url") or "").strip()
            # coerce price
            try:
                price_val = float(price)
            except Exception:
                price_val = None
            # accept weekly offers (within 7 days)
            if item and store and price_val is not None and url and _is_recent(date, 7):
                html = (f"<strong>{item}</strong> — {store} — <strong>{price_val:.2f} DKK</strong> — {date} — "
                        f"<a href='{url}' style='color:#00f0ff;'>view source</a>")
                add_it(f"{item} — {store}", html, img or None)

    elif schema == "mma_news":
        for m in (data.get("mma") or []):
            ev = (m.get("event") or "").strip()
            dt = (m.get("date") or "").strip()
            hl = (m.get("headline") or "").strip()
            de = (m.get("detail") or "").strip()
            od = (m.get("odds") or "").strip()
            url = (m.get("source_url") or "").strip()
            img = (m.get("image_url") or "").strip()
            if url and (dt == TODAY or _is_recent(dt, 3)) and (ev or hl):
                rendered = f"<strong>{ev or hl}</strong> — {dt}<br>{de}{('<br>Odds: '+od) if od else ''}<br><a href='{url}' style='color:#00f0ff;'>source</a>"
                add_it(ev or hl, rendered, img or None)

    elif schema == "science_spirit":
        for s in (data.get("studies") or []):
            title = (s.get("title") or "").strip()
            authors = (s.get("authors") or "").strip()
            venue = (s.get("venue_or_institution") or "").strip()
            dt = (s.get("date") or "").strip()
            summ = (s.get("summary") or "").strip()
            url = (s.get("source_url") or "").strip()
            img = (s.get("image_url") or "").strip()
            if title and url and dt:
                rendered = f"<strong>{title}</strong><br>{authors} — {venue} — {dt}<br>{summ}<br><a href='{url}' style='color:#00f0ff;'>source</a>"
                add_it(title, rendered, img or None)

    elif schema == "good_news":
        for n in (data.get("news") or []):
            hl = (n.get("headline") or "").strip()
            dt = (n.get("date") or "").strip()
            wh = (n.get("what_happened") or "").strip()
            url = (n.get("source_url") or "").strip()
            img = (n.get("image_url") or "").strip()
            if hl and url and (_is_recent(dt, 3) or dt == TODAY):
                rendered = f"<strong>{hl}</strong> — {dt}<br>{wh}<br><a href='{url}' style='color:#00f0ff;'>source</a>"
                add_it(hl, rendered, img or None)

    else:
        for b in (data.get("bullets") or []):
            if b:
                add_it(heading, b, None)

    # if nothing parsed, fallback to raw output (so the section isn't empty)
    if not items:
        if raw:
            items.append({"title": heading, "rendered": raw, "image_url": None})
        else:
            items.append({"title": heading, "rendered": "No results found.", "image_url": None})

    return {"heading": heading, "items": items}
