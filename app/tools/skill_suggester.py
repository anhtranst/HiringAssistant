# app/tools/skill_suggester.py
"""
Context-aware skill/mission suggester.

Key improvements in this version:
- Accepts optional `drafts` to POLISH existing text or GENERATE when blank.
- Robustly normalizes model outputs:
    * If the model returns strings (not lists) for must/nice/resp, we split them
      into proper arrays (by commas, newlines, bullet chars, etc.) before returning.
    * UI layers can safely render using simple joiners.
- Always returns a mission string (model → fallback composer).
"""

import os
import re
import json
from typing import Dict, List, Tuple, Optional


# ---------------------------- Utilities & Normalizers ----------------------------

def _dedup_keep_order(items: List[str], limit: Optional[int] = None) -> List[str]:
    """
    Case-insensitive de-duplication while preserving order.
    Trims whitespace, skips non-strings/empties, and optionally enforces a max length.
    """
    seen, out = set(), []
    for x in items:
        if not isinstance(x, str):
            continue
        s = x.strip()
        if not s:
            continue
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
        if limit and len(out) >= limit:
            break
    return out


def _as_list_from_commas(s: Optional[str]) -> List[str]:
    """Split a comma-separated string into a cleaned list."""
    if not isinstance(s, str):
        return []
    return [t.strip() for t in s.split(",") if t.strip()]


def _as_list_from_lines(s: Optional[str]) -> List[str]:
    """Split a newline-separated string into a cleaned list (for responsibilities)."""
    if not isinstance(s, str):
        return []
    return [t.strip() for t in s.splitlines() if t.strip()]


# --- NEW: resilient splitters used to sanitize *model outputs* that might be strings ---

_BULLET_PATTERN = r"[,\n;•·\-\u2022]+"  # commas/newlines/semicolons/common bullet chars

def _split_csvish(s: str) -> List[str]:
    """
    Split on commas/newlines/bullets for 'must'/'nice'.
    Handles cases where the model returns a single string instead of a list.
    """
    parts = re.split(_BULLET_PATTERN, s)
    return [p.strip(" •\t\r-") for p in parts if p and p.strip(" •\t\r-")]

def _split_lines(s: str) -> List[str]:
    """
    Split on newlines/semicolons/bullets for 'responsibilities' style text.
    """
    parts = re.split(r"[\n;•·\-\u2022]+", s)
    return [p.strip(" •\t\r-") for p in parts if p and p.strip(" •\t\r-")]

def _coerce_list(val, *, mode: str) -> List[str]:
    """
    Ensure we always produce List[str] from possibly messy model output.
    mode='csv' for must/nice; mode='lines' for responsibilities.
    """
    if isinstance(val, list):
        return [str(x).strip() for x in val if isinstance(x, (str, int, float)) and str(x).strip()]
    if isinstance(val, (str, int, float)):
        s = str(val).strip()
        if not s:
            return []
        return _split_csvish(s) if mode == "csv" else _split_lines(s)
    return []


# -------------------------------- Mission Composer --------------------------------

def _compose_mission_local(title: str, seniority: str, function: Optional[str] = None) -> str:
    """
    Lightweight local mission composer used when:
      - No API key, or
      - API returns invalid JSON / missing mission.
    """
    t = (title or "role").strip()
    s = (seniority or "").strip()
    f = (function or "").strip()
    opener = f"As our {s + ' ' if s else ''}{t}"
    if f:
        opener += f" on the {f} team"
    body = (
        ", you will prototype, test, and iterate quickly to deliver user-facing impact. "
        "Over the next 6–12 months, success looks like shipping features end-to-end, "
        "documenting learnings, and collaborating closely with peers to raise quality and velocity."
    )
    return opener + body


# --------------------------------- Heuristic Fallback ---------------------------------

