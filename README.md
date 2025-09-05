# Hiring Assistant · Agentic HR Planner

Plan a startup hiring process from a single prompt.

- **Clarifies the ask** (basic parsing of multiple roles)
- **Drafts Job Descriptions (JDs)** from templates with **optional LLM polish**
- **Creates a hiring checklist & interview loop** (Markdown + JSON)
- **Flags non-inclusive language** and provides **outreach email templates**
- **Exports**: `plan.md`, `plan.json`, and **HR-friendly `plan.docx`**
- **LangGraph** orchestrated, **Streamlit** UI, **Docker** ready, **AWS EB** deployable

> This project is for the Squareshift “Agent in Action – GenAI Builder-in-Residence Challenge”.  
> It intentionally uses deterministic stubs + optional LLM refinement to keep demos fast and repeatable.

---

## Demo (What it does)

1. Enter a prompt like:  
   _“I need to hire a founding engineer and a GenAI intern. Can you help?”_
2. Click **Plan Hiring**.
3. The app:
   - Parses roles
   - Loads role facts from `/data/role_knowledge`
   - Builds structured **JDs** (and optionally polishes wording via OpenAI)
   - Emits a **Checklist + Interview Loop** (Markdown + JSON)
   - Flags **inclusive-language issues** and drafts **outreach emails**
4. Export everything as **MD/JSON/DOCX**.

---

## Stack

- **UI**: Streamlit
- **Agent Orchestration**: LangGraph
- **Models**: Pydantic (state + schemas)
- **LLM (optional)**: OpenAI (Chat Completions)
- **Exports**: `python-docx` for `.docx`
- **Packaging/Deploy**: Docker; AWS Elastic Beanstalk (ALB + ACM), Route 53

---

## Project Structure


```
HiringAssistant/
├─ app/
│  ├─ ui.py                              # Streamlit UI (resolve roles, show results)
│  ├─ __init__.py
│  ├─ graph/
│  │  ├─ __init__.py
│  │  ├─ state.py                        # AppState, RoleSpec, JD models
│  │  ├─ nodes.py                        # intake → profile → jd → plan
│  │  └─ graph_builder.py                # LangGraph wiring
│  └─ tools/
│     ├─ __init__.py
│     ├─ role_matcher.py                 # Extract phrases, match KB, save/load roles
│     ├─ search_stub.py                  # load_role_template, load_template_for_role
│     ├─ skill_suggester.py              # AI suggestions for must/nice skills & responsibilities
│     ├─ checklist.py                    # Build checklist + interview loop
│     ├─ email_writer.py                 # Outreach email templates
│     ├─ inclusive_check.py              # Inclusive language linter
│     ├─ simulator.py                    # Success estimator
│     ├─ analytics.py                    # Simple CSV logger
│     └─ exporters.py                    # Export JSON → DOCX
├─ data/
│  ├─ roles_kb.json                      # Curated role index
│  ├─ roles_kb_custom.json               # Custom role index (user-created)
│  ├─ role_knowledge/                    # Curated templates
│  │  ├─ founding_engineer.json
│  │  └─ genai_intern.json
│  └─ role_knowledge_custom/             # Custom templates (generated at runtime)
├─ exports/                              # (ignored) generated files
├─ logs/                                 # (ignored) usage logs
├─ Dockerfile
├─ .dockerignore
├─ requirements.txt
└─ .gitignore

```

---

## How it flows (LangGraph)

