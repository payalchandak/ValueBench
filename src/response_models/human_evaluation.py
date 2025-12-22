"""
Human Evaluation Models

Pydantic models for human evaluation sessions and case evaluations.
"""

from pydantic import BaseModel
from typing import Optional, Set

from src.response_models.case import BenchmarkCandidate


class CaseEvaluation(BaseModel):
    """Transient view object for displaying evaluation data in UI."""
    case_id: str
    evaluated_at: str
    decision: str  # "approve" or "reject"
    evaluator: str
    original_case: BenchmarkCandidate
    updated_case: Optional[BenchmarkCandidate] = None
    notes: Optional[str] = None
    
    def has_edits(self) -> bool:
        """Check if any edits were made."""
        return self.updated_case is not None
    
    @property
    def final_case(self) -> BenchmarkCandidate:
        """Get the final version (edited if available, otherwise original)."""
        return self.updated_case or self.original_case


class UserSession(BaseModel):
    """User evaluation session - lightweight tracking only."""
    username: str
    session_id: str
    started_at: str
    last_updated: str
    reviewed_case_ids: Set[str] = set()  # Just track IDs, not full data
    
    class Config:
        # Allow set type in JSON schema
        json_schema_extra = {
            "reviewed_case_ids": {"type": "array", "items": {"type": "string"}}
        }

