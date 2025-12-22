from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, model_validator


class TocEntry(BaseModel):
    title: str
    page_label: str


class TocDetectionResult(BaseModel):
    has_toc: bool
    entries: List[TocEntry]

class SectionCases(BaseModel):
    cases: List[str] 

class LiteratureCurationResult(BaseModel):
    """
    Mirrors the JSON shape expected by CurateLiteratureCase.curate_one.
    """

    usable: bool
    reason: str
    scenario_type: Optional[str]
    value_1: Optional[str]
    value_2: Optional[str]
    case: Optional[str]
