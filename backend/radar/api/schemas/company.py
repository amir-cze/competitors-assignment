from __future__ import annotations

from pydantic import BaseModel, Field


class CompanyOut(BaseModel):
    text: str
    is_default: bool


class CompanyIn(BaseModel):
    text: str = Field(max_length=4000)
