# app/tools/search_stub.py
from __future__ import annotations
from typing import Any, Dict
import json
import os

from tools.role_matcher import load_kb


def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """
    Safe getter that works with both Pydantic models (attributes) and dicts (keys).
    """
    # Attribute path
    try:
        return getattr(obj, name)
    except Exception:
        pass
    # Dict path
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def load_role_template(path: str) -> Dict[str, Any]:
    """
    Load a role template JSON from disk. Caller is responsible for passing
    a valid existing file path.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_template_for_role(role: Any) -> Dict[str, Any]:
    """
    Robustly load the template for a given role (RoleSpec or dict).

    Resolution order:
      1) If the role already has a 'file' path that exists → load that.
      2) Else, look up by 'role_id' in the KB.
      3) Else, look up by 'title' (case-insensitive) in the KB.
      4) Else, return a minimal fallback template so the editor still renders.

    This avoids AttributeError when the role is a dict (added via "Add role").
    """
    # 1) Explicit file on the role
    file_path = _get_field(role, "file")
    if isinstance(file_path, str) and os.path.exists(file_path):
        return load_role_template(file_path)

    # 2) Try to resolve from the knowledge base
    kb = load_kb()  # each record: {"id","title","file",...}

    # 2a) by role_id
    role_id = _get_field(role, "role_id")
    rec = None
    if role_id:
        rec = next((r for r in kb if r.get("id") == role_id), None)

    # 2b) by title (case-insensitive)
    if rec is None:
        title = _get_field(role, "title")
        if isinstance(title, str) and title.strip():
            t_norm = title.strip().lower()
            rec = next(
                (r for r in kb if str(r.get("title", "")).strip().lower() == t_norm),
                None,
            )

    # If we found a KB record with a file, load it
    if rec and isinstance(rec.get("file"), str) and os.path.exists(rec["file"]):
        return load_role_template(rec["file"])

    # 4) Fallback minimal template so the UI doesn't crash
    #    (keeps keys your editor expects)
    return {
        "title": _get_field(role, "title"),
        "function": _get_field(role, "function"),
        "seniority": _get_field(role, "seniority", "Mid"),
        "mission": None,
        "skills": {"must": [], "nice": []},
        "responsibilities": [],
        "benefits": ["Equity", "Flexible work", "Growth opportunities"],
    }
