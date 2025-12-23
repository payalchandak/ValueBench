"""
Standalone evaluation records stored separately from case files.

This module defines evaluations that are stored in per-evaluator directories
to avoid merge conflicts when multiple experts evaluate the same cases.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from src.response_models.case import BenchmarkCandidate


class StandaloneEvaluation(BaseModel):
    """
    A single evaluator's evaluation of a case, stored independently.
    
    Uses content hash to reference the exact case version evaluated,
    avoiding data duplication. Only stores the updated case if edits were made.
    """
    case_id: str = Field(..., description="UUID of the case being evaluated")
    case_content_hash: str = Field(..., description="Content hash of the case version evaluated")
    evaluator: str = Field(..., description="Username of the evaluator")
    evaluated_at: datetime = Field(default_factory=datetime.now)
    
    # The evaluation decision
    decision: str = Field(..., description="'approve' or 'reject'")
    
    # Only store edited version if changes were made (minimizes duplication)
    updated_case: Optional[BenchmarkCandidate] = Field(
        None, 
        description="Only populated if evaluator made edits to the case"
    )
    
    # Optional notes
    notes: Optional[str] = Field(None, description="Evaluator's notes or rejection reason")
    
    # Metadata
    evaluation_version: str = "1.0"
    
    @property
    def has_edits(self) -> bool:
        """Check if evaluator made edits."""
        return self.updated_case is not None
    
    def get_case_filename_pattern(self) -> str:
        """Get the expected filename pattern for the evaluated case."""
        return f"case_{self.case_id}_{self.case_content_hash}.json"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

