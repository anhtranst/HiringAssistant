# app/tools/checklist.py
from typing import Tuple, Dict, Any, List, Optional
from graph.state import RoleSpec, JD
import os
import json
import re


# =========================
# Helpers: normalization
# =========================

def _as_list(val) -> List[str]:
    """Coerce strings/lists into a clean List[str]."""
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, (str, int, float)):
        s = str(val).strip()
        if not s:
            return []
        # Split on newlines/semicolons/commas/bullets
        parts = re.split(r"[\n,;•·\-\u2022]+", s)
        return [p.strip(" •\t\r-") for p in parts if p and p.strip(" •\t\r-")]
    return []


def _as_int(val, default: int) -> int:
    """Coerce to int safely."""
    try:
        return int(float(val))
    except Exception:
        return default


def _dedup_keep_order(items: List[str], limit: Optional[int] = None) -> List[str]:
    """Case-insensitive dedup while preserving order."""
    seen, out = set(), []
    for x in items:
        s = str(x).strip()
        if not s:
            continue
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
        if limit and len(out) >= limit:
            break
    return out


# =========================
# Fallback (non-LLM)
# =========================

def _fallback_tasks(weeks: int) -> List[Dict[str, Any]]:
    return [
        {"name": "Finalize JD(s)", "owner": "HR", "due": "Day 1"},
        {"name": "Post roles", "owner": "HR", "due": "Day 2"},
        {"name": "Resume screen cadence", "owner": "HR", "due": "Daily"},
        {"name": "Set interview loop & rubrics", "owner": "Hiring Manager", "due": "Day 3"},
        {"name": "Start interviews", "owner": "Panel", "due": "Week 1"},
        {"name": "Weekly review funnel", "owner": "HR + HM", "due": "Weekly"},
        {"name": "Offer & close", "owner": "HM", "due": f"By Week {weeks}"},
    ]


def _fallback_loop() -> List[Dict[str, Any]]:
    return [
        {"stage": "Recruiter Screen", "duration_min": 30, "signals": ["motivation","communication"]},
        {"stage": "Hiring Manager", "duration_min": 45, "signals": ["ownership","role fit"]},
        {"stage": "Technical Exercise", "duration_min": 60, "signals": ["coding","problem-solving"]},
        {"stage": "Final Panel", "duration_min": 180, "signals": ["design","collaboration","values"]},
    ]


# =========================
# LLM call (optional)
# =========================