def _fallback(
    title: str,
    seniority: str,
    function: Optional[str] = None,
    drafts: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """
    Heuristic fallback. If drafts are provided, prefer them (clean/dedup),
    otherwise synthesize generic-but-useful content.

    Returns dict with keys: must (List[str]), nice (List[str]),
    responsibilities (List[str]), mission (str).
    """
    drafts = drafts or {}
    mission_d = drafts.get("mission")
    must_d = drafts.get("must")               # list OR comma string
    nice_d = drafts.get("nice")               # list OR comma string
    resp_d = drafts.get("responsibilities")   # list OR newline string

    # Prefer user drafts if present
    def _std_list(x, comma=False):
        if isinstance(x, list):
            return [str(v).strip() for v in x if str(v).strip()]
        if isinstance(x, str):
            return _as_list_from_commas(x) if comma else _as_list_from_lines(x)
        return []

    must_list = _std_list(must_d, comma=True)
    nice_list = _std_list(nice_d, comma=True)
    resp_list = _std_list(resp_d, comma=False)

    title_lower = (title or "").lower()
    senior = (seniority or "").lower() in {"senior", "staff", "principal", "lead"}

    # Only backfill missing parts
    if not must_list:
        must_list = [
            "Programming proficiency" if ("engineer" in title_lower or "developer" in title_lower) else f"{title} fundamentals",
            "System design basics" if senior else "Code quality and testing",
            "Version control (Git)" if ("engineer" in title_lower or "developer" in title_lower) else "Collaboration",
            "Debugging and troubleshooting" if ("engineer" in title_lower or "developer" in title_lower) else "Clear communication",
        ]
    if not nice_list:
        nice_list = ["Performance tuning", "Security awareness", "Documentation habits"]
    if senior:
        must_list = must_list + ["Mentoring", "Ownership", "Stakeholder communication"]
        nice_list = nice_list + ["Architecture reviews", "Tech strategy input"]

    if not resp_list:
        resp_list = [
            "Collaborate cross-functionally to deliver product increments",
            "Write, test, and review high-quality work",
            "Participate in planning, estimation, and retrospectives",
            "Own features from design to production",
        ]
        if senior:
            resp_list += [
                "Lead design discussions and propose architecture improvements",
                "Mentor teammates and raise the bar",
                "Drive reliability, performance, and security best practices",
            ]

    mission = (mission_d or "").strip() or _compose_mission_local(title, seniority, function)

    return {
        "must": _dedup_keep_order(must_list, 10),
        "nice": _dedup_keep_order(nice_list, 10),
        "responsibilities": _dedup_keep_order(resp_list, 12),
        "mission": mission.strip(),
    }


# --------------------------------- OpenAI Integration ---------------------------------

def _openai_payload(
    title: str,
    seniority: str,
    function: Optional[str] = None,
    drafts: Optional[Dict[str, object]] = None,
) -> Tuple[Dict[str, object], Dict]:
    """
    Calls OpenAI to POLISH user drafts or GENERATE fresh content:
      - 'must' (6–10)
      - 'nice' (4–8)
      - 'responsibilities' (6–10)
      - 'mission' (≤ 2 sentences)

    Returns (skills_dict, meta_dict).
    skills_dict is sanitized so lists are ALWAYS List[str] and mission is ALWAYS str.
    """
    from openai import OpenAI

    client = OpenAI()
    model = os.getenv("SKILL_SUGGESTER_MODEL", "gpt-4o-mini")

    # Prepare drafts with consistent string/list shapes for the prompt
    drafts = drafts or {}
    d_mission = (drafts.get("mission") or "").strip()
    d_must = drafts.get("must")
    d_nice = drafts.get("nice")
    d_resp = drafts.get("responsibilities")

    # Convert to unified text for the prompt
    d_must_txt = ", ".join(d_must) if isinstance(d_must, list) else (d_must or "")
    d_nice_txt = ", ".join(d_nice) if isinstance(d_nice, list) else (d_nice or "")
    d_resp_txt = "\n".join(d_resp) if isinstance(d_resp, list) else (d_resp or "")

    system = (
        "You are an expert technical recruiter and hiring manager. "
        "You will either POLISH user-provided drafts or GENERATE fresh content when drafts are empty. "
        "Return strict JSON with four fields: 'must', 'nice', 'responsibilities', 'mission'.\n"
        "Rules:\n"
        "• Keep bullets concise (≤ 7–10 words), actionable, and deduplicated.\n"
        "• If drafts are provided, preserve intent but tighten, de-jargon, fix overlaps.\n"
        "• Align the mission to the role's purpose and next 6–12 months outcomes (≤ 2 sentences).\n"
        "• No preamble or commentary; return JSON only."
    )

    user_lines = [
        f"Title: {title}",
        f"Seniority: {seniority}",
        f"Function: {function or ''}",
        "Drafts (may be empty):",
        f"- mission:\n{d_mission}",
        f"- must (comma-separated):\n{d_must_txt}",
        f"- nice (comma-separated):\n{d_nice_txt}",
        f"- responsibilities (one per line):\n{d_resp_txt}",
        "Return JSON with keys exactly: must, nice, responsibilities, mission.",
    ]
    user = "\n".join(user_lines)

    resp = client.chat.completions.create(
        model=model,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )

    # --- Parse & normalize model output ---
    try:
        data = json.loads(resp.choices[0].message.content)
    except Exception:
        # If model returns invalid JSON, use our fallback with drafts
        return _fallback(title, seniority, function, drafts), {
            "used": False,
            "model": model,
            "error": "Invalid JSON from model",
            "prompt_tokens": getattr(getattr(resp, "usage", None), "prompt_tokens", None),
            "completion_tokens": getattr(getattr(resp, "usage", None), "completion_tokens", None),
            "total_tokens": getattr(getattr(resp, "usage", None), "total_tokens", None),
        }

    # Normalize whatever the model returned into clean lists/strings
    must = _coerce_list(data.get("must"), mode="csv")
    nice = _coerce_list(data.get("nice"), mode="csv")
    resp_list = _coerce_list(data.get("responsibilities"), mode="lines")

    mission = data.get("mission")
    if not isinstance(mission, str) or not mission.strip():
        mission = _compose_mission_local(title, seniority, function)

    skills = {
        "must": _dedup_keep_order(must, 10),
        "nice": _dedup_keep_order(nice, 10),
        "responsibilities": _dedup_keep_order(resp_list, 12),
        "mission": mission.strip(),
    }

    usage = getattr(resp, "usage", None)
    meta = {
        "used": True,
        "model": model,
        "error": None,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    return skills, meta


# --------------------------------- Public API ---------------------------------

def suggest_skills(
    title: str,
    seniority: str,
    function: Optional[str] = None,
    drafts: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """
    Convenience wrapper that returns only the skills dict.
    Uses OpenAI if an API key is present; otherwise falls back heuristically.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback(title, seniority, function, drafts)
    try:
        skills, _ = _openai_payload(title, seniority, function, drafts)
        return skills
    except Exception:
        return _fallback(title, seniority, function, drafts)


def suggest_skills_with_meta(
    title: str,
    seniority: str,
    function: Optional[str] = None,
    drafts: Optional[Dict[str, object]] = None,
) -> Tuple[Dict[str, object], Dict]:
    """
    Returns (skills, meta) where:
      skills = {
        "must": List[str],
        "nice": List[str],
        "responsibilities": List[str],
        "mission": str,
      }
      meta   = {"used": bool, "model": str|None, "error": str|None, ...}

    drafts = {
      "mission": str | None,
      "must": List[str] | comma-string | None,
      "nice": List[str] | comma-string | None,
      "responsibilities": List[str] | newline-string | None
    }
    """
    def _meta(used=False, model=None, error=None):
        return {"used": used, "model": model, "error": error}

    if not os.getenv("OPENAI_API_KEY"):
        return _fallback(title, seniority, function, drafts), _meta(used=False, model=None)

    try:
        skills, meta = _openai_payload(title, seniority, function, drafts)
        return skills, meta
    except Exception as e:
        # Fall back but still return meta with the error
        return _fallback(title, seniority, function, drafts), _meta(used=False, error=str(e))
