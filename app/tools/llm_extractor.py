# app/tools/llm_extractor.py
import os, json
from typing import List, Dict, Any, Tuple

def extract_roles_with_llm(text: str, model: str | None = None, timeout: int = 20) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parse an HR prompt and return roles the user wants to hire.
    Returns (roles, meta). meta = {"used": bool, "model": str|None, "error": str|None}
    roles = [{"title": "...", "seniority": "Senior"|None, "function": "Engineering"|None, "count": int}]
    """
    roles: List[Dict[str, Any]] = []
    meta = {"used": False, "model": None, "error": None}

    # Only run if key is present
    if not os.getenv("OPENAI_API_KEY"):
        return roles, meta

    try:
        # Prefer an env override, else a small cheap model
        model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        meta["model"] = model

        try:
            # OpenAI Python SDK >= 1.0
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content":
                        "You are a recruiting intake parser. "
                        "Extract the distinct roles a hiring manager wants to hire. "
                        "Return strict JSON with no commentary."
                    },
                    {"role": "user", "content": (
                        "Text:\n"
                        f"{text}\n\n"
                        "Return JSON with this shape:\n"
                        "{ \"roles\": ["
                        "{ \"title\": \"<role title>\", "
                        "\"seniority\": \"Intern|Junior|Mid|Senior|Staff|Principal|Lead\" | null, "
                        "\"function\": \"Engineering|Data|Design|GTM|Operations\" | null, "
                        "\"count\": <integer number of openings> ] }.\n"
                        "Rules:\n"
                        "- Always include at least 'title'.\n"
                        "- If count is not stated, use 1.\n"
                        "- Titles should be short noun phrases (e.g., 'Full Stack Engineer')."
                    )}
                ],
                timeout=timeout,
            )
            content = resp.choices[0].message.content or "{}"
        except Exception:
            # Legacy SDK fallback (openai<1.0). If you don't need this, you can remove it.
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY")
            resp = openai.ChatCompletion.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content":
                        "You are a recruiting intake parser. "
                        "Extract the distinct roles a hiring manager wants to hire. "
                        "Return strict JSON with no commentary."
                    },
                    {"role": "user", "content": (
                        "Text:\n"
                        f"{text}\n\n"
                        "Return JSON with this shape:\n"
                        "{ \"roles\": ["
                        "{ \"title\": \"<role title>\", "
                        "\"seniority\": \"Intern|Junior|Mid|Senior|Staff|Principal|Lead\" | null, "
                        "\"function\": \"Engineering|Data|Design|GTM|Operations\" | null, "
                        "\"count\": <integer number of openings> ] }.\n"
                        "Rules:\n"
                        "- Always include at least 'title'.\n"
                        "- If count is not stated, use 1.\n"
                        "- Titles should be short noun phrases (e.g., 'Full Stack Engineer')."
                    )}
                ],
                request_timeout=timeout,
            )
            content = resp["choices"][0]["message"]["content"] or "{}"

        data = json.loads(content)
        for r in data.get("roles", []):
            title = (r.get("title") or "").strip()
            if not title:
                continue
            roles.append({
                "title": title,
                "seniority": (r.get("seniority") or None),
                "function": (r.get("function") or None),
                "count": int(r.get("count") or 1),
            })
        meta["used"] = True
        return roles, meta
    except Exception as e:
        meta["error"] = str(e)
        return [], meta