def _llm_generate_checklist(
    roles: List[RoleSpec],
    jds: Dict[str, JD],
    constraints: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Ask the model for:
      {
        "tasks": [{"name": str, "owner": str, "due": str}, ...],
        "interview_loop": [{"stage": str, "duration_min": int, "signals": [str, ...]}, ...]
      }
    Returns None if no key/disabled/error.
    """
    use_llm = bool(constraints.get("use_llm"))
    if not use_llm or not os.getenv("OPENAI_API_KEY"):
        return None

    # Respect a simple per-run cap (same pattern as other nodes)
    cap = int(constraints.get("llm_cap", 0))
    used = int(constraints.get("llm_calls", 0))
    if cap and used >= cap:
        return None

    try:
        from openai import OpenAI
        client = OpenAI()
        model = os.getenv("CHECKLIST_MODEL", "gpt-4o-mini")

        # Build concise role context for the prompt
        role_summaries = []
        for r in roles:
            jd = jds.get(r.title)
            role_summaries.append({
                "title": r.title,
                "function": getattr(r, "function", None),
                "seniority": getattr(r, "seniority", None),
                "mission": (jd.mission if isinstance(jd, JD) else None) if jd else None,
                "requirements": (jd.requirements if isinstance(jd, JD) else None) if jd else None,
                "nice_to_haves": (jd.nice_to_haves if isinstance(jd, JD) else None) if jd else None,
            })

        weeks = int(constraints.get("timeline_weeks", 6))
        budget = int(constraints.get("budget_usd", 0))
        location = constraints.get("location_policy", "unspecified")

        system = (
            "You are an experienced recruiting operations lead. "
            "Given roles, target timeline, budget, and location policy, produce a crisp hiring checklist.\n"
            "Return STRICT JSON with keys:\n"
            "  tasks: array of {name, owner, due}\n"
            "  interview_loop: array of {stage, duration_min, signals}\n"
            "Rules:\n"
            "• tasks should be practical, sequenced, and align to the given timeline.\n"
            "• interview_loop should be reasonable length; durations in minutes; signals as short phrases.\n"
            "• Owners should be concise (e.g., HR, HM, Panel).\n"
            "• No prose, no Markdown, JSON ONLY."
        )

        user = json.dumps({
            "timeline_weeks": weeks,
            "budget_usd": budget,
            "location_policy": location,
            "roles": role_summaries,
        }, ensure_ascii=False)

        resp = client.chat.completions.create(
            model=model,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )

        raw = resp.choices[0].message.content
        data = json.loads(raw)

        # Normalize shapes defensively
        tasks_in = data.get("tasks", [])
        loop_in = data.get("interview_loop", [])

        tasks: List[Dict[str, Any]] = []
        for t in (tasks_in if isinstance(tasks_in, list) else []):
            if not isinstance(t, dict): 
                continue
            name = str(t.get("name", "")).strip()
            owner = str(t.get("owner", "")).strip()
            due = str(t.get("due", "")).strip()
            if not name:
                continue
            tasks.append({
                "name": name,
                "owner": owner or "HR",
                "due": due or "TBD",
            })

        loop: List[Dict[str, Any]] = []
        for s in (loop_in if isinstance(loop_in, list) else []):
            if not isinstance(s, dict):
                continue
            stage = str(s.get("stage", "")).strip()
            if not stage:
                continue
            loop.append({
                "stage": stage,
                "duration_min": _as_int(s.get("duration_min", 45), 45),
                "signals": _dedup_keep_order(_as_list(s.get("signals")), 6) or ["general fit"],
            })

        # Minimal viable result
        if not tasks:
            tasks = _fallback_tasks(weeks)
        if not loop:
            loop = _fallback_loop()

        # Update simple LLM accounting in-place so the UI tab can display it
        usage = getattr(resp, "usage", None)
        meta = {
            "feature": "checklist",
            "used": True,
            "model": model,
            "error": None,
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        constraints["llm_calls"] = used + 1
        constraints.setdefault("llm_log", []).append(meta)

        return {"tasks": tasks, "interview_loop": loop}

    except Exception as e:
        # Record error but proceed with fallback
        constraints.setdefault("llm_log", []).append({
            "feature": "checklist",
            "used": False,
            "model": os.getenv("CHECKLIST_MODEL", "gpt-4o-mini"),
            "error": str(e),
        })
        return None


# =========================
# Public entry point
# =========================

def build_checklist(roles: List[RoleSpec], jds: dict, constraints: dict) -> Tuple[str, Dict[str, Any]]:
    """
    Build the hiring checklist.

    Behavior:
      - If LLM is enabled and available, generate tasks & interview loop using role/JD context,
        timeline_weeks, budget_usd, and location_policy.
      - Otherwise (or on error), use the static fallback.
      - Always render Markdown + JSON for the UI/export tabs.

    Returns: (markdown, json_dict)
    """
    weeks = int(constraints.get("timeline_weeks", 6))
    budget = int(constraints.get("budget_usd", 0))
    location = constraints.get("location_policy", "unspecified")

    # Try LLM path first (respecting cap), else fallback
    llm_data = _llm_generate_checklist(roles, jds, constraints)
    if llm_data:
        tasks = llm_data["tasks"]
        loop = llm_data["interview_loop"]
    else:
        tasks = _fallback_tasks(weeks)
        loop = _fallback_loop()

    # ---------- Markdown rendering ----------
    md_lines = [ "# Hiring Checklist\n" ]
    md_lines.append(f"_Target timeline: **{weeks} weeks** · Budget: **${budget:,}** · Location: **{location}**_")
    md_lines.append("")  # blank line

    for t in tasks:
        md_lines.append(f"- [ ] **{t['name']}** — _owner: {t.get('owner','HR')}, due: {t.get('due','TBD')}_")

    md_lines.append("\n## Interview Loop")
    for s in loop:
        sig = ", ".join(s.get("signals", []) or [])
        md_lines.append(f"- **{s['stage']}** ({_as_int(s.get('duration_min', 45),45)} min): {sig or '—'}")

    md_lines.append("\n## Roles & JDs")
    for r in roles:
        jd: Optional[JD] = jds.get(r.title)
        if isinstance(jd, JD):
            req = ", ".join(jd.requirements) if jd.requirements else "—"
            nice = ", ".join(jd.nice_to_haves) if jd.nice_to_haves else "—"
            md_lines.append(f"\n### {jd.title}\n- Mission: {jd.mission or '—'}")
            md_lines.append(f"- Requirements: {req}")
            md_lines.append(f"- Nice-to-haves: {nice}")

    # ---------- JSON payload ----------
    js = {
        "timeline_weeks": weeks,
        "budget_usd": budget,
        "location_policy": location,
        "tasks": tasks,
        "interview_loop": loop,
        "roles": [r.model_dump() for r in roles],
        "jds": {k: v.model_dump() for k, v in jds.items()},
        # Optional: tiny breadcrumb for the UI to know if LLM was used
        "meta": {
            "llm_used": bool(llm_data),
        },
    }

    return "\n".join(md_lines), js
