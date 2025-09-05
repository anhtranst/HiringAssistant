# app/tools/role_matcher.py
from __future__ import annotations
import json, re, unicodedata, uuid, tempfile, shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from rapidfuzz import fuzz, process

DATA_DIR = Path("data")
KB_CORE_PATH = DATA_DIR / "roles_kb.json"
KB_CUSTOM_PATH = DATA_DIR / "roles_kb_custom.json"
ROLE_KNOWLEDGE_DIR = DATA_DIR / "role_knowledge"
ROLE_KNOWLEDGE_CUSTOM_DIR = DATA_DIR / "role_knowledge_custom"

# ---------- Helpers ----------
_SPLIT = re.compile(r"[,\n;/|]+|\b(?:and|plus|with|for)\b", re.I)
HINT_VERBS = re.compile(r"\b(hire|hiring|need|looking for|search(?:ing)? for|recruit|open(?:ing)?)\b", re.I)

def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().strip()
    s = re.sub(r"[^\w\s/#\+\-]", " ", s)  # keep c#, c++, etc.
    s = re.sub(r"\s+", " ", s)
    return s

def _slugify(title: str) -> str:
    s = _normalize(title)
    s = s.replace("+", "plus").replace("#", "sharp")
    s = re.sub(r"[^\w]+", "_", s).strip("_")
    return s

def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(path.parent)) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    shutil.move(str(tmp_path), str(path))

# ---------- KB load/merge ----------
def _augment(rec: Dict[str, Any]) -> Dict[str, Any]:
    rec = dict(rec)
    rec["norm_title"] = _normalize(rec["title"])
    rec["norm_aliases"] = [_normalize(a) for a in rec.get("aliases", [])]
    rec["match_corpus"] = [rec["norm_title"], *rec["norm_aliases"]]
    return rec

def load_kb() -> List[Dict[str, Any]]:
    core = json.loads(KB_CORE_PATH.read_text(encoding="utf-8")) if KB_CORE_PATH.exists() else []
    custom = json.loads(KB_CUSTOM_PATH.read_text(encoding="utf-8")) if KB_CUSTOM_PATH.exists() else []
    kb = [*_map_files(core), *_map_files(custom)]
    return [_augment(r) for r in kb]

def _map_files(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Ensure "file" paths are relative to data/
    out = []
    for r in items:
        r = dict(r)
        fp = Path("data") / r["file"] if not str(r["file"]).startswith("data/") else Path(r["file"])
        r["file"] = str(fp.as_posix())
        out.append(r)
    return out

# ---------- Extraction ----------
def extract_candidate_phrases(prompt: str) -> List[str]:
    p = _normalize(prompt)
    parts = _SPLIT.split(p) if HINT_VERBS.search(p) else [p]
    cand = [c.strip() for c in parts if 2 <= len(c.split()) <= 7]
    # plural → singular (cheap heuristic)
    cand = [re.sub(r"s\b", "", c) for c in cand]
    seen, out = set(), []
    for c in cand:
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out or [p]

# ---------- Matching ----------
@dataclass
class MatchResult:
    status: str                   # "match" | "suggest" | "unknown"
    role_id: Optional[str]
    title: str
    file: Optional[str]
    confidence: float
    suggestions: List[Dict[str, Any]]

def match_one(phrase: str, kb: List[Dict[str, Any]], fuzzy_threshold: int = 88) -> MatchResult:
    choices = []
    for r in kb:
        for txt in r["match_corpus"]:
            choices.append((txt, r))  # (normalized text, role record)

    if not choices:
        return MatchResult("unknown", None, phrase.title(), None, 0.0, [])

    # Best single
    best = process.extractOne(phrase, [c[0] for c in choices], scorer=fuzz.token_set_ratio)
    score = float(best[1]) if best else 0.0
    rec = choices[best[2]][1] if best else None

    # Top-K (dedup by role_id)
    topk = process.extract(phrase, [c[0] for c in choices], scorer=fuzz.token_set_ratio, limit=10)
    agg: Dict[str, float] = {}
    for _, s, idx in topk:
        rid = choices[idx][1]["id"]
        agg[rid] = max(agg.get(rid, 0.0), float(s))
    suggestions = sorted(
        ({"role_id": rid, "title": next(r for r in kb if r["id"] == rid)["title"], "score": sc/100.0}
         for rid, sc in agg.items()),
        key=lambda x: -x["score"]
    )[:3]

    if rec and score >= fuzzy_threshold:
        return MatchResult("match", rec["id"], rec["title"], rec["file"], score/100.0, suggestions)
    elif suggestions:
        return MatchResult("suggest", None, phrase.title(), None, score/100.0, suggestions)
    else:
        return MatchResult("unknown", None, phrase.title(), None, score/100.0, [])

# ---------- Save custom role ----------
def save_custom_role(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload must include: title, function, seniority (optional), aliases, skills.must, skills.nice,
    responsibilities (list), interview_loop (list)
    """
    title = payload["title"].strip()
    slug = _slugify(title)
    # ensure unique slug (very simple)
    suffix = 1
    final_slug = slug
    while (ROLE_KNOWLEDGE_CUSTOM_DIR / f"{final_slug}.json").exists():
        suffix += 1
        final_slug = f"{slug}_{suffix}"

    # build template object (keeps same shape as curated)
    tpl = {
        "id": final_slug,
        "title": title,
        "aliases": payload.get("aliases", []),
        "function": payload.get("function", "Engineering"),
        "seniority": payload.get("seniority", None),
        "skills": {
            "must": payload.get("skills", {}).get("must", []),
            "nice": payload.get("skills", {}).get("nice", [])
        },
        "responsibilities": payload.get("responsibilities", []),
        "interview_loop": payload.get("interview_loop", ["Screen","Tech Deep-Dive","System Design","Founder Chat","References"]),
        "sourcing_tags": payload.get("sourcing_tags", []),
        "approved": False,
        "version": 1
    }

    # Write template file
    file_rel = f"role_knowledge_custom/{final_slug}.json"
    file_abs = DATA_DIR / file_rel
    _atomic_write(file_abs, json.dumps(tpl, ensure_ascii=False, indent=2))

    # Append to custom KB index
    kb_custom = json.loads(KB_CUSTOM_PATH.read_text(encoding="utf-8")) if KB_CUSTOM_PATH.exists() else []
    kb_custom.append({
        "id": final_slug,
        "title": title,
        "aliases": tpl["aliases"],
        "file": file_rel,
        "function": tpl["function"],
        "approved": False
    })
    _atomic_write(KB_CUSTOM_PATH, json.dumps(kb_custom, ensure_ascii=False, indent=2))

    return {"id": final_slug, "file": f"data/{file_rel}", "title": title}
