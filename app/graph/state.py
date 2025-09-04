from __future__ import annotations
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class RoleSpec(BaseModel):
    title: str
    seniority: Optional[str] = None
    geo: Optional[str] = None
    must_haves: List[str] = Field(default_factory=list)
    nice_to_haves: List[str] = Field(default_factory=list)

class JD(BaseModel):
    title: str
    mission: str
    responsibilities: List[str]
    requirements: List[str]
    nice_to_haves: List[str]
    benefits: List[str]

class AppState(BaseModel):
    user_prompt: str = ""
    global_constraints: Dict[str, Any] = Field(default_factory=dict)

    roles: List[RoleSpec] = Field(default_factory=list)
    jds: Dict[str, JD] = Field(default_factory=dict)

    checklist_markdown: Optional[str] = None
    checklist_json: Optional[Dict[str, Any]] = None

    inclusive_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    emails: Dict[str, str] = Field(default_factory=dict)
