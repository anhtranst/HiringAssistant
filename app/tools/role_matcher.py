# app/tools/role_matcher.py
from __future__ import annotations
import os
import json, re, unicodedata, tempfile, shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from rapidfuzz import fuzz, process
from datetime import datetime
from tools.llm_extractor import extract_roles_with_llm

# ---------- Paths (repo-root anchored) ----------
REPO_ROOT = Path(__file__).resolve().parents[2]  # app/tools -> app -> <repo root>
DATA_DIR = REPO_ROOT / "data"
KB_CORE_PATH = DATA_DIR / "roles_kb.json"
KB_CUSTOM_PATH = DATA_DIR / "roles_kb_custom.json"
ROLE_KNOWLEDGE_DIR = DATA_DIR / "role_knowledge"
ROLE_KNOWLEDGE_CUSTOM_DIR = DATA_DIR / "role_knowledge_custom"

# ---------- Helpers ----------
# Split on commas, sentence punctuation, and conjunctions.
# Avoid splitting on "for" (e.g., "engineer for platform" should stay together).
_SPLIT = re.compile(r"[,\.\?\!\n;/|]+|\b(?:and|or|plus|with)\b", re.I)

# Head nouns that commonly end role titles
_HEAD_NOUNS = {
    "engineer","developer","intern","designer","analyst","manager",
    "scientist","architect","lead","specialist","pm","producer",
    "marketer","researcher","administrator","technician","consultant"
}

# Leading filler words we strip at the start of each segment
_STOP_HEAD = {
    "i","we","you","they","to","a","an","the","my","our","your",
    "need","needs","needing","hire","hiring","looking","search","searching",
    "recruit","recruiting","open","opening","want","wanted",
    "someone","help","please","thanks","thank","thankyou","thank-you","can","could","would"
}

def _clean_head_tokens(text: str, max_len: int = 7) -> str:
    """Trim leading filler tokens and, if still long, drop from the left to keep the noun tail."""
    toks = [t for t in text.strip().split() if t]
    while toks and toks[0] in _STOP_HEAD:
        toks.pop(0)
    while len(toks) > max_len:  # keep the rightmost words (role tail)
        toks.pop(0)
    return " ".join(toks).strip()

def _attach_missing_head_noun(cands: list[str]) -> list[str]:
    """
    If a candidate is just a modifier (e.g., 'backend') and an adjacent candidate
    ends with a known head noun (e.g., '... engineer'), attach that noun.
    """
    out: list[str] = []
    last_head: str | None = None

    def head_noun(s: str) -> str | None:
        w = s.split()[-1] if s else ""
        return w if w in _HEAD_NOUNS else None

    for i, c in enumerate(cands):
        base = c
        words = base.split()
        if len(words) <= 2 and head_noun(base) is None:
            ahead = cands[i+1] if i + 1 < len(cands) else ""
            ahead_head = head_noun(ahead)
            noun = ahead_head or last_head
            if noun:
                base = f"{base} {noun}"
        h = head_noun(base)
        if h:
            last_head = h
        out.append(base)
    return out

def _heuristic_titles_from_prompt(prompt: str) -> list[str]:
    """
    Heuristic extractor that supports arbitrary lists:
      - **Split BEFORE normalize** so commas/and/or are respected.
      - Trim leading filler words.
      - Reconstruct lone modifiers ('backend') by borrowing neighbor head nouns.
      - Deduplicate while preserving order.
    """
    # 1) Split using the original text so punctuation is still present
    parts = [seg for seg in _SPLIT.split(prompt) if seg and seg.strip()]

    # 2) Normalize & clean each segment independently
    cands = []
    for part in parts:
        norm = _normalize(part)  # lowercases, trims, strips extra punctuation
        # remove very common polite tails within the segment
        norm = re.sub(r"\b(can you help|please|thanks|thank you)\b", " ", norm)
        cand = _clean_head_tokens(norm, max_len=7)
        if 1 <= len(cand.split()) <= 7:
            cands.append(cand)

    if not cands:
        # final fallback: normalize the whole thing and keep the tail
        whole = _clean_head_tokens(_normalize(prompt), max_len=7)
        return [whole] if whole else []

    # 3) Reconstruct missing nouns for lone modifiers when possible
    cands = _attach_missing_head_noun(cands)

    # 4) Deduplicate while preserving order
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out

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
    # add metadata convenience
    rec["is_custom"] = "role_knowledge_custom/" in str(rec.get("file", ""))
    # created_at may be missing for curated or older custom entries
    rec["created_at"] = rec.get("created_at")
    return rec

