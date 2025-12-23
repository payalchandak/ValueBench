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
    def validate_minimum_values(self) -> 'BenchmarkCandidate':
        """Ensures at least 2 values are non-neutral across both choices."""
        values = ["autonomy", "beneficence", "nonmaleficence", "justice"]
        involved_values = set()
        
        for value in values:
            tag_1 = getattr(self.choice_1, value)
            tag_2 = getattr(self.choice_2, value)
            if tag_1 != "neutral" or tag_2 != "neutral":
                involved_values.add(value)
        
        if len(involved_values) < 2:
            raise ValueError(
                f"Case must involve at least 2 values, but only {len(involved_values)} "
                f"value(s) are non-neutral: {involved_values}. "
                "Please tag at least 2 values as promoting or violating."
            )
        return self