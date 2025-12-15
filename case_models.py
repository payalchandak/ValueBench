from pydantic import BaseModel
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