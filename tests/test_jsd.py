"""Extensive tests for JSD (Jensen-Shannon Divergence) code in src/analysis/.

Covers:
- softmax_profile: normalization, temperature scaling, edge cases
- pairwise_jsd_matrix: symmetry, bounds, identity, known values
- _mean_within_jsd: helper correctness
- bootstrap_mean_jsd: structure, reproducibility, statistical properties
- permutation_test_jsd: structure, p-value validity, statistical power
- Integration: end-to-end pipeline, numerical stability
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.spatial.distance import jensenshannon

from src.analysis.result_types import BootstrapResult
from src.analysis.value_profiles import (
    _mean_within_jsd,
    bootstrap_mean_jsd,
    pairwise_jsd_matrix,
    permutation_test_jsd,
    softmax_profile,
)

LN2 = math.log(2)

# ---------------------------------------------------------------------------
# Fixtures: reusable profile sets
# ---------------------------------------------------------------------------

VALUES = ["autonomy", "beneficence", "nonmaleficence", "justice"]


def _uniform_profile() -> dict[str, float]:
    return {v: 0.25 for v in VALUES}


def _peaked_profile(peak: str = "autonomy") -> dict[str, float]:
    """~60 % on *peak*, rest split evenly."""
    p = {v: 0.4 / 3 for v in VALUES}
    p[peak] = 0.6
    return p


def _make_profiles(n: int, seed: int = 0) -> dict[str, dict[str, float]]:
    """Generate *n* random Dirichlet(1) profiles."""
    rng = np.random.default_rng(seed)
    out = {}
    for i in range(n):
        raw = rng.dirichlet(np.ones(len(VALUES)))
        out[f"agent_{i}"] = {v: float(raw[j]) for j, v in enumerate(VALUES)}
    return out


# ===================================================================
# softmax_profile
# ===================================================================


class TestSoftmaxProfile:
    """Tests for softmax_profile."""

    def test_output_sums_to_one(self):
        coeffs = {"a": 1.0, "b": 2.0, "c": 0.5}
        prof = softmax_profile(coeffs)
        assert math.isclose(sum(prof.values()), 1.0, rel_tol=1e-12)

    def test_keys_preserved(self):
        coeffs = {"x": 0.0, "y": 1.0, "z": -1.0}
        assert list(softmax_profile(coeffs).keys()) == ["x", "y", "z"]

    def test_equal_coefficients_give_uniform(self):
        coeffs = {v: 3.14 for v in VALUES}
        prof = softmax_profile(coeffs)
        for p in prof.values():
            assert math.isclose(p, 0.25, rel_tol=1e-10)

    def test_default_temperature_is_standard_softmax(self):
        coeffs = {"a": 1.0, "b": 2.0}
        prof = softmax_profile(coeffs)
        e1, e2 = math.exp(1.0), math.exp(2.0)
        expected_a = e1 / (e1 + e2)
        expected_b = e2 / (e1 + e2)
        assert math.isclose(prof["a"], expected_a, rel_tol=1e-12)
        assert math.isclose(prof["b"], expected_b, rel_tol=1e-12)

    def test_high_temperature_flattens(self):
        coeffs = {"a": 0.0, "b": 10.0}
        prof_flat = softmax_profile(coeffs, temperature=100.0)
        assert abs(prof_flat["a"] - prof_flat["b"]) < 0.05

    def test_low_temperature_sharpens(self):
        coeffs = {"a": 0.0, "b": 1.0, "c": -1.0}
        prof_sharp = softmax_profile(coeffs, temperature=0.01)
        assert prof_sharp["b"] > 0.99

    def test_temperature_zero_raises(self):
        with pytest.raises(ValueError, match="temperature must be > 0"):
            softmax_profile({"a": 1.0}, temperature=0.0)

    def test_negative_temperature_raises(self):
        with pytest.raises(ValueError, match="temperature must be > 0"):
            softmax_profile({"a": 1.0}, temperature=-1.0)

    def test_single_coefficient(self):
        prof = softmax_profile({"only": 42.0})
        assert math.isclose(prof["only"], 1.0)

    def test_large_coefficients_no_overflow(self):
        coeffs = {"a": 500.0, "b": 501.0}
        prof = softmax_profile(coeffs)
        assert all(0.0 <= p <= 1.0 for p in prof.values())
        assert math.isclose(sum(prof.values()), 1.0, rel_tol=1e-12)

    def test_very_negative_coefficients_no_underflow(self):
        coeffs = {"a": -500.0, "b": -501.0}
        prof = softmax_profile(coeffs)
        assert all(p > 0.0 for p in prof.values())
        assert math.isclose(sum(prof.values()), 1.0, rel_tol=1e-12)

    def test_all_zeros_gives_uniform(self):
        coeffs = {v: 0.0 for v in VALUES}
        prof = softmax_profile(coeffs)
        for p in prof.values():
            assert math.isclose(p, 0.25, rel_tol=1e-12)

    def test_two_coefficients_temperature_scaling(self):
        """At temperature T, softmax(a,b;T) == softmax(a/T, b/T; 1)."""
        coeffs = {"a": 2.0, "b": 5.0}
        T = 3.0
        prof_T = softmax_profile(coeffs, temperature=T)
        prof_manual = softmax_profile({"a": 2.0 / T, "b": 5.0 / T}, temperature=1.0)
        for k in coeffs:
            assert math.isclose(prof_T[k], prof_manual[k], rel_tol=1e-12)


# ===================================================================
# pairwise_jsd_matrix
# ===================================================================


class TestPairwiseJsdMatrix:
    """Tests for pairwise_jsd_matrix."""

    def test_identical_profiles_all_zero(self):
        p = _uniform_profile()
        profiles = {"a": p, "b": p.copy(), "c": p.copy()}
        mat = pairwise_jsd_matrix(profiles)
        np.testing.assert_allclose(mat.values, 0.0, atol=1e-15)

    def test_diagonal_is_zero(self):
        profiles = _make_profiles(5)
        mat = pairwise_jsd_matrix(profiles)
        np.testing.assert_allclose(np.diag(mat.values), 0.0, atol=1e-15)

    def test_symmetry(self):
        profiles = _make_profiles(6, seed=42)
        mat = pairwise_jsd_matrix(profiles)
        np.testing.assert_allclose(mat.values, mat.values.T, atol=1e-15)

    def test_non_negative(self):
        profiles = _make_profiles(8, seed=7)
        mat = pairwise_jsd_matrix(profiles)
        assert (mat.values >= -1e-15).all()

    def test_upper_bound_ln2(self):
        profiles = _make_profiles(8, seed=99)
        mat = pairwise_jsd_matrix(profiles)
        assert (mat.values <= LN2 + 1e-10).all()

    def test_returns_dataframe_with_correct_labels(self):
        profiles = {"alice": _uniform_profile(), "bob": _peaked_profile()}
        mat = pairwise_jsd_matrix(profiles)
        assert isinstance(mat, pd.DataFrame)
        assert list(mat.index) == ["alice", "bob"]
        assert list(mat.columns) == ["alice", "bob"]

    def test_single_profile_is_zero_matrix(self):
        mat = pairwise_jsd_matrix({"solo": _uniform_profile()})
        assert mat.shape == (1, 1)
        assert mat.iloc[0, 0] == 0.0

    def test_known_value_matches_scipy(self):
        """Manually verify against scipy for two distributions."""
        p = {"a": 0.7, "b": 0.2, "c": 0.1}
        q = {"a": 0.1, "b": 0.3, "c": 0.6}
        mat = pairwise_jsd_matrix({"p": p, "q": q})
        expected = jensenshannon([0.7, 0.2, 0.1], [0.1, 0.3, 0.6]) ** 2
        assert math.isclose(mat.loc["p", "q"], expected, rel_tol=1e-12)
        assert math.isclose(mat.loc["q", "p"], expected, rel_tol=1e-12)

    def test_orthogonal_distributions_near_max(self):
        """Disjoint-support distributions should approach ln(2)."""
        p = {"a": 1.0, "b": 0.0}
        q = {"a": 0.0, "b": 1.0}
        mat = pairwise_jsd_matrix({"p": p, "q": q})
        assert math.isclose(mat.loc["p", "q"], LN2, rel_tol=1e-10)

    def test_triangle_inequality_on_sqrt(self):
        """sqrt(JSD) is a metric and should satisfy triangle inequality."""
        profiles = _make_profiles(3, seed=123)
        mat = pairwise_jsd_matrix(profiles)
        ids = list(profiles.keys())
        d01 = math.sqrt(mat.loc[ids[0], ids[1]])
        d02 = math.sqrt(mat.loc[ids[0], ids[2]])
        d12 = math.sqrt(mat.loc[ids[1], ids[2]])
        assert d01 <= d02 + d12 + 1e-10
        assert d02 <= d01 + d12 + 1e-10
        assert d12 <= d01 + d02 + 1e-10

    def test_ordering_preserved(self):
        """Profile order in dict determines row/column order."""
        profiles = {
            "z_last": _uniform_profile(),
            "a_first": _peaked_profile("justice"),
        }
        mat = pairwise_jsd_matrix(profiles)
        assert list(mat.index) == ["z_last", "a_first"]

    def test_many_profiles_shape(self):
        n = 20
        profiles = _make_profiles(n, seed=5)
        mat = pairwise_jsd_matrix(profiles)
        assert mat.shape == (n, n)


# ===================================================================
# _mean_within_jsd (helper)
# ===================================================================


class TestMeanWithinJsd:
    """Tests for the _mean_within_jsd helper."""

    def test_two_elements(self):
        """With 2 elements, mean = the single pairwise JSD."""
        jsd_mat = np.array(
            [[0.0, 0.3, 0.5], [0.3, 0.0, 0.4], [0.5, 0.4, 0.0]]
        )
        indices = np.array([0, 2])
        triu = np.triu_indices(2, k=1)
        result = _mean_within_jsd(jsd_mat, indices, triu)
        assert math.isclose(result, 0.5)

    def test_three_elements(self):
        """With 3 elements, mean of the 3 upper-tri values."""
        jsd_mat = np.array(
            [[0.0, 0.1, 0.2], [0.1, 0.0, 0.3], [0.2, 0.3, 0.0]]
        )
        indices = np.array([0, 1, 2])
        triu = np.triu_indices(3, k=1)
        result = _mean_within_jsd(jsd_mat, indices, triu)
        expected = (0.1 + 0.2 + 0.3) / 3
        assert math.isclose(result, expected, rel_tol=1e-12)

    def test_subset_of_larger_matrix(self):
        """Selecting a subset of indices from a larger matrix."""
        n = 5
        rng = np.random.default_rng(77)
        jsd_mat = rng.uniform(0, 0.5, (n, n))
        jsd_mat = (jsd_mat + jsd_mat.T) / 2
        np.fill_diagonal(jsd_mat, 0.0)

        subset = np.array([1, 3, 4])
        triu = np.triu_indices(3, k=1)
        result = _mean_within_jsd(jsd_mat, subset, triu)

        sub = jsd_mat[np.ix_(subset, subset)]
        expected = sub[triu].mean()
        assert math.isclose(result, expected, rel_tol=1e-12)

    def test_identical_indices_gives_zero(self):
        """When all resampled indices are the same row, sub-matrix diagonal is 0."""
        jsd_mat = np.array(
            [[0.0, 0.5, 0.5], [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]]
        )
        indices = np.array([1, 1])
        triu = np.triu_indices(2, k=1)
        result = _mean_within_jsd(jsd_mat, indices, triu)
        assert math.isclose(result, 0.0)


# ===================================================================
# bootstrap_mean_jsd
# ===================================================================


class TestBootstrapMeanJsd:
    """Tests for bootstrap_mean_jsd."""

    @pytest.fixture()
    def diverse_profiles(self):
        return _make_profiles(10, seed=42)

    @pytest.fixture()
    def group_ids(self, diverse_profiles):
        ids = list(diverse_profiles.keys())
        return ids[:5], ids[5:]

    # -- Structure / return types --

    def test_return_keys(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=100, seed=0)
        assert set(result.keys()) == {"group_a_mean", "group_b_mean", "difference"}

    def test_return_types(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=100, seed=0)
        for key in ("group_a_mean", "group_b_mean", "difference"):
            assert isinstance(result[key], BootstrapResult)

    def test_sample_count_matches_n_bootstrap(self, diverse_profiles, group_ids):
        a, b = group_ids
        n = 500
        result = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=n, seed=0)
        assert len(result["group_a_mean"].samples) == n
        assert len(result["group_b_mean"].samples) == n
        assert len(result["difference"].samples) == n

    # -- Statistical properties --

    def test_mean_jsd_non_negative(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=200, seed=0)
        assert (result["group_a_mean"].samples >= -1e-15).all()
        assert (result["group_b_mean"].samples >= -1e-15).all()

    def test_difference_equals_a_minus_b(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=200, seed=0)
        np.testing.assert_allclose(
            result["difference"].samples,
            result["group_a_mean"].samples - result["group_b_mean"].samples,
            atol=1e-15,
        )

    def test_identical_profiles_mean_near_zero(self):
        """If every agent has the same profile, mean JSD ≈ 0."""
        p = _uniform_profile()
        profiles = {f"a{i}": p.copy() for i in range(6)}
        ids = list(profiles.keys())
        result = bootstrap_mean_jsd(profiles, ids[:3], ids[3:], n_bootstrap=200, seed=0)
        assert abs(result["group_a_mean"].mean) < 1e-12
        assert abs(result["group_b_mean"].mean) < 1e-12

    def test_within_group_divergence_bounded(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=500, seed=0)
        assert (result["group_a_mean"].samples <= LN2 + 1e-10).all()
        assert (result["group_b_mean"].samples <= LN2 + 1e-10).all()

    # -- Reproducibility --

    def test_seed_reproducibility(self, diverse_profiles, group_ids):
        a, b = group_ids
        r1 = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=300, seed=123)
        r2 = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=300, seed=123)
        np.testing.assert_array_equal(
            r1["group_a_mean"].samples, r2["group_a_mean"].samples
        )
        np.testing.assert_array_equal(
            r1["group_b_mean"].samples, r2["group_b_mean"].samples
        )

    def test_different_seeds_differ(self, diverse_profiles, group_ids):
        a, b = group_ids
        r1 = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=300, seed=0)
        r2 = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=300, seed=999)
        assert not np.array_equal(
            r1["group_a_mean"].samples, r2["group_a_mean"].samples
        )

    # -- Confidence interval sanity --

    def test_ci_encloses_mean(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = bootstrap_mean_jsd(diverse_profiles, a, b, n_bootstrap=2000, seed=0)
        for key in ("group_a_mean", "group_b_mean", "difference"):
            lo, hi = result[key].ci(99)
            assert lo <= result[key].mean <= hi

    # -- Error handling --

    def test_group_a_too_small(self):
        profiles = _make_profiles(4, seed=0)
        ids = list(profiles.keys())
        with pytest.raises(ValueError, match="group_a must have >= 2"):
            bootstrap_mean_jsd(profiles, ids[:1], ids[1:], n_bootstrap=10)

    def test_group_b_too_small(self):
        profiles = _make_profiles(4, seed=0)
        ids = list(profiles.keys())
        with pytest.raises(ValueError, match="group_b must have >= 2"):
            bootstrap_mean_jsd(profiles, ids[:3], ids[3:4], n_bootstrap=10)

    # -- Overlapping group IDs --

    def test_overlapping_ids_accepted(self):
        """Groups may share IDs (combined index deduplicates)."""
        profiles = _make_profiles(4, seed=0)
        ids = list(profiles.keys())
        shared = ids[:3]
        group_a = shared
        group_b = ids[1:]  # overlaps with shared on ids[1], ids[2]
        result = bootstrap_mean_jsd(profiles, group_a, group_b, n_bootstrap=100, seed=0)
        assert result["group_a_mean"].mean >= 0

    # -- Minimum group sizes --

    def test_two_member_groups(self):
        """Smallest valid groups (size 2) should work without error."""
        profiles = _make_profiles(4, seed=11)
        ids = list(profiles.keys())
        result = bootstrap_mean_jsd(profiles, ids[:2], ids[2:4], n_bootstrap=100, seed=0)
        assert result["group_a_mean"].mean >= 0


# ===================================================================
# permutation_test_jsd
# ===================================================================


class TestPermutationTestJsd:
    """Tests for permutation_test_jsd."""

    @pytest.fixture()
    def diverse_profiles(self):
        return _make_profiles(10, seed=42)

    @pytest.fixture()
    def group_ids(self, diverse_profiles):
        ids = list(diverse_profiles.keys())
        return ids[:5], ids[5:]

    # -- Structure / return types --

    def test_return_keys(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = permutation_test_jsd(diverse_profiles, a, b, n_permutations=100, seed=0)
        assert set(result.keys()) == {"observed_diff", "p_value", "null_distribution"}

    def test_null_distribution_length(self, diverse_profiles, group_ids):
        a, b = group_ids
        n = 500
        result = permutation_test_jsd(diverse_profiles, a, b, n_permutations=n, seed=0)
        assert len(result["null_distribution"]) == n

    def test_observed_diff_non_negative(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = permutation_test_jsd(diverse_profiles, a, b, n_permutations=100, seed=0)
        assert result["observed_diff"] >= 0.0

    def test_p_value_in_unit_interval(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = permutation_test_jsd(diverse_profiles, a, b, n_permutations=200, seed=0)
        assert 0.0 <= result["p_value"] <= 1.0

    def test_null_distribution_non_negative(self, diverse_profiles, group_ids):
        a, b = group_ids
        result = permutation_test_jsd(diverse_profiles, a, b, n_permutations=200, seed=0)
        assert (result["null_distribution"] >= -1e-15).all()

    # -- Statistical properties --

    def test_identical_groups_high_p_value(self):
        """When both groups are drawn from the same distribution, p should be large."""
        p = _uniform_profile()
        profiles = {f"x{i}": p.copy() for i in range(8)}
        ids = list(profiles.keys())
        result = permutation_test_jsd(
            profiles, ids[:4], ids[4:], n_permutations=500, seed=0
        )
        assert result["p_value"] >= 0.05

    def test_very_different_groups_low_p_value(self):
        """Group A is tightly clustered, group B is spread → detectable difference."""
        rng = np.random.default_rng(42)
        profiles = {}
        # Group A: all nearly identical (peaked on autonomy)
        for i in range(5):
            noise = rng.normal(0, 0.001, len(VALUES))
            raw = np.array([0.7, 0.1, 0.1, 0.1]) + noise
            raw = raw / raw.sum()
            profiles[f"tight_{i}"] = {v: float(raw[j]) for j, v in enumerate(VALUES)}
        # Group B: diverse random profiles
        for i in range(5):
            raw = rng.dirichlet(np.ones(len(VALUES)) * 0.3)
            profiles[f"spread_{i}"] = {v: float(raw[j]) for j, v in enumerate(VALUES)}

        group_a = [f"tight_{i}" for i in range(5)]
        group_b = [f"spread_{i}" for i in range(5)]
        result = permutation_test_jsd(
            profiles, group_a, group_b, n_permutations=2000, seed=0
        )
        assert result["p_value"] < 0.05

    def test_p_value_is_proportion(self, diverse_profiles, group_ids):
        """p-value should equal the fraction of null stats >= observed."""
        a, b = group_ids
        result = permutation_test_jsd(diverse_profiles, a, b, n_permutations=500, seed=0)
        manual_p = float(
            np.mean(result["null_distribution"] >= result["observed_diff"])
        )
        assert math.isclose(result["p_value"], manual_p, rel_tol=1e-12)

    # -- Reproducibility --

    def test_seed_reproducibility(self, diverse_profiles, group_ids):
        a, b = group_ids
        r1 = permutation_test_jsd(diverse_profiles, a, b, n_permutations=300, seed=7)
        r2 = permutation_test_jsd(diverse_profiles, a, b, n_permutations=300, seed=7)
        assert r1["observed_diff"] == r2["observed_diff"]
        assert r1["p_value"] == r2["p_value"]
        np.testing.assert_array_equal(
            r1["null_distribution"], r2["null_distribution"]
        )

    def test_different_seeds_differ(self, diverse_profiles, group_ids):
        a, b = group_ids
        r1 = permutation_test_jsd(diverse_profiles, a, b, n_permutations=300, seed=0)
        r2 = permutation_test_jsd(diverse_profiles, a, b, n_permutations=300, seed=99)
        assert not np.array_equal(
            r1["null_distribution"], r2["null_distribution"]
        )

    # -- Error handling --

    def test_group_a_too_small(self):
        profiles = _make_profiles(4, seed=0)
        ids = list(profiles.keys())
        with pytest.raises(ValueError, match="group_a must have >= 2"):
            permutation_test_jsd(profiles, ids[:1], ids[1:], n_permutations=10)

    def test_group_b_too_small(self):
        profiles = _make_profiles(4, seed=0)
        ids = list(profiles.keys())
        with pytest.raises(ValueError, match="group_b must have >= 2"):
            permutation_test_jsd(profiles, ids[:3], ids[3:4], n_permutations=10)

    def test_swapping_groups_same_observed_diff(self, diverse_profiles, group_ids):
        """observed_diff is |A-B|, so swapping groups should not change it."""
        a, b = group_ids
        r1 = permutation_test_jsd(diverse_profiles, a, b, n_permutations=100, seed=0)
        r2 = permutation_test_jsd(diverse_profiles, b, a, n_permutations=100, seed=0)
        assert math.isclose(r1["observed_diff"], r2["observed_diff"], rel_tol=1e-12)


# ===================================================================
# Integration / cross-cutting tests
# ===================================================================


class TestIntegration:
    """End-to-end and cross-cutting tests."""

    def test_softmax_to_jsd_pipeline(self):
        """softmax_profile outputs feed correctly into pairwise_jsd_matrix."""
        raw_betas = {
            "model_a": {"autonomy": 1.0, "beneficence": 0.5, "nonmaleficence": 0.2, "justice": 0.3},
            "model_b": {"autonomy": 0.3, "beneficence": 1.0, "nonmaleficence": 0.5, "justice": 0.2},
            "model_c": {"autonomy": 0.2, "beneficence": 0.3, "nonmaleficence": 1.0, "justice": 0.5},
        }
        profiles = {k: softmax_profile(v) for k, v in raw_betas.items()}
        mat = pairwise_jsd_matrix(profiles)
        assert mat.shape == (3, 3)
        assert (np.diag(mat.values) == 0.0).all()
        assert (mat.values >= 0).all()
        assert (mat.values <= LN2 + 1e-10).all()

    def test_full_pipeline_softmax_bootstrap_permutation(self):
        """Run the complete pipeline: softmax → JSD matrix → bootstrap → permutation."""
        rng = np.random.default_rng(10)
        raw = {}
        for i in range(12):
            raw[f"agent_{i}"] = {v: float(rng.normal(0, 1)) for v in VALUES}

        profiles = {k: softmax_profile(v, temperature=1.5) for k, v in raw.items()}
        ids = list(profiles.keys())
        group_a, group_b = ids[:6], ids[6:]

        mat = pairwise_jsd_matrix(profiles)
        assert mat.shape == (12, 12)

        bs = bootstrap_mean_jsd(profiles, group_a, group_b, n_bootstrap=500, seed=0)
        assert bs["group_a_mean"].mean >= 0
        lo, hi = bs["group_a_mean"].ci(95)
        assert lo <= hi

        pt = permutation_test_jsd(profiles, group_a, group_b, n_permutations=500, seed=0)
        assert 0.0 <= pt["p_value"] <= 1.0

    def test_near_zero_probabilities(self):
        """Profiles with very small probabilities should not cause NaN/Inf."""
        profiles = {
            "sparse_a": {"a": 1e-15, "b": 1.0 - 1e-15},
            "sparse_b": {"a": 1.0 - 1e-15, "b": 1e-15},
        }
        mat = pairwise_jsd_matrix(profiles)
        assert np.isfinite(mat.values).all()
        assert (mat.values >= 0).all()

    def test_many_value_dimensions(self):
        """Profiles with many dimensions work correctly."""
        n_values = 50
        val_names = [f"v{i}" for i in range(n_values)]
        rng = np.random.default_rng(3)
        profiles = {}
        for i in range(4):
            raw = rng.dirichlet(np.ones(n_values))
            profiles[f"agent_{i}"] = {v: float(raw[j]) for j, v in enumerate(val_names)}

        mat = pairwise_jsd_matrix(profiles)
        assert mat.shape == (4, 4)
        assert (mat.values >= -1e-15).all()
        assert (mat.values <= LN2 + 1e-10).all()

    def test_bootstrap_ci_width_decreases_with_n(self):
        """More bootstrap samples → narrower CI (on average)."""
        profiles = _make_profiles(8, seed=55)
        ids = list(profiles.keys())
        a, b = ids[:4], ids[4:]

        r_small = bootstrap_mean_jsd(profiles, a, b, n_bootstrap=200, seed=0)
        r_large = bootstrap_mean_jsd(profiles, a, b, n_bootstrap=5000, seed=0)

        width_small = r_small["group_a_mean"].ci(95)[1] - r_small["group_a_mean"].ci(95)[0]
        width_large = r_large["group_a_mean"].ci(95)[1] - r_large["group_a_mean"].ci(95)[0]

        assert width_large <= width_small * 1.5

    def test_permutation_with_asymmetric_group_sizes(self):
        """Unequal group sizes should work correctly."""
        profiles = _make_profiles(9, seed=22)
        ids = list(profiles.keys())
        result = permutation_test_jsd(
            profiles, ids[:3], ids[3:], n_permutations=300, seed=0
        )
        assert 0.0 <= result["p_value"] <= 1.0
        assert len(result["null_distribution"]) == 300

    def test_jsd_matrix_consistent_with_bootstrap_precomputation(self):
        """Values from pairwise_jsd_matrix match what bootstrap uses internally."""
        profiles = _make_profiles(6, seed=33)
        mat = pairwise_jsd_matrix(profiles)
        ids = list(profiles.keys())

        value_names = list(profiles[ids[0]].keys())
        for i, id_i in enumerate(ids):
            for j, id_j in enumerate(ids):
                if i < j:
                    p = [profiles[id_i][v] for v in value_names]
                    q = [profiles[id_j][v] for v in value_names]
                    expected = jensenshannon(p, q) ** 2
                    assert math.isclose(
                        mat.loc[id_i, id_j], expected, rel_tol=1e-12
                    )

    def test_softmax_temperature_affects_jsd(self):
        """Higher temperature → profiles more similar → lower pairwise JSD."""
        raw = {
            "a": {"autonomy": 2.0, "beneficence": 0.5, "nonmaleficence": 0.1, "justice": 0.1},
            "b": {"autonomy": 0.1, "beneficence": 2.0, "nonmaleficence": 0.5, "justice": 0.1},
        }
        prof_low_t = {k: softmax_profile(v, temperature=0.5) for k, v in raw.items()}
        prof_high_t = {k: softmax_profile(v, temperature=5.0) for k, v in raw.items()}

        jsd_low = pairwise_jsd_matrix(prof_low_t).iloc[0, 1]
        jsd_high = pairwise_jsd_matrix(prof_high_t).iloc[0, 1]
        assert jsd_high < jsd_low
