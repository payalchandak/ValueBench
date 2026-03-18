"""Value profile analysis: normalization, divergence, and statistical tests.

Provides tools for converting raw logistic-regression coefficients into
interpretable value priority distributions and comparing them across
decision makers.
"""

from __future__ import annotations

import numpy as np
from scipy.special import softmax as _scipy_softmax


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
