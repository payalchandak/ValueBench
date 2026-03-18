"""Value profile analysis: normalization, divergence, and statistical tests.

Provides tools for converting raw logistic-regression coefficients into
interpretable value priority distributions and comparing them across
decision makers.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy.special import softmax as _scipy_softmax
from scipy.spatial.distance import jensenshannon
from scipy.stats import chi2
import statsmodels.api as sm

from src.analysis.tradeoffs import _build_regression_data
from src.llm_decisions.models import DecisionRecord


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


def lrt_uniform_null(
    decisions: list[DecisionRecord],
    model: str,
) -> dict:
    """Likelihood-ratio test against a uniform-prioritization null.

    Tests whether a decision maker's value weights are significantly
    non-uniform — i.e., whether we can reject the hypothesis that all
    four ethical values are weighted equally.

    Null  (H0): w_A = w_B = w_N = w_J  (1 free parameter; predictor is
                the sum of all four Δ_value columns)
    Alt   (H1): 4 free parameters      (standard value-weights model)

    The test statistic is  2·(ℓ_alt − ℓ_null)  which is asymptotically
    χ²(3) under H0.

    Args:
        decisions: Decision records from :func:`load_llm_decisions`.
        model: Model identifier (e.g. ``"openai/gpt-5.2"`` or
            ``"human_consensus"``).

    Returns:
        Dict with keys ``lrt_statistic`` (float), ``p_value`` (float),
        ``df`` (int, always 3), ``ll_null`` (float), and ``ll_alt`` (float).

    Raises:
        ValueError: If the model has no valid runs, or if either GLM
            fit fails (e.g. due to perfect separation).
    """
    X, y, n_trials = _build_regression_data(decisions, model)

    glm_kwargs: dict = dict(
        family=sm.families.Binomial(link=sm.families.links.Logit()),
        freq_weights=n_trials,
    )

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        warnings.filterwarnings("ignore", message=".*converge.*")

        # Null model: single shared weight → predictor = sum of deltas
        X_null = X.sum(axis=1, keepdims=True)
        null_result = sm.GLM(y, X_null, **glm_kwargs).fit(disp=False)

        # Alt model: one weight per value (4 predictors)
        alt_result = sm.GLM(y, X, **glm_kwargs).fit(disp=False)

    ll_null = null_result.llf
    ll_alt = alt_result.llf

    df = X.shape[1] - X_null.shape[1]  # 4 − 1 = 3
    lrt_stat = 2.0 * (ll_alt - ll_null)
    # Clamp to ≥ 0 to guard against numerical noise
    lrt_stat = max(lrt_stat, 0.0)
    p_value = float(chi2.sf(lrt_stat, df))

    return {
        "lrt_statistic": float(lrt_stat),
        "p_value": p_value,
        "df": int(df),
        "ll_null": float(ll_null),
        "ll_alt": float(ll_alt),
    }
