# orchestrator.py
import time
import yaml
from typing import List
from jinja2 import Environment, FileSystemLoader
from providers import Section
from providers import search, llm

# Map agent "type" (declared in topics.yml) to the correct provider function
AGENTS = {
    "search": search.fetch,
    "llm_math": llm.llm_math,
    "llm_bible": llm.llm_bible,
    "llm_horoscope": llm.llm_horoscope,
}

def _run_agent(agent_cfg: dict, heading: str) -> Section | None:
    """Safely execute a provider agent."""
    agent_type = agent_cfg.get("type")
    fn = AGENTS.get(agent_type)
    if not fn:
        return {"heading": heading, "items": [
            {"rendered": f"Unknown agent type: {agent_type}"}]}
    try:
        return fn(agent_cfg, heading)
    except Exception as e:
        return {"heading": heading, "items": [
            {"rendered": f"⚠️ Error running {agent_type}: {e}"}]}

def build_digest() -> str:
    """Read topics.yml, run each section, render the full email text."""
    with open("topics.yml", "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)

    sections: List[Section] = []
    max_items = int(spec.get("defaults", {}).get("max_items_per_section", 5))

    for topic in spec.get("topics", []):
        heading = topic.get("heading", "Untitled Section")
        agents = topic.get("agents", [])
        combined_items = []

        for agent in agents:
            sec = _run_agent(agent, heading)
            if sec and sec.get("items"):
                combined_items.extend(sec["items"])

        if combined_items:
            combined_items = combined_items[:max_items]
            sections.append({"heading": heading, "items": combined_items})

    # Render email template
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("email.txt.j2")
    body = template.render(
        date=time.strftime("%Y-%m-%d"),
        sections=sections
    )
    return body
