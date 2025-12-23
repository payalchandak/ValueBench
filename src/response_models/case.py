from pydantic import BaseModel, model_validator
from enum import Enum
from typing import Literal

ValueAlignmentStatus = Literal['promotes', 'violates', 'neutral']

class ChoiceWithValues(BaseModel):
    choice: str
    autonomy: ValueAlignmentStatus
    beneficence: ValueAlignmentStatus
    nonmaleficence: ValueAlignmentStatus
    justice: ValueAlignmentStatus

class DraftCase(BaseModel):
    vignette: str
    choice_1: str
    choice_2: str

class BenchmarkCandidate(BaseModel):
    vignette: str
    choice_1: ChoiceWithValues
    choice_2: ChoiceWithValues
    
    @model_validator(mode='after')
    def validate_value_conflict(self) -> 'BenchmarkCandidate':
        """Enforces that at least 2 values are in genuine conflict.
        
        A genuine conflict means:
        - At least 2 values are non-neutral
        - For EACH of these values, one choice promotes while the other violates
        
        This ensures subjective ethical dilemmas rather than obvious good vs bad choices.
        
        INVALID: Choice 1 promotes A & B, Choice 2 violates A & B (obvious choice)
        VALID: Choice 1 promotes A & violates B, Choice 2 violates A & promotes B (genuine dilemma)
        """
        values = ["autonomy", "beneficence", "nonmaleficence", "justice"]
        
        # Identify all values with any non-neutral tagging
        involved_values = []
        for value in values:
            tag_1 = getattr(self.choice_1, value)
            tag_2 = getattr(self.choice_2, value)
            if tag_1 != "neutral" or tag_2 != "neutral":
                involved_values.append(value)
        
        # Must have at least 2 values involved
        if len(involved_values) < 2:
            raise ValueError(
                f"Case must involve at least 2 values in conflict, but only {len(involved_values)} "
                f"value(s) are non-neutral: {involved_values}. "
                "Each case must create genuine conflict between at least two values."
            )
        
        # For each involved value, verify it's in genuine conflict
        # (one choice promotes, the other violates)
        for value in involved_values:
            tag_1 = getattr(self.choice_1, value)
            tag_2 = getattr(self.choice_2, value)
            
            # Valid conflict patterns for a value:
            # - Choice 1 promotes, Choice 2 violates
            # - Choice 1 violates, Choice 2 promotes
            is_valid_conflict = (
                (tag_1 == "promotes" and tag_2 == "violates") or
                (tag_1 == "violates" and tag_2 == "promotes")
            )
            
            if not is_valid_conflict:
                raise ValueError(
                    f"Value '{value}' is not in genuine conflict. "
                    f"Choice 1 is tagged as '{tag_1}' and Choice 2 as '{tag_2}'. "
                    f"For a genuine conflict, one choice must promote while the other violates. "
                    f"You cannot have one choice that promotes multiple values while another "
                    f"violates all those values - this creates an obvious answer, not a subjective dilemma."
                )
        
        return self