def _map_files(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Ensure "file" paths are prefixed with data/
    out = []
    for r in items:
        r = dict(r)
        fp = Path("data") / r["file"] if not str(r["file"]).startswith("data/") else Path(r["file"])
        r["file"] = str(fp.as_posix())
        out.append(r)
    return out

def load_kb() -> List[Dict[str, Any]]:
    core = json.loads(KB_CORE_PATH.read_text(encoding="utf-8")) if KB_CORE_PATH.exists() else []
    custom = json.loads(KB_CUSTOM_PATH.read_text(encoding="utf-8")) if KB_CUSTOM_PATH.exists() else []
    # order here doesn't matter because we return top-3 suggestions (UI lets user choose)
    kb = [*_map_files(core), *_map_files(custom)]
    return [_augment(r) for r in kb]

# ---------- Extraction ----------
def extract_candidate_phrases(prompt: str, use_llm: bool | None = None) -> List[str]:
    """
    LLM-first (optional) → heuristic fallback that handles 1..N roles.
    """
    should_use_llm = (
        bool(use_llm)
        if use_llm is not None
        else bool(os.getenv("OPENAI_API_KEY"))
    )

    if should_use_llm:
        try:
            roles, _meta = extract_roles_with_llm(prompt)
            titles = [r["title"] for r in roles if r.get("title")]
            if titles:
                return titles
        except Exception:
            pass

    return _heuristic_titles_from_prompt(prompt)

# ---------- Matching ----------
@dataclass
class MatchResult:
    status: str                   # "suggest" | "unknown"
    role_id: Optional[str]
    title: str
    file: Optional[str]
    confidence: float
    suggestions: List[Dict[str, Any]]  # [{role_id,title,score,is_custom,created_at}]

def match_one(phrase: str, kb: List[Dict[str, Any]], fuzzy_threshold: int = 88) -> MatchResult:
    """
    NEW behavior:
    Always return top-3 suggestions and let the UI decide.
    If none found above a weak threshold, return 'unknown'.
    """
    choices = []
    for r in kb:
        for txt in r["match_corpus"]:
            choices.append((txt, r))  # (normalized text, role record)

    if not choices:
        return MatchResult("unknown", None, phrase.title(), None, 0.0, [])

    # top-10 raw, then aggregate per role id (max score per role)
    topk = process.extract(phrase, [c[0] for c in choices], scorer=fuzz.token_set_ratio, limit=10)
    if not topk:
        return MatchResult("unknown", None, phrase.title(), None, 0.0, [])

    agg: Dict[str, float] = {}
    for _, s, idx in topk:
        rid = choices[idx][1]["id"]
        agg[rid] = max(agg.get(rid, 0.0), float(s))

    # keep top-3 by score
    top3_ids = sorted(agg.items(), key=lambda x: -x[1])[:3]
    suggestions = []
    for rid, sc in top3_ids:
        rec = next(r for r in kb if r["id"] == rid)
        suggestions.append({
            "role_id": rid,
            "title": rec["title"],
            "score": sc / 100.0,
            "is_custom": bool(rec.get("is_custom")),
            "created_at": rec.get("created_at"),  # ISO string or None
        })

    # choose "confidence" as best score we saw (for display)
    best_score = (top3_ids[0][1] / 100.0) if top3_ids else 0.0

    # If nothing is even vaguely close, mark unknown
    if best_score < (fuzzy_threshold - 20) / 100.0 and not suggestions:
        return MatchResult("unknown", None, phrase.title(), None, best_score, [])

    # Always return suggest + top-3 — UI picks default
    return MatchResult("suggest", None, phrase.title(), None, best_score, suggestions)

# ---------- Save custom role ----------
def save_custom_role(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    payload must include: title, function, seniority (optional), aliases, skills.must, skills.nice,
    responsibilities (list), interview_loop (list)
    """
    title = payload["title"].strip()
    slug = _slugify(title)

    # timestamped id for easy "newest custom" selection
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    final_slug = f"{slug}__custom__{ts}"

    # build template object (keeps same shape as curated)
    created_iso = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
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
        "version": 1,
        "created_at": created_iso,
    }

    # Write template file (under <repo>/data/role_knowledge_custom/)
    file_rel = f"role_knowledge_custom/{final_slug}.json"
    file_abs = DATA_DIR / file_rel
    _atomic_write(file_abs, json.dumps(tpl, ensure_ascii=False, indent=2))

    # Append to custom KB index (now carries created_at + is_custom=true in loader)
    kb_custom = json.loads(KB_CUSTOM_PATH.read_text(encoding="utf-8")) if KB_CUSTOM_PATH.exists() else []
    kb_custom.append({
        "id": final_slug,
        "title": title,
        "aliases": tpl["aliases"],
        "file": file_rel,
        "function": tpl["function"],
        "approved": False,
        "created_at": created_iso,
    })
    _atomic_write(KB_CUSTOM_PATH, json.dumps(kb_custom, ensure_ascii=False, indent=2))

    # Return a path that your loaders already understand (prefixed with "data/")
    return {"id": final_slug, "file": f"data/{file_rel}", "title": title}
