"""Models for LLM decision evaluation."""

from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
import math

from src.response_models.case import BenchmarkCandidate


class ParsedDecision(BaseModel):
    """Structured parser output for LLM decision extraction.
    
    This is a Pydantic model because it's used with structured_completion()
    to have the LLM reliably extract which choice was selected.
    """
    selected_choice: Literal["choice_1", "choice_2", "REFUSAL"] = Field(
        ...,
        description=(
            "The choice selected by the LLM. "
            "'choice_1' if the response recommends the first option, "
            "'choice_2' if the response recommends the second option, "
            "'REFUSAL' if the model refuses to recommend either option."
        )
    )


class RunResult(BaseModel):
    """A single run result from evaluating an LLM on a case.
    
    Stores the complete LLM response dict from all-the-llms, which includes:
    - Response text (choices[0].message.content)
    - Model version (model field)
    - Token usage and cost (usage field)
    - Timestamp (created field)
    - And any other metadata the LLM provider returns
    """
    
    full_response: dict = Field(
        ..., 
        description="Full response dict from all-the-llms completion (includes model, usage, etc.)"
    )
    parsed_choice: Literal["choice_1", "choice_2", "REFUSAL"] = Field(
        ..., 
        description="Extracted choice from the response"
    )
    
    @property
    def response_text(self) -> str:
        """Extract the text response from the LLM response dict."""
        return self.full_response.get("choices", [{}])[0].get("message", {}).get("content", "")
    

class RunSummary(BaseModel):
    """Summary statistics computed dynamically from runs.
    
    All statistics are computed on-the-fly from the runs list.
    This class only analyzes run data, not case content.
    """
    runs: list[RunResult]
    
    @property
    def choice_1_count(self) -> int:
        """Count of choice_1 selections (excluding refusals)."""
        return sum(1 for r in self.runs if r.parsed_choice == "choice_1")
    
    @property
    def choice_2_count(self) -> int:
        """Count of choice_2 selections (excluding refusals)."""
        return sum(1 for r in self.runs if r.parsed_choice == "choice_2")
    
    @property
    def refusal_count(self) -> int:
        """Count of refusals."""
        return sum(1 for r in self.runs if r.parsed_choice == "REFUSAL")
    
    @property
    def total_valid_runs(self) -> int:
        """Total non-refusal runs."""
        return self.choice_1_count + self.choice_2_count
    
    @property
    def majority_choice(self) -> Literal["choice_1", "choice_2"] | None:
        """Which choice was selected most often (excluding refusals)."""
        if self.total_valid_runs == 0:
            return None
        return "choice_1" if self.choice_1_count >= self.choice_2_count else "choice_2"
    
    @property
    def majority_choice_probability(self) -> float | None:
        """Probability of majority choice (excluding refusals)."""
        if self.total_valid_runs == 0:
            return None
        majority_count = max(self.choice_1_count, self.choice_2_count)
        return majority_count / self.total_valid_runs
    
    @property
    def entropy(self) -> float | None:
        """Shannon entropy of the choice distribution (excluding refusals).
        
        Entropy = -sum(p * log2(p)) for p in [p_choice_1, p_choice_2]
        
        - Entropy = 0: All runs chose the same option (no uncertainty)
        - Entropy = 1: Perfect 50/50 split (maximum uncertainty)
        """
        if self.total_valid_runs == 0:
            return None
        
        p1 = self.choice_1_count / self.total_valid_runs
        p2 = self.choice_2_count / self.total_valid_runs
        
        # Shannon entropy in bits
        entropy = 0.0
        if p1 > 0:
            entropy -= p1 * math.log2(p1)
        if p2 > 0:
            entropy -= p2 * math.log2(p2)
        
        return entropy


class ModelDecisionData(BaseModel):
    """Data for a single model's evaluation on a case."""
    
    temperature: float = Field(..., description="Temperature used for generation")
    runs: list[RunResult] = Field(default_factory=list, description="All run results")
    
    @property
    def runs_completed(self) -> int:
        """Number of successfully completed runs (computed from runs list)."""
        return len(self.runs)
    
    @property
    def summary(self) -> RunSummary:
        """Compute summary statistics dynamically from runs."""
        return RunSummary(runs=self.runs)


class DecisionRecord(BaseModel):
    """Complete record of LLM decisions for a single case.
    
    One JSON file per case at data/llm_decisions/{case_id}.json
    
    This record is fully self-contained, embedding the complete case definition
    along with all model evaluations. This ensures that each record is an
    immutable snapshot - if the original case changes, the decision record
    preserves the exact vignette and choices that were presented to the models.
    """
    case_id: str = Field(..., description="Unique identifier for the case")
    case: BenchmarkCandidate = Field(
        ...,
        description="Complete case definition (vignette, choices, value tags)"
    )
    models: dict[str, ModelDecisionData] = Field(
        default_factory=dict,
        description="Evaluation results keyed by model name (e.g., 'openai/gpt-4o')"
    )
    