# orchestrator.py
import os
import yaml
from datetime import date
from jinja2 import Environment, FileSystemLoader, select_autoescape

# provider modules
from providers import llm, groceries

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml", "j2"])
)

def _load_topics(spec_path="topics.yml"):
    with open(spec_path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return doc

def _run_agent(agent_cfg: dict, heading: str):
    """
    Run an agent and ALWAYS return a Section-like dict:
      {"heading": heading, "items": [...]}

    If the provider raises or returns None/invalid, return a safe fallback
    section with one item explaining the error (so email never fails).
    """
    try:
        t = agent_cfg.get("type")
        if t == "llm_math":
            sec = llm.llm_math(agent_cfg, heading)
        elif t == "llm_bible":
            sec = llm.llm_bible(agent_cfg, heading)
        elif t == "llm_horoscope":
            sec = llm.llm_horoscope(agent_cfg, heading)
        elif t == "llm_search":
            sec = llm.llm_search(agent_cfg, heading)
        elif t == "groceries":
            sec = groceries.fetch_groceries(agent_cfg, heading)
        else:
            sec = {"heading": heading, "items":[{"title":"(agent error)",
                                                  "rendered": f"Unknown agent type: {t}"}]}
        # Defensive: ensure structure is correct
        if not isinstance(sec, dict) or "items" not in sec:
            return {"heading": heading, "items":[{"title":"(agent returned invalid)", "rendered": str(sec)}]}
        return sec
    except Exception as e:
        # Log to stdout so you can see it in console/workflow logs
        import traceback, sys
        tb = traceback.format_exc()
        print(f"ERROR running agent {agent_cfg!r} for heading {heading!r}:\n{tb}", file=sys.stderr)
        return {"heading": heading, "items":[{"title":"(agent exception)","rendered": f"Agent {agent_cfg.get('type')} failed: {e}"}]}
def build_digest():
    spec = _load_topics("topics.yml")
    defaults = spec.get("defaults", {}) if isinstance(spec, dict) else {}
    topics = spec.get("topics") if isinstance(spec, dict) else spec

    sections = []
    for topic in topics:
        heading = topic.get("heading", "Untitled")
        items_accum = []
        for agent_cfg in topic.get("agents", []):
            sec = _run_agent(agent_cfg, heading)
            # sec must be a dict with "items" list; skip if malformed
            if not sec or not isinstance(sec, dict):
                # generate fallback
                items_accum.append({"title":"(agent returned nothing)","rendered": f"Agent returned: {sec}"})
                continue
            agent_items = sec.get("items") or []
            # Ensure agent_items is iterable list
            if not isinstance(agent_items, list):
                items_accum.append({"title":"(agent invalid items)","rendered": str(agent_items)})
                continue
            for it in agent_items:
                items_accum.append(it)
        # Only add section if we have items; otherwise place a placeholder
        if not items_accum:
            items_accum = [{"title":"(no items)","rendered":"No items produced for this section."}]
        sections.append({"heading": heading, "items": items_accum})

    # render template
    tmpl = env.get_template("email.html.j2")
    today = date.today().isoformat()
    html = tmpl.render(date=today, sections=sections)

    # save browser copy
    out_path = os.path.join(DATA_DIR, "digest.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Browser version saved: {out_path}")
    return html
