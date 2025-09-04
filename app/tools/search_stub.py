import json
import os

DATA_DIR = os.path.join("data", "role_knowledge")

def _load_json(fname: str) -> dict:
    path = os.path.join(DATA_DIR, fname)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def role_knowledge(title: str) -> dict:
    t = title.strip().lower()
    if "founding engineer" in t:
        return _load_json("founding_engineer.json")
    if "genai intern" in t or "gen ai intern" in t:
        return _load_json("genai_intern.json")
    # default to founding_engineer facts if unknown
    return _load_json("founding_engineer.json")
