"""Statistical analysis framework for LLM decision data.

Provides tools for computing value preferences, model comparisons,
and tradeoff matrices with bootstrap confidence intervals.
"""

from src.analysis.bootstrap import bootstrap_indices
from src.analysis.loader import (
    load_all_decisions,
    load_human_decisions,
    load_llm_decisions,
    load_participant_registry,
)
from src.analysis.metrics import (
    agreement_rate,
    HUMAN_CONSENSUS,
    HumanCaseConsensus,
    human_consensus,
    refusal_rate,
    value_preference,
)
from src.analysis.tradeoffs import value_weights
from src.analysis.result_types import BootstrapResult, ValueWeightsResult

__all__ = [
    # Data loading
    "load_llm_decisions",
    "load_human_decisions",
    "load_all_decisions",
    "load_participant_registry",
    # Bootstrap utilities
    "bootstrap_indices",
    # Metrics
    "value_preference",
    "refusal_rate",
    "agreement_rate",
    "human_consensus",
    "value_weights",
    # Constants
    "HUMAN_CONSENSUS",
    # Result types
    "BootstrapResult",
    "HumanCaseConsensus",
    "ValueWeightsResult",
]
