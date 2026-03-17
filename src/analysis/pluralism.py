"""Pluralism analysis building blocks.

Domain-agnostic statistics and atomic per-case computations for
measuring disagreement, inter-rater reliability, and value tensions.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from src.analysis.metrics import _get_alignment
from src.llm_decisions.models import DecisionRecord
from src.response_models.case import BenchmarkCandidate, VALUE_NAMES


def value_tension_pairs(case: BenchmarkCandidate) -> list[tuple[str, str]]:
    """Detect which pairs of values are in tension for a case.

    A tension exists between values X and Y when the option that better
    aligns with X necessarily moves away from Y (and vice versa).
    Formally: ``delta_X * delta_Y < 0`` where
    ``delta_v = align(choice_1, v) - align(choice_2, v)``.

    Args:
        case: A benchmark case with two choices and value-alignment tags.

    Returns:
        Alphabetically ordered ``(X, Y)`` pairs (``X < Y``) whose
        alignment deltas have opposite signs.  Empty list when no
        tension exists.
    """
    deltas = {
        v: _get_alignment(case.choice_1, v) - _get_alignment(case.choice_2, v)
        for v in VALUE_NAMES
    }

    pairs: list[tuple[str, str]] = []
    values = sorted(deltas)
    for i, x in enumerate(values):
        for y in values[i + 1:]:
            if deltas[x] * deltas[y] < 0:
                pairs.append((x, y))
    return pairs


def build_kappa_input_table(
    decisions: list[DecisionRecord],
    raters: list[str],
) -> tuple[NDArray, list[str]]:
    """Build a rater-count table consumable by agreement metrics.

    For every case in *decisions*, counts how many of the supplied
    *raters* chose each option (``choice_1`` / ``choice_2``).  Refusals
    are excluded, so each row sums to at most ``len(raters)``.

    Only cases where at least one rater has a valid (non-refusal)
    response are included in the output.

    Args:
        decisions: Decision records (from ``load_all_decisions`` etc.).
        raters: Rater identifiers (e.g. physician IDs or model IDs).

    Returns:
        ``(table, case_ids)`` where *table* has shape ``(n_cases, 2)``
        with columns ``[choice_1_count, choice_2_count]`` and *case_ids*
        lists the corresponding case identifiers.
    """
    rows: list[list[int]] = []
    case_ids: list[str] = []

    for record in decisions:
        c1 = 0
        c2 = 0
        for rater in raters:
            if rater not in record.models:
                continue
            summary = record.models[rater].summary
            c1 += summary.choice_1_count
            c2 += summary.choice_2_count

        if c1 + c2 == 0:
            continue

        rows.append([c1, c2])
        case_ids.append(record.case_id)

    return np.array(rows, dtype=int), case_ids
