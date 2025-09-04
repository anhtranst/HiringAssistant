def quick_success_estimate(plan_json: dict) -> float:
    # trivial placeholder – returns a number based on timeline/tasks count
    weeks = plan_json.get("timeline_weeks", 6)
    tasks = len(plan_json.get("tasks", [])) or 1
    score = max(0.2, min(0.9, (8.0 / weeks) * (tasks / 7.0)))
    return round(score, 2)
