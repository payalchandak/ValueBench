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

from src.analysis.result_types import BootstrapResult
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


def bootstrap_mean_jsd(
    profiles: dict[str, dict[str, float]],
    group_a_ids: list[str],
    group_b_ids: list[str],
    n_bootstrap: int = 10_000,
    seed: int | None = None,
) -> dict:
    """Bootstrap CIs for mean within-group JSD for two populations.

    For each bootstrap iteration, decision makers are resampled with
    replacement from each group independently, and the mean pairwise
    Jensen-Shannon divergence within each resampled group is recorded.

    Pairwise JSD values are precomputed once; the bootstrap loop only
    indexes into the cached matrix, so runtime scales with *n_bootstrap*
    rather than the cost of recomputing divergences.

    Args:
        profiles: Mapping of decision-maker ID to its softmax value
            priority distribution (e.g. output of :func:`softmax_profile`).
            Every inner dict must share the same set of keys.
        group_a_ids: Decision-maker IDs belonging to group A.
        group_b_ids: Decision-maker IDs belonging to group B.
        n_bootstrap: Number of bootstrap iterations. Default 10 000.
        seed: Random seed for reproducibility.

    Returns:
        Dict with keys:

        - ``'group_a_mean'``: :class:`BootstrapResult` for group A's mean
          within-group JSD.
        - ``'group_b_mean'``: :class:`BootstrapResult` for group B's mean
          within-group JSD.
        - ``'difference'``: :class:`BootstrapResult` for
          (group A mean) − (group B mean).

    Raises:
        ValueError: If either group has fewer than 2 members (pairwise
            JSD is undefined for a single decision maker).
    """
    n_a, n_b = len(group_a_ids), len(group_b_ids)
    if n_a < 2:
        raise ValueError(f"group_a must have >= 2 members, got {n_a}")
    if n_b < 2:
        raise ValueError(f"group_b must have >= 2 members, got {n_b}")

    # Build a combined index so we can precompute one JSD matrix
    all_ids = list(dict.fromkeys(group_a_ids + group_b_ids))
    id_to_idx = {mid: i for i, mid in enumerate(all_ids)}

    value_names = list(profiles[all_ids[0]].keys())
    vectors = np.array(
        [[profiles[mid][v] for v in value_names] for mid in all_ids],
        dtype=np.float64,
    )

    n_all = len(all_ids)
    jsd_mat = np.zeros((n_all, n_all), dtype=np.float64)
    for i in range(n_all):
        for j in range(i + 1, n_all):
            d = jensenshannon(vectors[i], vectors[j]) ** 2
            jsd_mat[i, j] = d
            jsd_mat[j, i] = d

    idx_a = np.array([id_to_idx[mid] for mid in group_a_ids])
    idx_b = np.array([id_to_idx[mid] for mid in group_b_ids])

    # Precompute upper-triangle index tuples (constant across iterations
    # because the resampled groups always have the same size)
    triu_a = np.triu_indices(n_a, k=1)
    triu_b = np.triu_indices(n_b, k=1)

    rng = np.random.default_rng(seed)
    samples_a = np.empty(n_bootstrap)
    samples_b = np.empty(n_bootstrap)

    for b in range(n_bootstrap):
        boot_a = idx_a[rng.integers(0, n_a, size=n_a)]
        boot_b = idx_b[rng.integers(0, n_b, size=n_b)]

        sub_a = jsd_mat[np.ix_(boot_a, boot_a)]
        samples_a[b] = float(sub_a[triu_a].mean())

        sub_b = jsd_mat[np.ix_(boot_b, boot_b)]
        samples_b[b] = float(sub_b[triu_b].mean())

    return {
        "group_a_mean": BootstrapResult(samples=samples_a),
        "group_b_mean": BootstrapResult(samples=samples_b),
        "difference": BootstrapResult(samples=samples_a - samples_b),
    }


