# providers/llm.py
import json, os, hashlib, datetime
from typing import Any, Dict, List
from openai import OpenAI
from . import Item, Section

HISTORY_PATH = "data/history.json"

def _load_hist() -> Dict[str, Any]:
    if not os.path.exists(HISTORY_PATH):
        return {"math_hashes": [], "bible_refs": [], "last_horoscope_date": ""}
    with open(HISTORY_PATH, "r", encoding="utf-8") as f:
        try:
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
    """
    Returns assistant text. We ask for strict JSON and validate downstream.
    """
    client = _client()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7
    )
    return resp.choices[0].message.content.strip()

def llm_math(cfg: dict, heading: str) -> Section:
    """
    Generate 1-2 algebra/CS/AI-leaning exercises with tips.
    Avoid repetition using history hashes.
    cfg: {count: 2}
    """
    count = int(cfg.get("count", 2))
    hist = _load_hist()
    seen = set(hist.get("math_hashes", []))

    system = (
        "You generate short math practice tasks for a CS/AI learner. "
        "Focus on algebra, factoring, linear equations, simple proofs (direct, contrapositive), "
        "matrix basics (2x2 det, solving small systems), and tiny calculus snippets when helpful. "
        "Each problem must be concise (one line). Return STRICT JSON with keys: "
        "{\"math\":[{\"problem\":\"...\",\"tip\":\"...\"}, ...]} . "
        "Do not repeat any problem semantically; vary structures."
    )

    user = (
        f"Create {count} distinct problems with a relevant tip each. "
        "Target: quick morning practice. Use simple notation. "
        "Avoid problems that are identical to any in this list (by idea), here are past-hash hints: "
        f"{list(seen)[:50]}"
    )

    txt = _call_llm([{"role":"system","content":system},{"role":"user","content":user}])
    try:
        data = json.loads(txt)
        items: List[Item] = []
        new_hashes: List[str] = []
        for obj in data.get("math", [])[:count]:
            prob = obj.get("problem","").strip()
            tip  = obj.get("tip","").strip()
            if not prob:
                continue
            h = _sha(prob.lower())
            if h in seen:
                # skip repeated; we accept fewer items rather than repeat
                continue
            new_hashes.append(h)
            items.append({"title": prob, "rendered": f"{prob}\n  Tip: {tip}"})
        if new_hashes:
            # keep only last 200 hashes to limit growth
            hist["math_hashes"] = (hist.get("math_hashes", []) + new_hashes)[-200:]
            _save_hist(hist)
        return {"heading": heading, "items": items}
    except Exception as e:
        # If JSON parsing fails, return the raw text as a single item
        return {"heading": heading, "items":[{"title":"math (LLM error)", "rendered": txt}]}

def llm_bible(cfg: dict, heading: str) -> Section:
    """
    Bible excerpt of the day (public-domain wording like KJV). 
    Avoid repeating the same reference frequently.
    """
    hist = _load_hist()
    recent = hist.get("bible_refs", [])

    system = (
        "Provide a short Bible excerpt suitable for daily meditation, KJV wording (public domain). "
        "Return STRICT JSON: {\"bible\":{\"reference\":\"Book X:Y-Z\",\"text\":\"...\"}} . "
        "Avoid repeating any references in this recent list: " + ", ".join(recent[-20:])
    )
    user = "One excerpt only; 1-3 verses; spiritually strengthening; no commentary."

    txt = _call_llm([{"role":"system","content":system},{"role":"user","content":user}])
    try:
        data = json.loads(txt)
        b = data.get("bible", {})
        ref = b.get("reference","").strip()
        text = b.get("text","").strip()
        if ref:
            # keep last 60 refs
            hist["bible_refs"] = (recent + [ref])[-60:]
            _save_hist(hist)
        return {"heading": heading, "items":[{"title": ref or "Bible", "rendered": f"{ref} — {text}"}]}
    except Exception:
        return {"heading": heading, "items":[{"title":"Bible (LLM raw)", "rendered": txt}]}

def llm_horoscope(cfg: dict, heading: str) -> Section:
    """
    Daily + weekly hint based on provided birth chart data.
    No fortune-telling; keep it reflective, practical, grounded.
    """
    hist = _load_hist()
    today = datetime.date.today().isoformat()
    if hist.get("last_horoscope_date") == today:
        # already generated today (idempotent runs)
        pass

    system = (
        "You write a concise daily horoscope with one practical weekly hint. "
        "Tone: grounded, empowering, no fatalism; 70-120 words daily + one line week hint. "
        "Return STRICT JSON: {\"horoscope\":{\"daily\":\"...\",\"week\":\"...\"}}."
    )
    user = (
        "Birth: 21 Oct 1990, Odense, Denmark, 16:07 (CET). "
        "Assume a modern psychological astrology framing."
    )

    txt = _call_llm([{"role":"system","content":system},{"role":"user","content":user}])
    try:
        data = json.loads(txt)
        h = data.get("horoscope", {})
        daily = h.get("daily","").strip()
        week  = h.get("week","").strip()
        hist["last_horoscope_date"] = today
        _save_hist(hist)
        return {"heading": heading, "items":[{"title":"Today", "rendered": f"{daily}\n  Week: {week}"}]}
    except Exception:
        return {"heading": heading, "items":[{"title":"Horoscope (LLM raw)", "rendered": txt}]}
