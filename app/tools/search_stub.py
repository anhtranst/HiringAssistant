# app/tools/search_stub.py
import json
from pathlib import Path
from typing import Dict, Any
from tools.role_matcher import load_kb

def load_role_template(file_path: str) -> Dict[str, Any]:
    p = Path(file_path)
    if not p.exists():
        repo_root = Path(__file__).resolve().parents[2]
        p = repo_root / file_path
        if not p.exists():
            p = Path(".") / file_path
    return json.loads(p.read_text(encoding="utf-8"))

def load_template_for_role(role) -> dict:
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
