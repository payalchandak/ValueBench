"""Statistical analysis framework for LLM decision data.

Provides tools for computing value preferences, model comparisons,
and tradeoff matrices with bootstrap confidence intervals.
"""

from src.analysis.bootstrap import bootstrap_indices
from src.analysis.loader import load_decisions
from src.analysis.metrics import refusal_rate, value_preference
from src.analysis.tradeoffs import value_weights
from src.analysis.result_types import BootstrapResult, ValueWeightsResult

__all__ = [
    # Data loading
    "load_decisions",
    # Bootstrap utilities
    "bootstrap_indices",
    # Metrics
    "value_preference",
    "refusal_rate",
    "value_weights",
    # Result types
    "BootstrapResult",
    "ValueWeightsResult",
]
