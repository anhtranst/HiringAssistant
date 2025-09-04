from typing import Tuple, Dict, Any, List
from graph.state import RoleSpec, JD

def build_checklist(roles: List[RoleSpec], jds: dict, constraints: dict) -> Tuple[str, Dict[str, Any]]:
    weeks = constraints.get("timeline_weeks", 6)

    tasks = [
        {"name": "Finalize JD(s)", "owner": "HR", "due": "Day 1"},
        {"name": "Post roles", "owner": "HR", "due": "Day 2"},
        {"name": "Resume screen cadence", "owner": "HR", "due": "Daily"},
        {"name": "Set interview loop & rubrics", "owner": "Hiring Manager", "due": "Day 3"},
        {"name": "Start interviews", "owner": "Panel", "due": "Week 1"},
        {"name": "Weekly review funnel", "owner": "HR + HM", "due": "Weekly"},
        {"name": "Offer & close", "owner": "HM", "due": f"By Week {weeks}"},
    ]

    loop = [
        {"stage": "Recruiter Screen", "duration_min": 30, "signals": ["motivation","communication"]},
        {"stage": "Hiring Manager", "duration_min": 45, "signals": ["ownership","role fit"]},
        {"stage": "Technical Exercise", "duration_min": 60, "signals": ["coding/problem-solving"]},
        {"stage": "Final Panel", "duration_min": 180, "signals": ["design","collaboration","values"]},
    ]

    md_lines = ["# Hiring Checklist\n"]
    for t in tasks:
        md_lines.append(f"- [ ] **{t['name']}** — _owner: {t['owner']}, due: {t['due']}_")
    md_lines.append("\n## Interview Loop")
    for s in loop:
        md_lines.append(f"- **{s['stage']}** ({s['duration_min']} min): {', '.join(s['signals'])}")

    md_lines.append("\n## Roles & JDs")
    for r in roles:
        jd = jds.get(r.title)
        if jd:
            md_lines.append(f"\n### {jd.title}\n- Mission: {jd.mission}")
            md_lines.append(f"- Requirements: {', '.join(jd.requirements)}")
            md_lines.append(f"- Nice-to-haves: {', '.join(jd.nice_to_haves)}")

    js = {
        "timeline_weeks": weeks,
        "tasks": tasks,
        "interview_loop": loop,
        "roles": [r.model_dump() for r in roles],
        "jds": {k: v.model_dump() for k, v in jds.items()}
    }

    return "\n".join(md_lines), js
