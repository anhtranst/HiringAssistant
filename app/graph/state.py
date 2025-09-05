# app/graph/state.py
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class RoleSpec(BaseModel):
    role_id: Optional[str] = None
    title: str
    status: str = "match"           # "match" | "suggest" | "unknown"
    confidence: float = 1.0
    file: Optional[str] = None      # path to template json (curated or custom)
    suggestions: List[Dict] = Field(default_factory=list)

    # EDITABLE / ENRICHABLE FIELDS
    must_haves: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    geo: Optional[str] = None


class JD(BaseModel):
    title: str
    mission: str
    responsibilities: List[str] = Field(default_factory=list)
    requirements: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)
    benefits: List[str] = Field(default_factory=list)


class AppState(BaseModel):
    user_prompt: str
    roles: List[RoleSpec] = Field(default_factory=list)
    jds: Dict[str, JD] = Field(default_factory=dict)
    checklist_markdown: Optional[str] = None
    checklist_json: Dict = Field(default_factory=dict)
    emails: Dict[str, str] = Field(default_factory=dict)
    inclusive_warnings: List[str] = Field(default_factory=list)
    global_constraints: Dict = Field(default_factory=dict)
