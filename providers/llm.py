# providers/llm.py
import json, os, hashlib, datetime, re
from typing import Any, Dict, List, Optional
from openai import OpenAI
from . import Item, Section

HISTORY_PATH = "data/history.json"

TODAY = datetime.date.today().isoformat()

def _is_today(s: str) -> bool:
    try:
        return datetime.date.fromisoformat(s).isoformat() == TODAY
    except Exception:
        return False

def _is_recent(s: str, days: int = 3) -> bool:
    try:
        d = datetime.date.fromisoformat(s)
        return (datetime.date.today() - d).days <= days
    except Exception:
        return False

def _load_hist() -> Dict[str, Any]:
    if not os.path.exists(HISTORY_PATH):
        return {"math_hashes": [], "bible_refs": [], "last_horoscope_date": ""}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"math_hashes": [], "bible_refs": [], "last_horoscope_date": ""}

def _save_hist(hist: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def _client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def _call_llm(messages, model: str = "gpt-4o-mini") -> str:
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )
        text = resp.choices[0].message.content.strip()
        print("DEBUG: LLM raw output prefix:", text[:120].replace("\n"," ") + "...")
        return text
    except Exception as e:
        print("ERROR contacting OpenAI:", e)
        return f"LLM error: {e}"

def _extract_json(text: str) -> Optional[dict]:
    """
    Try strict JSON first; if that fails, pull the first {...} block (code fences allowed).
    """
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{"); end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        cand = text[start:end+1]
        try:
            return json.loads(cand)
        except Exception:
            cand = re.sub(r",\s*}", "}", cand)
            cand = re.sub(r",\s*]", "]", cand)
            try:
                return json.loads(cand)
            except Exception:
                return None
    return None

# ---------- Agents ----------

def llm_math(cfg: dict, heading: str) -> Section:
    count = int(cfg.get("count", 2))
    hist = _load_hist()
    seen = set(hist.get("math_hashes", []))

    system = (
        "Generate short math practice tasks for a CS/AI learner (algebra, factoring, 2×2 matrices, short proof sketches). "
        "Each problem MUST include inline LaTeX between $...$ AND a readable plain form in parentheses, e.g.: "
        "\"Solve for $x$: $3x+2=8$ (3x+2=8)\". "
        "Return STRICT JSON: {\"math\":[{\"problem\":\"...\",\"tip\":\"...\"}, ...]}."
    )
    user = (
        f"Create {count} distinct problems with a relevant tip each. "
        "Avoid problems that are semantically identical to any in this SHA1 list: "
        f"{list(seen)[:50]}"
    )

    txt = _call_llm([{"role":"system","content":system},{"role":"user","content":user}])
    data = _extract_json(txt) or {}
    items: List[Item] = []
    new_hashes: List[str] = []

    for obj in (data.get("math") or [])[:count]:
        prob = (obj.get("problem") or "").strip()
        tip  = (obj.get("tip") or "").strip()
        if not prob:
            continue
        h = _sha(prob.lower())
        if h in seen:
            continue
        new_hashes.append(h)
        items.append({"title": prob, "rendered": f"{prob}\n  Tip: {tip}"})

    if not items:
        items = [{"title":"math (fallback)", "rendered": (txt[:500] + "…") if len(txt) > 500 else txt}]

    if new_hashes:
        hist["math_hashes"] = (hist.get("math_hashes", []) + new_hashes)[-200:]
        _save_hist(hist)

    return {"heading": heading, "items": items}

def llm_bible(cfg: dict, heading: str) -> Section:
    hist = _load_hist()
    recent = hist.get("bible_refs", [])

    system = (
        "Provide a short Bible excerpt suitable for daily meditation, KJV wording (public domain). "
        "Return STRICT JSON only: {\"bible\":{\"reference\":\"Book X:Y-Z\",\"text\":\"...\"}}"
    )
    user = "One excerpt (1–3 verses). Avoid repeating any of these references: " + ", ".join(recent[-20:])

    txt = _call_llm([{"role":"system","content":system},{"role":"user","content":user}])
    data = _extract_json(txt) or {}
    b = data.get("bible") or {}
    ref = (b.get("reference") or "").strip()
    text = (b.get("text") or "").strip()
    if not ref or not text:
        return {"heading": heading, "items":[{"title":"Bible (fallback)", "rendered": (txt[:500] + "…") if len(txt) > 500 else txt}]}

    hist["bible_refs"] = (recent + [ref])[-60:]
    _save_hist(hist)
    return {"heading": heading, "items":[{"title": ref, "rendered": f"{ref} — {text}"}]}

def llm_search(cfg: dict, heading: str) -> Section:
    """
    Schema-driven search via LLM. Requires URLs; for time-sensitive items we accept TODAY or last 3 days.
    Supports optional image_url for display in the template.
    """
    schema  = cfg.get("schema", "fallback_bullets")
    query   = cfg.get("query", "")
    purpose = cfg.get("purpose", "")
    model   = cfg.get("model", "gpt-4o")

    if schema == "grocery_prices":
        sys = (
            "You are a precise data curator. Return only verifiable Danish grocery prices that are valid TODAY. "
            "Each item MUST include item name, store, price in DKK (numeric), observed_date (YYYY-MM-DD), source_url (https), "
            "and, if available, a product image_url (https). If you cannot verify TODAY with a working URL, omit the item. "
            "Return STRICT JSON ONLY:\n"
            "{\"grocery_prices\":[{\"item\":\"...\",\"store\":\"...\",\"price_dkk\":123.45,"
            "\"observed_date\":\"YYYY-MM-DD\",\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}"
        )
        user = f"Today is {TODAY}. Items: {', '.join(cfg.get('items', []))}. Context: {query}. Goal: {purpose}."

    elif schema == "mma_news":
        sys = (
            "You are an MMA analyst. Provide only facts valid TODAY: next UFC event name/date, confirmed card changes, odds if published, major headlines. "
            "Each item MUST include date (YYYY-MM-DD), source_url (https), and, if available, an event poster image_url (https). Do not guess. "
            "Return STRICT JSON ONLY:\n"
            "{\"mma\":[{\"event\":\"...\",\"date\":\"YYYY-MM-DD\",\"headline\":\"...\",\"detail\":\"...\","
            "\"odds\":\"...\",\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}"
        )
        user = f"Today is {TODAY}. Topic: {query}. Goal: {purpose}."

    elif schema == "science_spirit":
        sys = (
            "Return recent, citable studies linking quantum/information and consciousness/spirituality. "
            "Each item MUST include title, authors or institution, date (YYYY-MM-DD), and a URL (doi/arXiv/journal https). "
            "If a relevant figure or cover image exists, include image_url (https). Prefer TODAY; otherwise the most recent with exact date. "
            "Return STRICT JSON ONLY:\n"
            "{\"studies\":[{\"title\":\"...\",\"authors\":\"...\",\"venue_or_institution\":\"...\",\"date\":\"YYYY-MM-DD\","
            "\"summary\":\"...\",\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}"
        )
        user = f"Today is {TODAY}. Topic: {query}. Goal: {purpose}."

    elif schema == "good_news":
        sys = (
            "Return optimistic world news with real facts. Each item MUST include date (YYYY-MM-DD) and a reputable source_url (https). "
            "If a relevant news photo exists, include image_url (https). Prefer TODAY. "
            "Return STRICT JSON ONLY:\n"
            "{\"news\":[{\"headline\":\"...\",\"date\":\"YYYY-MM-DD\",\"what_happened\":\"...\","
            "\"source_url\":\"https://...\",\"image_url\":\"https://...\"}]}"
        )
        user = f"Today is {TODAY}. Topic: {query}. Goal: {purpose}."

    else:
        sys = (
            "Return compact, verifiable bullets with URLs. If uncertain, output an empty list. "
            "STRICT JSON ONLY: {\"bullets\":[\"...\",\"...\"]}"
        )
        user = f"Today is {TODAY}. Topic: {query}. Goal: {purpose}."

    txt  = _call_llm([{"role":"system","content":sys},{"role":"user","content":user}], model)
    data = _extract_json(txt) or {}
    items: List[Item] = []

    if schema == "grocery_prices":
        for g in (data.get("grocery_prices") or []):
            item = (g.get("item") or "").strip()
            store = (g.get("store") or "").strip()
            price = g.get("price_dkk")
            date  = (g.get("observed_date") or "").strip()
            url   = (g.get("source_url") or "").strip()
            img   = (g.get("image_url") or "").strip()
            if item and store and isinstance(price,(int,float)) and url and _is_today(date):
                items.append({
                    "title": f"{item} — {store}",
                    "rendered": (f"<strong>{item}</strong> — {store} — "
                                 f"<strong>{price:.2f} DKK</strong> — {date} — "
                                 f"<a href='{url}' style='color:#00f0ff;'>source</a>"),
                    "image_url": img or None
                })

    elif schema == "mma_news":
        for m in (data.get("mma") or []):
            ev  = (m.get("event") or "").strip()
            dt  = (m.get("date") or "").strip()
            hl  = (m.get("headline") or "").strip()
            de  = (m.get("detail") or "").strip()
            od  = (m.get("odds") or "").strip()
            url = (m.get("source_url") or "").strip()
            img = (m.get("image_url") or "").strip()
            if url and _is_recent(dt, 3) and (ev or hl):
                items.append({
                    "title": ev or hl,
                    "rendered": (f"<strong>{ev or hl}</strong> — {dt}<br>{de}"
                                 f"{('<br>Odds: '+od) if od else ''}<br>"
                                 f"<a href='{url}' style='color:#00f0ff;'>source</a>"),
                    "image_url": img or None
                })

    elif schema == "science_spirit":
        for s in (data.get("studies") or []):
            title   = (s.get("title") or "").strip()
            authors = (s.get("authors") or "").strip()
            venue   = (s.get("venue_or_institution") or "").strip()
            dt      = (s.get("date") or "").strip()
            summ    = (s.get("summary") or "").strip()
            url     = (s.get("source_url") or "").strip()
            img     = (s.get("image_url") or "").strip()
            if title and url and dt:
                items.append({
                    "title": title,
                    "rendered": (f"<strong>{title}</strong><br>{authors} — {venue} — {dt}<br>{summ}<br>"
                                 f"<a href='{url}' style='color:#00f0ff;'>source</a>"),
                    "image_url": img or None
                })

    elif schema == "good_news":
        for n in (data.get("news") or []):
            hl  = (n.get("headline") or "").strip()
            dt  = (n.get("date") or "").strip()
            wh  = (n.get("what_happened") or "").strip()
            url = (n.get("source_url") or "").strip()
            img = (n.get("image_url") or "").strip()
            if hl and url and _is_recent(dt, 3):
                items.append({
                    "title": hl,
                    "rendered": (f"<strong>{hl}</strong> — {dt}<br>{wh}<br>"
                                 f"<a href='{url}' style='color:#00f0ff;'>source</a>"),
                    "image_url": img or None
                })

    else:
        for b in (data.get("bullets") or []):
            if b:
                items.append({"title": heading, "rendered": b})

    return {"heading": heading, "items": items}

def llm_horoscope(cfg: dict, heading: str) -> Section:
    hist = _load_hist()
    today = datetime.date.today().isoformat()

    system = (
        "You are a precise, psychologically grounded astrologer. "
        "Base interpretations on this birth data: 21 Oct 1990, 16:07, Odense, Denmark. "
        "Focus on consistent natal themes and current transit motifs. "
        "Deliver one concise daily focus (80–120 words) and one actionable week hint (1 line). "
        "Return STRICT JSON only: {\"horoscope\":{\"daily\":\"...\",\"week\":\"...\"}}."
    )
    user = "Birth: 21 Oct 1990, Odense, Denmark, 16:07 (CET). Psychological astrology framing."

    txt = _call_llm([{"role":"system","content":system},{"role":"user","content":user}])
    data = _extract_json(txt) or {}
    h = data.get("horoscope") or {}
    daily = (h.get("daily") or "").strip()
    week  = (h.get("week") or "").strip()

    if not daily:
        return {"heading": heading, "items":[{"title":"Horoscope (fallback)", "rendered": (txt[:500] + "…") if len(txt) > 500 else txt}]}

    hist["last_horoscope_date"] = today
    _save_hist(hist)
    return {"heading": heading, "items":[{"title":"Today", "rendered": f"{daily}\n  Week: {week}"}]}
