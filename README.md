# Hiring Assistant · Agentic HR Planner

Plan an entire startup hiring process from a single prompt — then refine it with a tight, HR-friendly workflow.

- **Template-first JDs, AI-assisted where it helps**
  - Extracts intended roles (LLM-first optional, robust heuristic fallback)
  - Suggests curated/custom templates; **add new roles** or **remove roles** anytime
  - **Context-aware ✨ AI polish** for Mission, Must/Nice skills, and Responsibilities  
    (uses your drafts if provided; generates from scratch if blank)

- **Finalize first, generate later**
  - Edit matched roles inline without recomputing
  - Heavy work (JDs + plan) runs **only** when you click **Generate plan & JDs**

- **Hiring plan you can execute**
  - Checklist + interview loop built from **timeline**, **budget**, **location policy**, and role context
  - Inclusive language scan and example outreach emails

- **Exports built for HR & ATS**
  - `plan.md`, `plan.json`, and an HR-friendly **`plan.docx`**
  - **Per-role JD .docx** (one file per role) and a **ZIP** with all JDs

- **Controls & guardrails**
  - Optional OpenAI usage with **caps** and run-level usage log
  - Deterministic local fallback when no API key is present
  - Never overwrites fields you edited in the UI (profile step is fill-only)

- **Tech**
  - **LangGraph** orchestration, **Streamlit** UI
  - **Docker** ready, deployable to **AWS Elastic Beanstalk**

> Built for the Squareshift “Agent in Action – GenAI Builder-in-Residence Challenge”.  
> The app is deliberately template-first with optional LLM refinement to keep demos fast, repeatable, and enterprise-safe.


---

## Demo (What it does)

1. **Describe your hiring need**  
   Example: _“I need to hire a founding engineer and a GenAI intern. Can you help?”_

2. **Click “Review role suggestions”**  
   The app extracts intended roles (LLM-first optional; heuristic fallback) and shows top suggestions from curated + custom templates.

3. **Resolve roles in the “Roles & JDs” tab**  
   - Pick a suggested template (live preview: **Mission, Function, Seniority, Must/Nice, Responsibilities**)  
   - **Add another hiring role** (enter a title → see suggestions → pick or **create a custom role**)  
   - **Edit matched roles** inline (Title/Seniority/Must/Nice/Responsibilities)  
   - **✨ Suggest with AI** to polish your drafts or generate from scratch (respects LLM cap)  
   - **Remove a role** if you change your mind  
   - Changes are stored without recomputing; finalize all roles first.

4. **Click “Generate plan & JDs”**  
   Heavy compute runs once:  
   - Builds structured **Job Descriptions** per role (optionally polished via OpenAI)  
   - Generates a **Hiring Plan** (Checklist + Interview Loop) using your **timeline**, **budget**, and **location policy**

5. **Review tools**  
   - **Inclusive language** warnings  
   - Example **outreach emails**  
   - **LLM usage** summary (toggle, cap, calls, log)

6. **Export**  
   - **Hiring Plan:** `plan.md`, `plan.json`, and **`plan.docx`**  
   - **Per-role JDs:** one **.docx** per role  
   - **All JDs:** single **.zip** bundle

---

## Stack

- **UI:** Streamlit (`session_state` for store-only edits; controlled actions for rebuilds)
- **Agent Orchestration:** LangGraph (intake → profile(fill-only) → JD compose/polish → plan)
- **Models/Schemas:** Pydantic (AppState, RoleSpec with optional `confidence`, JD)
- **LLM (optional):** OpenAI Chat Completions (`gpt-4o-mini` by default; env-configurable), deterministic fallbacks when no key
- **Data/Templates:** Curated JSON under `data/role_knowledge/`; custom templates persisted to `data/role_knowledge_custom/` and indexed in `roles_kb_custom.json`
- **Exports:** `python-docx` for `plan.docx` and per-role JD `.docx`; `zipfile` for JD bundles; Markdown + JSON
- **Inclusive Checks & Emails:** Lightweight rule-based linter; templated outreach emails
- **Packaging/Deploy:** Docker; AWS Elastic Beanstalk (ALB + ACM), Route 53

---

## Project Structure


