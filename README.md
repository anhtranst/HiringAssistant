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
│ ├─ ui.py # Streamlit shell; kicks off role review and renders Tabs (1–4)
│ ├─ init.py
│ ├─ tabs/
│ │ ├─ init.py
│ │ └─ roles_tab.py # Tab 1 orchestration:
│ │ # • Review role suggestions
│ │ # • Add another hiring role (search/select or create custom)
│ │ # • Edit matched roles (inline); remove role from the plan
│ │ # • "Generate plan & JDs" (rebuilds JD + plan only after roles finalized)
│ ├─ components/
│ │ ├─ init.py
│ │ ├─ matched_role_editor.py # Editor for matched roles:
│ │ │ # • Shows “Selected by HR” when manual
│ │ │ # • Context-aware ✨ AI suggest (polish drafts or generate)
│ │ │ # • Save changes (store-only; no rebuild)
│ │ │ # • Save as custom template (store-only)
│ │ │ # • 🗑 Remove this role from the hiring plan
│ │ └─ unresolved_role_panel.py # Suggestions UI (dropdown + live preview):
│ │ # • De-dupes already-chosen templates
│ │ # • Create-new flow (mission + skills/responsibilities with ✨ AI assist)
│ │ # • Marks role as matched (manual) when selected/created
│ ├─ services/
│ │ ├─ init.py
│ │ └─ state_helpers.py # field/set_field/_get helpers + bump_llm_usage; lightweight store-only updates
│ ├─ graph/
│ │ ├─ init.py
│ │ ├─ state.py # AppState, RoleSpec (confidence Optional, confidence_source), JD models
│ │ ├─ nodes.py # Intake (LLM-first + heuristic), top-3 suggests, profile fill-only, JD compose/polish
│ │ └─ graph_builder.py # LangGraph wiring (delays plan/JD generation until explicitly triggered)
│ └─ tools/
│ ├─ init.py
│ ├─ role_matcher.py # Data paths; timestamped custom ids; created_at; improved extractor; top-3 matching
│ ├─ llm_extractor.py # Optional LLM-based role extraction (strict JSON response)
│ ├─ search_stub.py # Robust template loader (curated/custom) for dicts or models; file/role_id/title fallback
│ ├─ skill_suggester.py # Context-aware ✨ AI: mission + must/nice + responsibilities (polish drafts or generate)
│ ├─ checklist.py # Generates hiring plan/checklist & loop (LLM-powered with timeline/budget/location context)
│ ├─ email_writer.py # Outreach email templates
│ ├─ inclusive_check.py # Inclusive language linter
│ ├─ simulator.py # Success estimator
│ ├─ analytics.py # Simple CSV logger (includes click_review_roles, etc.)
│ └─ exporters.py # Exports:
│ # • plan.docx (timeline, checklist, loop, Roles & JDs summary)
│ # • per-role JD .docx and ZIP bundle
├─ data/
│ ├─ roles_kb.json # Curated role index
│ ├─ roles_kb_custom.json # Custom role index (includes created_at)
│ ├─ role_knowledge/ # Curated templates (canonical schema: skills.{must,nice})
│ │ ├─ founding_engineer.json
│ │ └─ genai_intern.json
│ └─ role_knowledge_custom/ # Custom templates (timestamped ids: <slug>__custom__YYYYMMDD_HHMMSS)
├─ exports/ # (ignored) generated files
├─ logs/ # (ignored) usage logs
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

Extract intended roles from the full prompt:
• LLM-first (optional, respects use_llm/llm_cap) → titles
• Heuristic fallback (supports 1..N roles) → titles

For each title, fuzzy-match against roles_kb.json + roles_kb_custom.json

Produce RoleSpec(status="suggest" | "unknown") with top-3 suggestions per role
↓
[UI Resolver — Roles & JDs tab]

Review role suggestions:
• For each suggested role: default-select newest custom template if present
• Exclude templates already chosen in other slots (no duplicate picks)
• Choose from a dropdown (stable indices); preview updates live
• Preview includes: Mission, Function, Seniority, Must/Nice, Responsibilities
• “Use selected suggestion” marks the role as matched:
– Sets confidence=None and confidence_source="manual" (“Selected by HR”)

Create a brand-new custom role (alternative to picking a suggestion):
• Fields: Title, Function, Seniority, Mission, Must/Nice, Responsibilities
• ✨ Suggest with AI (context-aware): polish current drafts or generate from scratch (respects LLM cap)
• Save → persists to data/role_knowledge_custom/<slug>__custom__YYYYMMDD_HHMMSS.json
and indexes in data/roles_kb_custom.json (created_at)

Add another hiring role (global action on this tab):
• Enter a title → see suggestions → pick one OR create a custom role (same flow as above)
• Newly added role appears as “suggest” until confirmed

Edit matched roles inline:
• Update Title/Seniority/Must/Nice/Responsibilities
• ✨ Suggest with AI (context-aware) to refine existing drafts
• Save changes (store-only; no rebuild)
• 🗑 Remove this role from the hiring plan (store-only)

Once all roles are finalized → RoleSpec(status="match") for each

Click Generate plan & JDs:
• Rebuilds Job Descriptions and the Hiring Plan using the current set of matched roles
• Heavy compute happens here (not during every small edit)
↓
[Profile (enrich-only)]

Load curated/custom JSON template for each matched role

FILL ONLY MISSING FIELDS (skills.must, skills.nice, responsibilities, seniority, geo)

Never overwrite fields already edited in UI
↓
[JD]

Build structured Job Descriptions per matched role (includes role-specific Mission)

(Optional) LLM polish (strict JSON in/out; capped by llm_cap)
↓
[Plan]

Generate checklist + interview loop (Markdown + JSON) using timeline_weeks, budget_usd, location_policy,
and role/JD context

Inclusive language scan

Outreach emails (only for finalized roles)
↓
[UI Tabs]

Roles & JDs
• Resolve suggestions, add roles, create custom roles
• Edit matched roles, ✨ context-aware re-suggest, Save (no rebuild), 🗑 Remove role
• Generate plan & JDs to refresh outputs after all roles are ready

Checklist / Plan

Tools (Inclusive warnings / Outreach email examples / LLM usage log)

Export
• Hiring Plan → MD / JSON / DOCX (timeline/budget/location, checklist, loop, role summaries)
• Per-role JDs → one DOCX per role
• All JDs → ZIP
```

Notes:
- Apply changes updates only the current run; Save as custom template persists to disk.
- Custom roles are stored under data/role_knowledge_custom/ and indexed in data/roles_kb_custom.json.
- All AI features respect use_llm/llm_cap and log usage in global_constraints.llm_log.

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