# app/services/state_helpers.py
def field(obj, name, default=None):
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default

def set_field(obj, name, value):
    if hasattr(obj, name):
        setattr(obj, name, value)
    elif isinstance(obj, dict):
        obj[name] = value

def _get(s, name, default=None):
    if isinstance(s, dict):
        return s.get(name, default)
    return getattr(s, name, default)

def bump_llm_usage(state, meta: dict, feature: str):
    if not meta or not meta.get("used"):
        return state
    gc = _get(state, "global_constraints", {}) or {}
    gc["llm_calls"] = int(gc.get("llm_calls", 0)) + 1
    log = list(gc.get("llm_log", []))
    log.append({"feature": feature, "model": meta.get("model"), "error": meta.get("error")})
    gc["llm_log"] = log
    if isinstance(state, dict):
        state["global_constraints"] = gc
    else:
        state.global_constraints = gc
    return state
