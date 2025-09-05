# app/graph/state.py
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field

class RoleSpec(BaseModel):
    # --- Matching/meta ---
    role_id: Optional[str] = None
    title: str
    status: Literal["match", "suggest", "unknown"] = "match"
    confidence: float = 1.0
    file: Optional[str] = None  # path to role template json
    suggestions: List[dict] = Field(default_factory=list)  # [{role_id,title,score}]

    # --- Enrichment fields (filled in node_profile) ---
    seniority: Optional[str] = None
    geo: Optional[str] = None
    must_haves: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)

class JD(BaseModel):
    title: str
    mission: str
    responsibilities: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)
    benefits: List[str] = Field(default_factory=list)

class AppState(BaseModel):
    user_prompt: str
    global_constraints: Dict = Field(default_factory=dict)
    roles: List[RoleSpec] = Field(default_factory=list)
    jds: Dict[str, JD] = Field(default_factory=dict)
    checklist_markdown: Optional[str] = None
    checklist_json: Dict = Field(default_factory=dict)
    emails: Dict = Field(default_factory=dict)
    inclusive_warnings: List[str] = Field(default_factory=list)

