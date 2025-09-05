import json
import os
from pathlib import Path
from typing import Dict, Any
from tools.role_matcher import load_kb

def load_role_template(file_path: str) -> Dict[str, Any]:
    """
    file_path comes from RoleSpec.file (e.g.,
    'data/role_knowledge/founding_engineer.json'
    or 'data/role_knowledge_custom/ai_agent_orchestrator.json').
    """
    p = Path(file_path)
    if not p.exists():
        # try relative to repo root
        p = Path(".") / file_path
    return json.loads(p.read_text(encoding="utf-8"))

def load_template_for_role(role) -> dict:
    """
    Given a RoleSpec (or dict-like), resolve its template JSON.
    1. Prefer the file path set by intake (works for curated + custom).
    2. Fallback: lookup by role_id or title in KB.
    """
    if getattr(role, "file", None):
        return load_role_template(role.file)

    kb = load_kb()
    rec = next(
        (r for r in kb
         if r["id"] == getattr(role, "role_id", None)
         or r["title"].lower() == role.title.lower()),
        None
    )
    return load_role_template(rec["file"]) if rec else {}