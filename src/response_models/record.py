from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import uuid
import hashlib
import json as json_module

from src.response_models.case import BenchmarkCandidate, DraftCase
from src.response_models.rubric import ClinicalRubric, EthicalRubric, StylisticRubric, ValueRubric
from src.response_models.status import GenerationStatus

class IterationRecord(BaseModel):
    """Captures a single state of the case and any evaluations performed on it."""
    iteration: int = Field(..., description="0 for initial seed, 1+ for refinements")
    step_description: str = Field(..., description="e.g., 'initial_seed', 'refinement_1', 'value_tagging', 'final_improvement', 'human_evaluation'")
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
    
    # Human evaluation metadata
    human_evaluation: Optional[Dict[str, Any]] = Field(
        None, 
        description="Human evaluation metadata including decision, evaluator, and notes"
    )

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
    
    status: GenerationStatus = Field(
        default=GenerationStatus.DRAFT,
        description="Generation lifecycle status"
    )
    
    @property
    def final_case(self) -> Optional[BenchmarkCandidate]:
        """Helper to get the most recent version if it's a BenchmarkCandidate."""
        if not self.refinement_history:
            return None
        last_version = self.refinement_history[-1].data
        if isinstance(last_version, BenchmarkCandidate):
            return last_version
        return None
    
    def compute_content_hash(self) -> str:
        """
        Compute SHA256 hash of the final case content for content-addressable storage.
        
        Returns:
            First 12 characters of SHA256 hash
            
        Raises:
            ValueError: If no final_case exists
        """
        if not self.final_case:
            raise ValueError("Cannot compute hash without final_case")
        
        # Create deterministic string from final case content
        final = self.final_case
        
        # Handle both ChoiceWithValues objects and dict-like structures
        choice_1_dict = final.choice_1.model_dump() if hasattr(final.choice_1, 'model_dump') else (
            final.choice_1 if isinstance(final.choice_1, dict) else final.choice_1.__dict__
        )
        choice_2_dict = final.choice_2.model_dump() if hasattr(final.choice_2, 'model_dump') else (
            final.choice_2 if isinstance(final.choice_2, dict) else final.choice_2.__dict__
        )
        
        content_dict = {
            "vignette": final.vignette,
            "choice_1": choice_1_dict,
            "choice_2": choice_2_dict,
        }
        content_str = json_module.dumps(content_dict, sort_keys=True)
        
        hash_obj = hashlib.sha256(content_str.encode('utf-8'))
        return hash_obj.hexdigest()[:12]
    
    def add_human_evaluation(
        self,
        decision: str,
        evaluator: str,
        updated_case: Optional[BenchmarkCandidate] = None,
        notes: Optional[str] = None
    ) -> None:
        """
        [DEPRECATED] Add a human evaluation iteration to the case record.
        
        This method is deprecated. Use EvaluationStore.record_evaluation() instead,
        which stores evaluations separately to avoid merge conflicts.
        
        Args:
            decision: "approve" or "reject"
            evaluator: Username of the evaluator
            updated_case: Optional edited version of the case
            notes: Optional evaluation notes
            
        Raises:
            NotImplementedError: Always raised - use EvaluationStore instead
        """
        import warnings
        warnings.warn(
            "CaseRecord.add_human_evaluation() is deprecated. "
            "Use EvaluationStore.record_evaluation() to avoid merge conflicts.",
            DeprecationWarning,
            stacklevel=2
        )
        raise NotImplementedError(
            "Use EvaluationStore.record_evaluation() instead to store evaluations separately."
        )
    
    def get_latest_evaluation(self) -> Optional[Dict[str, Any]]:
        """Get the most recent human evaluation, if any."""
        for iteration in reversed(self.refinement_history):
            if iteration.human_evaluation:
                return {
                    "iteration": iteration.iteration,
                    "timestamp": iteration.timestamp,
                    **iteration.human_evaluation
                }
        return None
    
    def get_evaluation_history(self) -> List[Dict[str, Any]]:
        """Get all human evaluations performed on this case."""
        evaluations = []
        for iteration in self.refinement_history:
            if iteration.human_evaluation:
                evaluations.append({
                    "iteration": iteration.iteration,
                    "timestamp": iteration.timestamp,
                    **iteration.human_evaluation
                })
        return evaluations

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
