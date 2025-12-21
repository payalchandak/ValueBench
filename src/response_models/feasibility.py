from typing import Literal

from pydantic import BaseModel


class FeasibilityDecision(BaseModel):
    """
    Feasibility decision for a synthetic seed combination.

    decision:
      - "continue": use this combination to generate a vignette
      - "start_over": discard and resample a new combination
    """

    decision: Literal["continue", "start_over"]


