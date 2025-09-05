# app/tools/skill_suggester.py
import os
from typing import Dict, List, Tuple


def _dedup_keep_order(items: List[str], limit: int | None = None) -> List[str]:
    """Case-insensitive de-duplication while preserving order."""
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


def _fallback(title: str, seniority: str) -> Dict[str, List[str]]:
    """
    Very light heuristic for skills + responsibilities when no API key or API error.
    Tries to be role-agnostic but still a bit useful.
    """
    title_lower = (title or "").lower()
    senior = seniority.lower() in {"senior", "staff", "principal", "lead"}

    base_must = [
        f"{title} fundamentals",
        "Collaboration",
        "Clear communication",
    ]
    if "engineer" in title_lower or "developer" in title_lower:
        base_must = [
            "Programming proficiency",
            "System design basics" if senior else "Code quality and testing",
            "Version control (Git)",
            "Debugging and troubleshooting",
            "CI/CD basics",
        ]

    base_nice = [
        "Performance tuning",
        "Security awareness",
        "Documentation habits",
    ]

    if senior:
        base_must += ["Mentoring", "Ownership", "Stakeholder communication"]
        base_nice += ["Architecture reviews", "Tech strategy input"]

    # Responsibilities are general but helpful for structure
    base_resp = [
        "Collaborate cross-functionally to deliver product increments",
        "Write, test, and review high-quality code",
        "Participate in planning, estimation, and retrospectives",
        "Own features from design to production",
    ]
    if senior:
        base_resp += [
            "Lead design discussions and propose architecture improvements",
            "Mentor teammates and raise the engineering bar",
            "Drive reliability, performance, and security best practices",
        ]

    return {
        "must": _dedup_keep_order(base_must, 10),
        "nice": _dedup_keep_order(base_nice, 10),
        "responsibilities": _dedup_keep_order(base_resp, 12),
    }


def _openai_payload(title: str, seniority: str) -> Tuple[Dict[str, List[str]], Dict]:
    """
    Calls OpenAI to get must/nice/responsibilities.
    Returns (skills_dict, meta_dict).
    """
    from openai import OpenAI
    import json

    client = OpenAI()

    # Prompt keeps outputs short, concrete, and JSON-only
    system = (
        "You are an expert technical recruiter. "
        "Given a role title and seniority, return JSON with three arrays:\n"
        "  - 'must'  (6–10 concrete, role-specific hard skills)\n"
        "  - 'nice'  (4–8 useful but optional skills)\n"
        "  - 'responsibilities' (6–10 short, action-oriented bullets)\n"
        "Rules:\n"
        "• Keep each item concise (≤ 7–10 words).\n"
        "• Avoid duplicates and vague soft skills unless critical to the role.\n"
        "• No preamble or commentary; return JSON only."
    )
    user = f"Title: {title}\nSeniority: {seniority}\nReturn JSON with keys: must, nice, responsibilities."

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    data = json.loads(resp.choices[0].message.content)

    must = _dedup_keep_order([s for s in data.get("must", []) if isinstance(s, str)], 10)
    nice = _dedup_keep_order([s for s in data.get("nice", []) if isinstance(s, str)], 10)
    responsibilities = _dedup_keep_order(
        [s for s in data.get("responsibilities", []) if isinstance(s, str)], 12
    )

    skills = {"must": must, "nice": nice, "responsibilities": responsibilities}

    usage = getattr(resp, "usage", None)
    meta = {
        "used": True,
        "model": "gpt-4o-mini",
        "error": None,
        # token fields may be None depending on SDK/version
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    return skills, meta


def suggest_skills(title: str, seniority: str) -> Dict[str, List[str]]:
    """
    Returns {"must": [...], "nice": [...], "responsibilities": [...]} using OpenAI if key is present,
    otherwise a tiny heuristic fallback.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return _fallback(title, seniority)

    try:
        skills, _ = _openai_payload(title, seniority)
        return skills
    except Exception:
        return _fallback(title, seniority)


def suggest_skills_with_meta(title: str, seniority: str) -> Tuple[Dict[str, List[str]], Dict]:
    """
    Returns (skills, meta) where:
      skills = {"must": [...], "nice": [...], "responsibilities": [...]}
      meta   = {"used": bool, "model": str|None, "error": str|None, ...}
    """
    def _meta(used=False, model=None, error=None):
        return {"used": used, "model": model, "error": error}

    if not os.getenv("OPENAI_API_KEY"):
        return _fallback(title, seniority), _meta(used=False, model=None)

    try:
        skills, meta = _openai_payload(title, seniority)
        return skills, meta
    except Exception as e:
        # Fall back but still return meta with the error
        return _fallback(title, seniority), _meta(used=False, error=str(e))
