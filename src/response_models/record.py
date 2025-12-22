from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import uuid

from src.response_models.case import BenchmarkCandidate, DraftCase
from src.response_models.rubric import ClinicalRubric, EthicalRubric, StylisticRubric, ValueRubric

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
    
    status: str = "pending" # 'completed', 'failed_refinement', 'flagged', 'approved', 'rejected'
    
    @property
    def final_case(self) -> Optional[BenchmarkCandidate]:
        """Helper to get the most recent version if it's a BenchmarkCandidate."""
        if not self.refinement_history:
            return None
        last_version = self.refinement_history[-1].data
        if isinstance(last_version, BenchmarkCandidate):
            return last_version
        return None
    
    def add_human_evaluation(
        self,
        decision: str,
        evaluator: str,
        updated_case: Optional[BenchmarkCandidate] = None,
        notes: Optional[str] = None
    ) -> None:
        """
        Add a human evaluation iteration to the case record.
        
        Args:
            decision: "approve" or "reject"
            evaluator: Username of the evaluator
            updated_case: Optional edited version of the case
            notes: Optional evaluation notes
            
        Raises:
            ValueError: If case has no final version or already evaluated
        """
        if decision not in ["approve", "reject"]:
            raise ValueError(f"Invalid decision: {decision}. Must be 'approve' or 'reject'")
        
        current_case = self.final_case
        if not current_case:
            raise ValueError("Cannot evaluate case without a final BenchmarkCandidate")
        
        # Check if already evaluated (avoid duplicates)
        if self.get_latest_evaluation() is not None:
            raise ValueError(
                f"Case already has a human evaluation. "
                f"Current status: {self.status}. "
                f"Use a different method to update existing evaluations."
            )
        
        # Use edited case if provided, otherwise use current
        final_case = updated_case if updated_case else current_case
        iteration_num = len(self.refinement_history)
        
        evaluation_metadata = {
            "decision": decision,
            "evaluator": evaluator,
            "notes": notes,
            "has_edits": updated_case is not None,
            "evaluated_at": datetime.now().isoformat()
        }
        
        new_iteration = IterationRecord(
            iteration=iteration_num,
            step_description="human_evaluation",
            timestamp=datetime.now(),
            data=final_case,
            human_evaluation=evaluation_metadata
        )
        
        self.refinement_history.append(new_iteration)
        
        # Update status based on decision
        self.status = "approved" if decision == "approve" else "rejected"
    
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
