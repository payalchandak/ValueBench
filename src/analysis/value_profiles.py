"""Value profile analysis: normalization, divergence, and statistical tests.

Provides tools for converting raw logistic-regression coefficients into
interpretable value priority distributions and comparing them across
decision makers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import softmax as _scipy_softmax
from scipy.spatial.distance import jensenshannon


def softmax_profile(coefficients: dict[str, float]) -> dict[str, float]:
    """Softmax-normalize raw regression betas into a value priority distribution.

    Applies the softmax function to the coefficient values so they sum to 1
    and can be interpreted as a probability distribution over values (π_V).

    Args:
        coefficients: Mapping of value name to raw β coefficient,
            e.g. ``{"autonomy": 0.8, "beneficence": 1.2, ...}``.

    Returns:
        Dict with the same keys, values replaced by softmax probabilities
        that sum to 1.
    """
    names = list(coefficients.keys())
    betas = np.array([coefficients[n] for n in names], dtype=np.float64)
    probs = _scipy_softmax(betas)
    return {name: float(p) for name, p in zip(names, probs)}


def pairwise_jsd_matrix(
    profiles: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Compute pairwise Jensen-Shannon divergence between value profiles.

    Returns the JSD *divergence* (not distance): for each pair the
    ``scipy.spatial.distance.jensenshannon`` distance is squared so the
    result lives in [0, ln 2] rather than [0, sqrt(ln 2)].

    Args:
        profiles: Mapping of decision-maker identifier to its value
            priority distribution (e.g. output of :func:`softmax_profile`).
            Every inner dict must share the same set of keys.

    Returns:
        Symmetric ``len(profiles) x len(profiles)`` DataFrame with
        decision-maker labels as both index and columns.  Diagonal
        entries are 0.
    """
    ids = list(profiles.keys())
    n = len(ids)

    value_names = list(profiles[ids[0]].keys())
    vectors = np.array(
        [[profiles[mid][v] for v in value_names] for mid in ids],
        dtype=np.float64,
    )

    mat = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            jsd = jensenshannon(vectors[i], vectors[j]) ** 2
            mat[i, j] = jsd
            mat[j, i] = jsd

    return pd.DataFrame(mat, index=ids, columns=ids)