```
User prompt
   ↓
[Intake v2]
   - Extract candidate phrases
   - Match against roles_kb.json (+ roles_kb_custom.json)
   - Produce RoleSpec(status="match" | "suggest" | "unknown")
   ↓
[UI Resolver]
   - For suggest/unknown: pick a suggested template OR create a new role
   - (Optional) ✨ AI suggest must-have / nice-to-have skills + responsibilities
   - Save custom role → role_knowledge_custom/ + roles_kb_custom.json (when chosen)
   - Once finalized → RoleSpec(status="match")
   ↓
[Profile (enrich-only)]
   - Load curated/custom JSON template for each matched role
   - FILL ONLY MISSING FIELDS (must_haves, nice_to_haves, responsibilities, seniority, geo)
   - Never overwrite fields already edited in UI
   ↓
[JD]
   - Build structured Job Descriptions from RoleSpec
   - (Optional) LLM polish (strict JSON in/out; capped by llm_cap)
   ↓
[Plan]
   - Generate checklist + interview loop (Markdown + JSON)
   - Inclusive language scan
   - Outreach emails (only for finalized roles)
   ↓
[UI Tabs]
   - Roles & JDs (edit matched roles; ✨ AI re-suggest; Apply changes re-runs graph)
   - Checklist / Plan
   - Tools (Email / Inclusive warnings / LLM usage log)
   - Export (MD / JSON / DOCX)

Notes:
- **Apply changes** updates only the current run (session) and re-runs the graph; use “Save as custom template” to persist to disk.
- Custom roles are stored under `data/role_knowledge_custom/` and indexed in `data/roles_kb_custom.json`.

```


---

## Local Setup

**Requirements:** Python 3.10+ (3.11 recommended)

```bash
# clone + enter
pip install -r requirements.txt
```

Optional: create .env in the project root to enable LLM polish:
OPENAI_API_KEY=sk-...

Run:
streamlit run app/ui.py

Open the local URL Streamlit prints (default http://localhost:8501).

---

## LLM Toggle & Cost Guard

- Toggle **Use LLM to polish JD text** in the UI.
- The JD step will call OpenAI **only if**:
  - The toggle is **ON**, and
  - `OPENAI_API_KEY` is available, and
  - The per-run **call cap** has **not** been exceeded (configurable in the UI).
- The **Tools** tab shows an **LLM usage log** (model + token counts when provided).

> Without a key or with the toggle OFF, the app is fully deterministic.

---

## Exports

- **Markdown:** `plan.md`
- **JSON:** `plan.json`
- **DOCX:** `plan.docx` (HR-friendly, ready to share or print as PDF)

Download these in the **Export** tab.  
`plan.md` / `plan.json` are also written to `exports/` (local, ignored by Git).

---

## Security & Data

- Secrets are **not** committed. `.env` and `key.env` are ignored by `.gitignore`.
- Role data is synthetic templates under `data/role_knowledge/`.
- No real candidate PII; all outputs are demo-safe.

---

## Deploy to AWS Elastic Beanstalk (Docker)

This repo includes a `Dockerfile` and `.dockerignore`.

### One-time

```bash
pip install awsebcli
aws configure   # set your AWS creds/region
```

Initialize (pick your region)

```bash
# example: us-west-1
eb init -p docker HiringAssistant-EB --region us-west-1
```

Create a load-balanced environment (needed for HTTPS via ALB)
```bash
eb create hiring-assistant-lb --elb-type application
eb setenv PORT=8080 OPENAI_API_KEY=sk-xxxx
eb deploy
eb open
```

The Dockerfile binds Streamlit to 0.0.0.0:8080, which matches EB’s expectations.

---

## Roadmap (Next Up)

- Clarifying Questions node (ask for missing budget/timeline/skills, then continue)

- Rubric Generator node (competency anchors 1–4 + sample questions)

- Simulator tab (sliders for funnel rates → probability & bottleneck)

- Session memory (persist company profile/preferences)

- Analytics dashboard (basic charts for conversions & load)

---

## Known Limitations

- Role parsing is intentionally simple (keyword-based).

- Local exports/logs are ephemeral on EB (container filesystem). Use S3/DB for persistence in production.

---

## Credits

Built by Anh with guidance from a ChatGPT coding assistant. Uses Streamlit, LangGraph, OpenAI, Pydantic, and Python-docx