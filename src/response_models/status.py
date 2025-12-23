"""Generation status enumeration for case lifecycle management."""

from enum import Enum


class GenerationStatus(str, Enum):
    """
    Generation lifecycle status for benchmark cases.
    
    Tracks the state of case generation from initial draft through completion.
    
    Attributes:
        DRAFT: Case is currently being generated (in progress)
        COMPLETED: Case generation finished successfully, ready for evaluation
        FAILED: Case generation failed (e.g., value tagging unsuccessful)
        DEPRECATED: Case has been superseded or should be hidden from active use
    """
    
    DRAFT = "draft"
    COMPLETED = "completed"
    FAILED = "failed"
    DEPRECATED = "deprecated"
    
    def __str__(self) -> str:
        """Return the string value for compatibility with string comparisons."""
        return self.value

