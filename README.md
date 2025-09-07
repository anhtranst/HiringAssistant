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
│  ├─ ui.py                              # Streamlit shell; runs graph once + renders Tabs; Tab 1 delegated
│  ├─ __init__.py
│  ├─ tabs/
│  │  ├─ __init__.py
│  │  └─ roles_tab.py                    # NEW: Tab 1 orchestration (roles & JDs) + callbacks to re-run graph
│  ├─ components/
│  │  ├─ __init__.py
│  │  ├─ matched_role_editor.py          # NEW: editor for matched roles; AI suggest; apply changes; save custom template
│  │  └─ unresolved_role_panel.py        # NEW: top-3 suggestions UI; defaults to newest custom; preview; create-new flow
│  ├─ services/
│  │  ├─ __init__.py
│  │  └─ state_helpers.py                # NEW: field/set_field/_get helpers + bump_llm_usage
│  ├─ graph/
│  │  ├─ __init__.py
│  │  ├─ state.py                        # AppState, RoleSpec, JD models
│  │  ├─ nodes.py                        # UPDATED: LLM-first intake + robust heuristic fallback; top-3 suggests; profile fill-only; JD polish
│  │  └─ graph_builder.py                # LangGraph wiring
│  └─ tools/
│     ├─ __init__.py
│     ├─ role_matcher.py                 # UPDATED: repo-root data paths; timestamped custom ids; created_at; improved extractor; top-3 matching
│     ├─ llm_extractor.py                # NEW: optional LLM-based role extraction (strict JSON response)
│     ├─ search_stub.py                  # UPDATED: repo-root-aware template loader (curated + custom)
│     ├─ skill_suggester.py              # AI suggestions for must/nice skills & responsibilities
│     ├─ checklist.py                    # Build checklist + interview loop
│     ├─ email_writer.py                 # Outreach email templates
│     ├─ inclusive_check.py              # Inclusive language linter
│     ├─ simulator.py                    # Success estimator
│     ├─ analytics.py                    # Simple CSV logger
│     └─ exporters.py                    # Export JSON → DOCX
├─ data/
│  ├─ roles_kb.json                      # Curated role index
│  ├─ roles_kb_custom.json               # Custom role index (now includes created_at)
│  ├─ role_knowledge/                    # Curated templates (canonical schema: skills.{must,nice})
│  │  ├─ founding_engineer.json          # UPDATED to canonical schema
│  │  └─ genai_intern.json               # UPDATED to canonical schema
│  └─ role_knowledge_custom/             # Custom templates (timestamped ids: <slug>__custom__YYYYMMDD_HHMMSS)
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
[Intake]
  - Extract intended roles from the full prompt:
      • LLM-first (optional, respects use_llm/llm_cap) → titles
      • Heuristic fallback (supports 1..N roles) → titles
  - For each title, fuzzy-match against roles_kb.json + roles_kb_custom.json
  - Produce RoleSpec(status="suggest" | "unknown") with top-3 suggestions per role
  ↓
[UI Resolver]
  - For each suggested role: default-select the newest custom template if present
  - Preview selected template (function, skills.must/nice, responsibilities)
  - Choose a suggestion OR create a brand-new custom role
  - (Optional) ✨ AI suggest must-have / nice-to-have skills + responsibilities
  - Save custom role → data/role_knowledge_custom/<slug>__custom__YYYYMMDD_HHMMSS.json
    and index in data/roles_kb_custom.json (includes created_at)
  - Once finalized → RoleSpec(status="match")
  ↓
[Profile (enrich-only)]
  - Load curated/custom JSON template for each matched role
  - FILL ONLY MISSING FIELDS (skills.must, skills.nice, responsibilities, seniority, geo)
  - Never overwrite fields already edited in UI
  ↓
[JD]
  - Build structured Job Descriptions from RoleSpec + template facts
  - (Optional) LLM polish (strict JSON in/out; capped by llm_cap)
  ↓
[Plan]
  - Generate checklist + interview loop (Markdown + JSON)
  - Inclusive language scan
  - Outreach emails (only for finalized roles)
  ↓
[UI Tabs]
  - Roles & JDs (resolve roles, preview templates, edit matched roles; ✨ re-suggest; Apply changes re-runs graph)
  - Checklist / Plan
  - Tools (Email / Inclusive warnings / LLM usage log)
  - Export (MD / JSON / DOCX)

```

Notes:
- **Apply changes** updates only the current run; **Save as custom template** persists to disk.
- Custom roles are stored under `data/role_knowledge_custom/` and indexed in `data/roles_kb_custom.json`.
- Core templates use the canonical schema (`skills.must` / `skills.nice`).

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