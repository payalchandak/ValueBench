"""
Standalone evaluation records stored separately from case files.

This module defines evaluations that are stored in per-evaluator directories
to avoid merge conflicts when multiple experts evaluate the same cases.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class ProblemAxis(str, Enum):
    """Categories of problems that can be identified in a case."""
    CLINICAL = "clinical"
    ETHICAL = "ethical"
    LEGAL = "legal"
    STYLISTIC = "stylistic"
    OTHER = "other"


class StandaloneEvaluation(BaseModel):
    """
    A single evaluator's evaluation of a case, stored independently.
    
    Uses content hash to reference the exact case version evaluated,
    avoiding data duplication.
    """
    case_id: str = Field(..., description="UUID of the case being evaluated")
    case_content_hash: str = Field(..., description="Content hash of the case version evaluated")
    evaluator: str = Field(..., description="Username of the evaluator")
    evaluated_at: datetime = Field(default_factory=datetime.now)
    
    # The evaluation decision
    decision: str = Field(..., description="'approve' or 'reject'")
    
    # Optional notes
    notes: Optional[str] = Field(None, description="Evaluator's notes or rejection reason")
    
    # Structured feedback (new fields)
    problem_axes: Optional[List[ProblemAxis]] = Field(
        None,
        description="Categories of problems identified (clinical, ethical, legal, stylistic, other)"
    )
    
    comments: Optional[str] = Field(
        None,
        description="Detailed feedback, recommended changes, or explanations"
    )
    
    # Metadata
    evaluation_version: str = "1.1"  # Bumped version for new fields
    
    def get_case_filename_pattern(self) -> str:
        """Get the expected filename pattern for the evaluated case."""
        return f"case_{self.case_id}_{self.case_content_hash}.json"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

