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
│  ├─ ui.py                       # Streamlit UI (entry point)
│  ├─ __init__.py
│  ├─ graph/
│  │  ├─ __init__.py
│  │  ├─ state.py                 # Pydantic models (AppState, RoleSpec, JD)
│  │  ├─ nodes.py                 # Graph steps: intake → profile → jd → plan
│  │  └─ graph_builder.py         # LangGraph wiring
│  └─ tools/
│     ├─ __init__.py
│     ├─ search_stub.py           # Loads role facts from /data/role_knowledge
│     ├─ checklist.py             # Builds checklist + interview loop
│     ├─ email_writer.py          # Outreach email templates
│     ├─ inclusive_check.py       # Regex-based inclusive language linter
│     ├─ simulator.py             # Placeholder success estimator
│     ├─ analytics.py             # Tiny CSV logger (local)
│     └─ exporters.py             # JSON → DOCX
├─ data/
│  └─ role_knowledge/
│     ├─ founding_engineer.json
│     └─ genai_intern.json
├─ exports/                       # (ignored) generated files
├─ logs/                          # (ignored) usage logs
├─ Dockerfile
├─ .dockerignore
├─ requirements.txt
└─ .gitignore
```


---

## How it flows (LangGraph)

```
user prompt
   ↓
[Intake]  → parse roles (simple keyword parser)
   ↓
[Profile] → enrich with must-haves / nice-to-haves from /data templates
   ↓
[JD]      → build structured JDs; optionally LLM polish (same JSON shape)
   ↓
[Plan]    → checklist + interview loop (MD/JSON) + inclusivity + emails
   ↓
UI tabs   → view/export MD/JSON/DOCX + LLM usage log
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