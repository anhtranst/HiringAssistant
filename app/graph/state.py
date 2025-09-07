# app/graph/state.py
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal


class RoleSpec(BaseModel):
    """
    Canonical role record that flows through the graph + UI.

    Notes:
    - `confidence` is Optional[float] so we can explicitly set it to None
      for roles selected manually by HR (confidence_source="manual").
    - `status` uses a Literal union for clarity and validation.
    - We keep a few optional metadata fields (`function`, `seniority`, `geo`)
      that templates or UI may enrich.
    """
    # KB linkage / provenance
    role_id: Optional[str] = None          # id in roles KB (curated or custom)
    file: Optional[str] = None             # path to template json (curated or custom)

    # Identity + state
    title: str
    status: Literal["match", "suggest", "unknown"] = "match"

    # Matching signal (may be None when HR selects manually)
    confidence: Optional[float] = Field(default=None)
    confidence_source: Optional[str] = None  # e.g., "auto" | "manual"

    # Suggestions shown during resolution (top-3, etc.)
    suggestions: List[Dict] = Field(default_factory=list)

    # EDITABLE / ENRICHABLE FIELDS (UI can override; profile node may fill gaps)
    must_haves: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    function: Optional[str] = None
    geo: Optional[str] = None


class JD(BaseModel):
    """
    Structured Job Description used for rendering and exports.
    """
    title: str
    mission: str
    responsibilities: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)
    benefits: List[str] = Field(default_factory=list)


class AppState(BaseModel):
    """
    Top-level state passed through LangGraph and the Streamlit UI.
    """
    user_prompt: str

    # Roles selected/edited by HR
    roles: List[RoleSpec] = Field(default_factory=list)

    # Generated JDs keyed by JD.title
    jds: Dict[str, JD] = Field(default_factory=dict)

    # Hiring plan artifacts
    checklist_markdown: Optional[str] = None
    checklist_json: Dict = Field(default_factory=dict)

    # Extra tools / analytics
    emails: Dict[str, str] = Field(default_factory=dict)
    inclusive_warnings: List[str] = Field(default_factory=list)

    # Run-level controls (timeline/budget/location, LLM caps, usage log, etc.)
    global_constraints: Dict = Field(default_factory=dict)
