from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import uuid

from src.response_models.case import BenchmarkCandidate, DraftCase
from src.response_models.rubric import ClinicalRubric, EthicalRubric, StylisticRubric, ValueRubric

class IterationRecord(BaseModel):
    """Captures a single state of the case and any evaluations performed on it."""
    iteration: int = Field(..., description="0 for initial seed, 1+ for refinements")
    step_description: str = Field(..., description="e.g., 'initial_seed', 'refinement_1', 'value_tagging', 'final_improvement'")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # The case data at this stage. Can be a simple draft or a full benchmark candidate with values.
    data: Union[DraftCase, BenchmarkCandidate]
    
    # Optional evaluations performed on this specific version
    clinical_evaluation: Optional[ClinicalRubric] = None
    ethical_evaluation: Optional[EthicalRubric] = None
    stylistic_evaluation: Optional[StylisticRubric] = None
    
    # Value validations (Maps value name to its validation rubric)
    value_validations: Dict[str, ValueRubric] = {}
    
    # Optional feedback used to produce the NEXT version
    feedback: Dict[str, str] = {} # e.g., {"clinical": "...", "ethical": "..."}

class SeedContext(BaseModel):
    """The initial parameters that triggered generation."""
    mode: str  # 'literature' or 'synthetic'
    parameters: Dict[str, Any] 

class CaseRecord(BaseModel):
    """The complete record for one generated case, represented as a history of its versions."""
    case_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the case")
    created_at: datetime = Field(default_factory=datetime.now)
    version: str = "1.0"
    
    # Configuration metadata
    model_name: str
    generator_config: Dict[str, Any]
    
    # Provenance
    seed: SeedContext
    
    # Every version of the case from seed to final output
    refinement_history: List[IterationRecord] = []
    
    status: str = "pending" # 'completed', 'failed_refinement', 'flagged'
    
    @property
    def final_case(self) -> Optional[BenchmarkCandidate]:
        """Helper to get the most recent version if it's a BenchmarkCandidate."""
        if not self.refinement_history:
            return None
        last_version = self.refinement_history[-1].data
        if isinstance(last_version, BenchmarkCandidate):
            return last_version
        return None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
