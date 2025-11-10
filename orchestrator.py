# orchestrator.py
from typing import List, Optional
from providers import search, llm
from providers import Section

AGENTS = {
    "search":  search.fetch,
    "llm_search": llm.llm_search,
    "llm_math": llm.llm_math,
    "llm_bible": llm.llm_bible,
    "llm_horoscope": llm.llm_horoscope,
}

def _run_agent(agent_cfg: dict, heading: str) -> Optional[Section]:
    fn = AGENTS.get(agent_cfg.get("type"))
    if not fn:
        return {"heading": heading, "items":[{"rendered": f"Unknown agent type: {agent_cfg.get('type')}"}]}
    try:
        return fn(agent_cfg, heading)
    except Exception as e:
        return {"heading": heading, "items":[{"rendered": f"⚠️ Error running {agent_cfg.get('type')}: {e}"}]}