def _mean_within_jsd(
    jsd_mat: np.ndarray,
    indices: np.ndarray,
    triu: tuple[np.ndarray, np.ndarray],
) -> float:
    """Mean of upper-triangle pairwise JSD values for a group."""
    sub = jsd_mat[np.ix_(indices, indices)]
    return float(sub[triu].mean())


def permutation_test_jsd(
    profiles: dict[str, dict[str, float]],
    group_a_ids: list[str],
    group_b_ids: list[str],
    n_permutations: int = 10_000,
    seed: int | None = None,
) -> dict:
    """Permutation test for equal within-group JSD across two populations.

    Tests H0: the mean pairwise JSD within group A equals the mean
    pairwise JSD within group B.  The test statistic is the absolute
    difference |mean_jsd(A) − mean_jsd(B)|.  Under the null, group
    labels are exchangeable, so we build the reference distribution by
    randomly reassigning decision makers to two groups of the original
    sizes and recomputing the statistic.

    The JSD matrix is precomputed once; each permutation only indexes
    into it, keeping runtime proportional to *n_permutations*.

    Args:
        profiles: Mapping of decision-maker ID to its softmax value
            priority distribution (e.g. output of :func:`softmax_profile`).
            Every inner dict must share the same set of keys.
        group_a_ids: Decision-maker IDs belonging to group A.
        group_b_ids: Decision-maker IDs belonging to group B.
        n_permutations: Number of label permutations. Default 10 000.
        seed: Random seed for reproducibility.

    Returns:
        Dict with keys:

        - ``'observed_diff'``: Absolute difference in mean within-group
          JSD between the two groups.
        - ``'p_value'``: Two-sided p-value (fraction of permuted
          statistics ≥ observed, inclusive of the observed value itself).
        - ``'null_distribution'``: 1-D ``ndarray`` of length
          *n_permutations* containing the permuted test statistics.

    Raises:
        ValueError: If either group has fewer than 2 members.
    """
    n_a, n_b = len(group_a_ids), len(group_b_ids)
    if n_a < 2:
        raise ValueError(f"group_a must have >= 2 members, got {n_a}")
    if n_b < 2:
        raise ValueError(f"group_b must have >= 2 members, got {n_b}")

    all_ids = list(dict.fromkeys(group_a_ids + group_b_ids))
    id_to_idx = {mid: i for i, mid in enumerate(all_ids)}

    value_names = list(profiles[all_ids[0]].keys())
    vectors = np.array(
        [[profiles[mid][v] for v in value_names] for mid in all_ids],
        dtype=np.float64,
    )

    n_all = len(all_ids)
    jsd_mat = np.zeros((n_all, n_all), dtype=np.float64)
    for i in range(n_all):
        for j in range(i + 1, n_all):
            d = jensenshannon(vectors[i], vectors[j]) ** 2
            jsd_mat[i, j] = d
            jsd_mat[j, i] = d

    idx_a = np.array([id_to_idx[mid] for mid in group_a_ids])
    idx_b = np.array([id_to_idx[mid] for mid in group_b_ids])

    triu_a = np.triu_indices(n_a, k=1)
    triu_b = np.triu_indices(n_b, k=1)

    observed_diff = abs(
        _mean_within_jsd(jsd_mat, idx_a, triu_a)
        - _mean_within_jsd(jsd_mat, idx_b, triu_b)
    )

    pooled = np.concatenate([idx_a, idx_b])
    rng = np.random.default_rng(seed)
    null_dist = np.empty(n_permutations)

    for p in range(n_permutations):
        rng.shuffle(pooled)
        perm_a = pooled[:n_a]
        perm_b = pooled[n_a:]
        null_dist[p] = abs(
            _mean_within_jsd(jsd_mat, perm_a, triu_a)
            - _mean_within_jsd(jsd_mat, perm_b, triu_b)
        )

    p_value = float(np.mean(null_dist >= observed_diff))

    return {
        "observed_diff": float(observed_diff),
        "p_value": p_value,
        "null_distribution": null_dist,
    }
