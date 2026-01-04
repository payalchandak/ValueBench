"""Generation status enumeration for case lifecycle management."""

from enum import Enum


class CaseStatus(str, Enum):
    """
    Generation lifecycle status for benchmark cases.
    
    Tracks the state of case generation from initial draft through review and approval.
    
    Attributes:
        DRAFT: Case is currently being generated (in progress)
        NEEDS_REVIEW: Case generation finished successfully, awaiting human review
        APPROVED: Case has been approved by a reviewer (R2 or R3)
        FAILED: Case generation failed (e.g., value tagging unsuccessful)
        DEPRECATED: Case has been rejected by a reviewer or superseded
    """
    
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    
    def __str__(self) -> str:
        """Return the string value for compatibility with string comparisons."""
        return self.value