```
HiringAssistant/
├─ app/
│ ├─ ui.py # Streamlit app shell + tabs
│ ├─ init.py
│ ├─ tabs/
│ │ └─ roles_tab.py # Tab 1: review/add/edit/remove roles; generate plan/JDs
│ ├─ components/
│ │ ├─ matched_role_editor.py # Edit matched roles; AI suggest; remove role
│ │ └─ unresolved_role_panel.py # Pick suggestions; preview; create custom role
│ ├─ services/
│ │ └─ state_helpers.py # field/set_field/_get; LLM usage bump
│ ├─ graph/
│ │ ├─ state.py # Pydantic models (AppState, RoleSpec, JD)
│ │ ├─ nodes.py # Intake → profile(fill-only) → JD → plan
│ │ └─ graph_builder.py # LangGraph wiring (build on explicit action)
│ └─ tools/
│ ├─ role_matcher.py # KB matching; persist custom templates
│ ├─ llm_extractor.py # Optional role extraction via LLM
│ ├─ search_stub.py # Load curated/custom templates
│ ├─ skill_suggester.py # AI mission/skills/responsibilities (polish/gen)
│ ├─ checklist.py # Hiring plan + interview loop
│ ├─ email_writer.py # Outreach email examples
│ ├─ inclusive_check.py # Inclusive language linter
│ ├─ simulator.py # Success estimator stub
│ └─ exporters.py # plan.docx; per-role JD .docx; ZIP bundle
├─ data/
│ ├─ roles_kb.json # Curated role index
│ ├─ roles_kb_custom.json # Custom role index
│ ├─ role_knowledge/ # Curated templates
│ │ ├─ founding_engineer.json
│ │ └─ genai_intern.json
│ └─ role_knowledge_custom/ # Saved custom templates (timestamped)
├─ exports/ # Generated files (ignored)
├─ logs/ # Usage logs (ignored)
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

- **Hiring Plan**
  - `plan.md` (Markdown)
  - `plan.json` (structured JSON)
  - `plan.docx` (HR-friendly DOCX with timeline, checklist, loop, role summaries)
- **Per-role JDs**
  - One DOCX per role (e.g., `JD_Founding-Engineer.docx`)
- **Bundle**
  - `JDs.zip` (all JD DOCXs)

Download everything from the **Export** tab.  
For convenience, `plan.md` and `plan.json` are also written to `exports/` locally (ignored by Git).


---

## Security & Data

- Secrets are **not** committed. `.env` and `key.env` are ignored by `.gitignore`.
- Role data uses synthetic templates under `data/role_knowledge/` (curated).
- **Custom roles** you create in the UI are saved locally under `data/role_knowledge_custom/`
  and indexed in `data/roles_kb_custom.json` (timestamped IDs). They are not uploaded anywhere.
  - If your custom templates may contain proprietary info, consider adding
    `data/role_knowledge_custom/` to `.gitignore` (org policy dependent).
  - Avoid placing PII or sensitive data in templates. To purge, delete the files in
    `data/role_knowledge_custom/` and remove their entries from `data/roles_kb_custom.json`.
- No real candidate PII is processed; all outputs are demo-safe by default.

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

- **Email Composer/Polisher**
  - Write full outreach emails from role context, or polish HR-provided notes into a finished message.
  - Support multiple tones (warm, concise, enterprise) and variants (first touch, follow-up, referral).

- **AI Cost Analytics**
  - Dashboard showing token/cost breakdown per step (role skills, JD polish, plan generation, emails).
  - Per-role and per-run summaries; caps and alerts.

- **Task-Specific AI Agents**
  - Split generation into specialized assistants (skills, hiring plan, interview loop, email).
  - Option to fine-tune per task or plug in organization-preferred models.

- **Session Persistence**
  - Store working data in session storage so refreshes don’t lose progress (expire on inactivity).
  - Optional autosave/export of session snapshots.

- **Admin: Template Governance**
  - Promote user **custom roles** to **CORE** templates.
  - Edit/retire CORE roles; audit history and versioning.


---

## Known Limitations

- **Role extraction is basic.** Heuristic parsing may miss roles or produce loose matches; manual confirmation is expected.
- **LLM outputs vary.** With OpenAI enabled, content can be non-deterministic; without a key, fallbacks are intentionally generic.
- **Session is volatile.** Refreshing the page clears in-memory progress (no autosave/persistence yet).
- **Inclusive checks are lightweight.** Rule-based linter may miss nuanced or context-specific language issues.
- **No ATS/inbox/calendar integrations.** Outputs are file-based; sharing/scheduling requires manual steps.
- **No auth/RBAC.** Single-user demo experience; admin/governance flows are not enforced.
- **Cost visibility is limited.** We cap calls, but there’s no per-step token/cost dashboard yet.
- **Ephemeral local files on EB.** Exports/logs don’t persist across deployments/restarts; use S3/DB in production.

---

## Credits

Built by Anh with guidance from a ChatGPT coding assistant. Uses Streamlit, LangGraph, OpenAI, Pydantic, and Python-docx