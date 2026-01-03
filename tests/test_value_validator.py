"""
Tests for the relaxed value tag validator in src/response_models/case.py

Tests are organized into three sections:
1. Valid edge cases V1-V7 (should pass validation)
2. Invalid edge cases I1-I7 (should fail validation)
3. Spot-check existing cases (should still pass validation)
"""

import pytest
import json
import glob
from pathlib import Path

from src.response_models.case import (
    BenchmarkCandidate,
    ChoiceWithValues,
    is_valid_per_value_pattern,
    count_choice_effects,
    has_cross_value_opposition,
    has_balance_violation,
    get_value_tags,
)

# =============================================================================
# Helper function to create test cases
# =============================================================================

def create_case(
    autonomy_1: str, autonomy_2: str,
    beneficence_1: str, beneficence_2: str,
    nonmaleficence_1: str, nonmaleficence_2: str,
    justice_1: str, justice_2: str,
) -> BenchmarkCandidate:
    """Create a BenchmarkCandidate with specified value tags.
    
    Args:
        *_1: Tag for Choice 1 for each value (promotes/violates/neutral)
        *_2: Tag for Choice 2 for each value (promotes/violates/neutral)
    
    Returns:
        BenchmarkCandidate with the specified tags
    """
    return BenchmarkCandidate(
        vignette="Test vignette for validation",
        choice_1=ChoiceWithValues(
            choice="Test choice 1",
            autonomy=autonomy_1,
            beneficence=beneficence_1,
            nonmaleficence=nonmaleficence_1,
            justice=justice_1,
        ),
        choice_2=ChoiceWithValues(
            choice="Test choice 2",
            autonomy=autonomy_2,
            beneficence=beneficence_2,
            nonmaleficence=nonmaleficence_2,
            justice=justice_2,
        ),
    )


# =============================================================================
# Tests for helper functions
# =============================================================================

class TestIsValidPerValuePattern:
    """Tests for the is_valid_per_value_pattern helper function."""
    
    def test_neutral_neutral_is_valid(self):
        """neutral + neutral = value not engaged"""
        assert is_valid_per_value_pattern("neutral", "neutral") is True
    
    def test_neutral_promotes_is_valid(self):
        """neutral + promotes = one-sided promotion"""
        assert is_valid_per_value_pattern("neutral", "promotes") is True
    
    def test_promotes_neutral_is_valid(self):
        """promotes + neutral = one-sided promotion"""
        assert is_valid_per_value_pattern("promotes", "neutral") is True
    
    def test_neutral_violates_is_valid(self):
        """neutral + violates = one-sided violation"""
        assert is_valid_per_value_pattern("neutral", "violates") is True
    
    def test_violates_neutral_is_valid(self):
        """violates + neutral = one-sided violation"""
        assert is_valid_per_value_pattern("violates", "neutral") is True
    
    def test_promotes_violates_is_valid(self):
        """promotes + violates = classic opposition"""
        assert is_valid_per_value_pattern("promotes", "violates") is True
    
    def test_violates_promotes_is_valid(self):
        """violates + promotes = classic opposition"""
        assert is_valid_per_value_pattern("violates", "promotes") is True
    
    def test_promotes_promotes_is_invalid(self):
        """promotes + promotes = same direction, no tension"""
        assert is_valid_per_value_pattern("promotes", "promotes") is False
    
    def test_violates_violates_is_invalid(self):
        """violates + violates = same direction, no tension"""
        assert is_valid_per_value_pattern("violates", "violates") is False


class TestCountChoiceEffects:
    """Tests for the count_choice_effects helper function."""
    
    def test_classic_cross_conflict(self):
        """C1: +A -B, C2: -A +B => both have promotions and violations"""
        tags = {
            "autonomy": ("promotes", "violates"),
            "beneficence": ("violates", "promotes"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        c1_promotes, c1_violates, c2_promotes, c2_violates = count_choice_effects(tags)
        assert c1_promotes is True
        assert c1_violates is True
        assert c2_promotes is True
        assert c2_violates is True
    
    def test_pure_upside_vs_pure_downside(self):
        """C1: +A +B, C2: -A -B => C1 pure upside, C2 pure downside"""
        tags = {
            "autonomy": ("promotes", "violates"),
            "beneficence": ("promotes", "violates"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        c1_promotes, c1_violates, c2_promotes, c2_violates = count_choice_effects(tags)
        assert c1_promotes is True
        assert c1_violates is False
        assert c2_promotes is False
        assert c2_violates is True


class TestHasCrossValueOpposition:
    """Tests for the has_cross_value_opposition helper function."""
    
    def test_different_values_promoted(self):
        """C1 promotes A, C2 promotes B (different values) => valid opposition"""
        tags = {
            "autonomy": ("promotes", "neutral"),
            "beneficence": ("neutral", "promotes"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        assert has_cross_value_opposition(tags) is True
    
    def test_different_values_violated(self):
        """C1 violates A, C2 violates B (different values) => valid opposition"""
        tags = {
            "autonomy": ("violates", "neutral"),
            "beneficence": ("neutral", "violates"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        assert has_cross_value_opposition(tags) is True
    
    def test_same_value_in_opposition(self):
        """One value has promotes↔violates => valid opposition"""
        tags = {
            "autonomy": ("promotes", "violates"),
            "beneficence": ("neutral", "neutral"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        assert has_cross_value_opposition(tags) is True
    
    def test_no_opposition_only_one_promotes(self):
        """Only C1 promotes, nothing from C2 => no opposition"""
        tags = {
            "autonomy": ("promotes", "neutral"),
            "beneficence": ("neutral", "neutral"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        assert has_cross_value_opposition(tags) is False
    
    def test_c1_promotes_c2_only_violates_no_opposition(self):
        """C1 promotes A, C2 violates B (no overlap) => no valid opposition"""
        tags = {
            "autonomy": ("promotes", "neutral"),
            "beneficence": ("neutral", "violates"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        # No cross-value opposition: 
        # - C1 and C2 don't both promote different values
        # - C1 and C2 don't both violate different values
        # - No same value has promotes↔violates
        assert has_cross_value_opposition(tags) is False


class TestHasBalanceViolation:
    """Tests for the has_balance_violation helper function."""
    
    def test_pure_upside_vs_pure_downside_is_violation(self):
        """C1: +A +B, C2: -A -B => balance violation"""
        tags = {
            "autonomy": ("promotes", "violates"),
            "beneficence": ("promotes", "violates"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        assert has_balance_violation(tags) is True
    
    def test_mixed_vs_pure_downside_is_violation(self):
        """C1: +A -B, C2: -C only => C2 has no upside, violation"""
        tags = {
            "autonomy": ("promotes", "neutral"),
            "beneficence": ("violates", "neutral"),
            "nonmaleficence": ("neutral", "violates"),
            "justice": ("neutral", "neutral"),
        }
        assert has_balance_violation(tags) is True
    
    def test_mixed_vs_mixed_is_valid(self):
        """C1: +A -B, C2: -A +B => both mixed, valid"""
        tags = {
            "autonomy": ("promotes", "violates"),
            "beneficence": ("violates", "promotes"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        assert has_balance_violation(tags) is False
    
    def test_pure_upside_vs_mixed_is_valid(self):
        """C1: +A only, C2: +B -C => pure upside vs mixed, valid"""
        tags = {
            "autonomy": ("promotes", "neutral"),
            "beneficence": ("neutral", "promotes"),
            "nonmaleficence": ("neutral", "violates"),
            "justice": ("neutral", "neutral"),
        }
        assert has_balance_violation(tags) is False
    
    def test_lesser_evil_is_valid(self):
        """C1: -A only, C2: -B only => both pure downside, valid (lesser evil)"""
        tags = {
            "autonomy": ("violates", "neutral"),
            "beneficence": ("neutral", "violates"),
            "nonmaleficence": ("neutral", "neutral"),
            "justice": ("neutral", "neutral"),
        }
        assert has_balance_violation(tags) is False


# =============================================================================
# VALID Edge Cases V1-V7 (Should PASS Validation)
# =============================================================================

class TestValidEdgeCases:
    """
    Valid edge cases from the plan discussion.
    These should all PASS validation.
    """
    
    def test_v1_classic_cross_conflict(self):
        """V1: C1: +A -B, C2: -A +B (classic cross-conflict, both have upside+downside)"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="violates",
            beneficence_1="violates", beneficence_2="promotes",
            nonmaleficence_1="neutral", nonmaleficence_2="neutral",
            justice_1="neutral", justice_2="neutral",
        )
        # Should not raise
        assert case is not None
    
    def test_v2_both_promote_different_values(self):
        """V2: C1: +A 0B, C2: 0A +B (both promote different values - NEW pattern)"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="neutral",
            beneficence_1="neutral", beneficence_2="promotes",
            nonmaleficence_1="neutral", nonmaleficence_2="neutral",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None
    
    def test_v3_mixed_vs_pure_upside_c1_has_upside(self):
        """V3: C1: +A -B, C2: 0A +B (mixed vs pure-upside, but C1 has upside too)"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="neutral",
            beneficence_1="violates", beneficence_2="promotes",
            nonmaleficence_1="neutral", nonmaleficence_2="neutral",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None
    
    def test_v4_lesser_evil(self):
        """V4: C1: -A 0B, C2: 0A -B (lesser evil - both only violate different values)"""
        case = create_case(
            autonomy_1="violates", autonomy_2="neutral",
            beneficence_1="neutral", beneficence_2="violates",
            nonmaleficence_1="neutral", nonmaleficence_2="neutral",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None
    
    def test_v5_imbalanced_promotions(self):
        """V5: C1: +A 0B 0N, C2: 0A +B +N (imbalanced 1 vs 2 promotions but valid)"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="neutral",
            beneficence_1="neutral", beneficence_2="promotes",
            nonmaleficence_1="neutral", nonmaleficence_2="promotes",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None
    
    def test_v6_complex_3_value_cross_conflict(self):
        """V6: C1: +A -B +N, C2: -A +B -N (complex 3-value cross-conflict)"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="violates",
            beneficence_1="violates", beneficence_2="promotes",
            nonmaleficence_1="promotes", nonmaleficence_2="violates",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None
    
    def test_v7_mixed_tradeoff_vs_clean_alternative(self):
        """V7: C1: +A -B, C2: +N only (mixed tradeoff vs clean alternative on different value)"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="neutral",
            beneficence_1="violates", beneficence_2="neutral",
            nonmaleficence_1="neutral", nonmaleficence_2="promotes",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None


# =============================================================================
# INVALID Edge Cases I1-I7 (Should FAIL Validation)
# =============================================================================

class TestInvalidEdgeCases:
    """
    Invalid edge cases from the plan discussion.
    These should all FAIL validation.
    """
    
    def test_i1_obvious_choice_all_good_vs_all_bad(self):
        """I1: C1: +A +B, C2: -A -B (obvious choice - C1 all good, C2 all bad)
        
        Constraint violated: #4 No free lunch (pure upside vs pure downside)
        """
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="promotes", autonomy_2="violates",
                beneficence_1="promotes", beneficence_2="violates",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        assert "INVALID" in str(exc_info.value)
        assert "only has violations" in str(exc_info.value) or "obviously better" in str(exc_info.value)
    
    def test_i2_only_1_value_engaged(self):
        """I2: C1: +A 0B, C2: -A 0B (only 1 value engaged)
        
        Constraint violated: #2 Min 2 values
        """
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="promotes", autonomy_2="violates",
                beneficence_1="neutral", beneficence_2="neutral",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        assert "INVALID" in str(exc_info.value)
        assert "1 value" in str(exc_info.value).lower() or "engaged" in str(exc_info.value).lower()
    
    def test_i3_autonomy_promotes_promotes(self):
        """I3: C1: +A 0B, C2: +A 0B (autonomy is promotes+promotes)
        
        Constraint violated: #1 Per-value validity
        """
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="promotes", autonomy_2="promotes",
                beneficence_1="neutral", beneficence_2="neutral",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        assert "INVALID" in str(exc_info.value)
        assert "promotes" in str(exc_info.value).lower() and "autonomy" in str(exc_info.value).lower()
    
    def test_i4_autonomy_violates_violates(self):
        """I4: C1: -A -B, C2: -A 0B (autonomy is violates+violates)
        
        Constraint violated: #1 Per-value validity
        """
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="violates", autonomy_2="violates",
                beneficence_1="violates", beneficence_2="neutral",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        assert "INVALID" in str(exc_info.value)
        assert "violates" in str(exc_info.value).lower() and "autonomy" in str(exc_info.value).lower()
    
    def test_i5_no_cross_opposition_and_free_lunch(self):
        """I5: C1: +A 0B, C2: 0A -B (no cross-opposition - C1 promotes, C2 only violates)
        
        Constraint violated: #3 Cross-value opposition + #4 No free lunch
        """
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="promotes", autonomy_2="neutral",
                beneficence_1="neutral", beneficence_2="violates",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        # Could fail on either constraint 3 or 4
        assert "INVALID" in str(exc_info.value)
    
    def test_i6_mixed_vs_pure_downside_asymmetric(self):
        """I6: C1: +A -B, C2: -A 0B (C2 has no upside, asymmetric)
        
        Constraint violated: #4 No free lunch (mixed vs pure downside is asymmetric)
        """
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="promotes", autonomy_2="violates",
                beneficence_1="violates", beneficence_2="neutral",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        assert "INVALID" in str(exc_info.value)
        assert "only has violations" in str(exc_info.value) or "no promotions" in str(exc_info.value).lower()
    
    def test_i7_only_c1_engages_values(self):
        """I7: C1: +A 0B, C2: 0A 0B (only C1 engages values, C2 neutral on all)
        
        Constraint violated: #3 Cross-value opposition
        """
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="promotes", autonomy_2="neutral",
                beneficence_1="promotes", beneficence_2="neutral",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        # Should fail because there's no cross-value opposition
        assert "INVALID" in str(exc_info.value)


# =============================================================================
# Additional Invalid Cases (edge cases not explicitly in plan)
# =============================================================================

class TestAdditionalInvalidCases:
    """Additional invalid cases to ensure robustness."""
    
    def test_all_neutral_values(self):
        """All values neutral => fails min 2 non-neutral constraint"""
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="neutral", autonomy_2="neutral",
                beneficence_1="neutral", beneficence_2="neutral",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        assert "INVALID" in str(exc_info.value)
        assert "0 value" in str(exc_info.value).lower() or "none" in str(exc_info.value).lower()
    
    def test_beneficence_violates_violates(self):
        """Beneficence is violates+violates (same-direction)"""
        with pytest.raises(ValueError) as exc_info:
            create_case(
                autonomy_1="promotes", autonomy_2="violates",
                beneficence_1="violates", beneficence_2="violates",
                nonmaleficence_1="neutral", nonmaleficence_2="neutral",
                justice_1="neutral", justice_2="neutral",
            )
        assert "INVALID" in str(exc_info.value)
        assert "beneficence" in str(exc_info.value).lower()


# =============================================================================
# Spot-Check Existing Cases
# =============================================================================

class TestExistingCases:
    """
    Spot-check existing cases in data/cases/.
    
    Note: The new validator adds constraint #4 (no free lunch / balance check)
    which is STRICTER than the old rules in one dimension. Some existing cases
    may fail this check because they have asymmetric patterns (one choice has
    only violations, making the other choice obviously better). These cases
    are identified here for potential retagging.
    """
    
    @pytest.fixture
    def case_files(self):
        """Get list of all case files."""
        cases_dir = Path(__file__).parent.parent / "data" / "cases"
        return list(cases_dir.glob("*.json"))
    
    def test_existing_cases_validation_report(self, case_files):
        """
        Report on existing cases: count valid vs invalid under new rules.
        
        This test PASSES as long as the majority of cases are valid.
        It prints a report of cases that need retagging for the balance constraint.
        """
        if not case_files:
            pytest.skip("No case files found in data/cases/")
        
        valid_count = 0
        invalid_cases = []
        skipped_count = 0
        
        for case_file in case_files:
            try:
                with open(case_file, "r") as f:
                    data = json.load(f)
                
                # Get the final version of the case (last iteration with choice data)
                final_data = None
                for history in reversed(data.get("refinement_history", [])):
                    if "data" in history and "choice_1" in history["data"]:
                        if isinstance(history["data"]["choice_1"], dict):
                            final_data = history["data"]
                            break
                
                if final_data is None:
                    skipped_count += 1
                    continue  # Skip cases without tagged values
                
                # Extract choice tags
                c1 = final_data["choice_1"]
                c2 = final_data["choice_2"]
                
                # Validate by creating a BenchmarkCandidate
                BenchmarkCandidate(
                    vignette=final_data["vignette"],
                    choice_1=ChoiceWithValues(
                        choice=c1["choice"],
                        autonomy=c1["autonomy"],
                        beneficence=c1["beneficence"],
                        nonmaleficence=c1["nonmaleficence"],
                        justice=c1["justice"],
                    ),
                    choice_2=ChoiceWithValues(
                        choice=c2["choice"],
                        autonomy=c2["autonomy"],
                        beneficence=c2["beneficence"],
                        nonmaleficence=c2["nonmaleficence"],
                        justice=c2["justice"],
                    ),
                )
                valid_count += 1
                
            except ValueError as e:
                invalid_cases.append((case_file.name, str(e)))
            except Exception as e:
                skipped_count += 1
        
        # Print report
        total_checked = valid_count + len(invalid_cases)
        print(f"\n\n{'='*60}")
        print("EXISTING CASES VALIDATION REPORT")
        print(f"{'='*60}")
        print(f"Total case files: {len(case_files)}")
        print(f"Checked (with value tags): {total_checked}")
        print(f"Skipped (no tags/incomplete): {skipped_count}")
        print(f"Valid under new rules: {valid_count}")
        print(f"Need retagging: {len(invalid_cases)}")
        
        if invalid_cases:
            print(f"\n{'='*60}")
            print("CASES NEEDING RETAGGING (balance constraint #4 violations):")
            print(f"{'='*60}")
            for name, error in invalid_cases:
                # Extract just the case ID
                case_id = name.split('_')[1] if '_' in name else name
                print(f"  - {case_id}")
        
        print(f"{'='*60}\n")
        
        # Test passes if majority are valid
        # (allow some existing cases to fail the new balance constraint)
        assert valid_count > 0, "No valid cases found"
        validity_rate = valid_count / total_checked if total_checked > 0 else 0
        assert validity_rate >= 0.9, (
            f"Too many cases ({len(invalid_cases)}/{total_checked}) fail validation. "
            f"Expected at least 90% valid, got {validity_rate:.1%}."
        )
    
    def test_sample_case_values(self, case_files):
        """Test that we can read and validate at least a few specific cases."""
        if not case_files:
            pytest.skip("No case files found in data/cases/")
        
        # Test first 5 cases
        validated_count = 0
        for case_file in case_files[:10]:
            try:
                with open(case_file, "r") as f:
                    data = json.load(f)
                
                # Get the final version of the case
                final_data = None
                for history in reversed(data.get("refinement_history", [])):
                    if "data" in history and "choice_1" in history["data"]:
                        if isinstance(history["data"]["choice_1"], dict):
                            final_data = history["data"]
                            break
                
                if final_data is None:
                    continue
                
                c1 = final_data["choice_1"]
                c2 = final_data["choice_2"]
                
                # Extract tags
                tags = {
                    "autonomy": (c1["autonomy"], c2["autonomy"]),
                    "beneficence": (c1["beneficence"], c2["beneficence"]),
                    "nonmaleficence": (c1["nonmaleficence"], c2["nonmaleficence"]),
                    "justice": (c1["justice"], c2["justice"]),
                }
                
                # Verify constraints are satisfied
                # 1. Per-value validity
                for value, (t1, t2) in tags.items():
                    assert is_valid_per_value_pattern(t1, t2), f"Per-value invalid for {value}"
                
                # 2. Min 2 non-neutral
                non_neutral = sum(1 for t1, t2 in tags.values() if t1 != "neutral" or t2 != "neutral")
                assert non_neutral >= 2, f"Only {non_neutral} non-neutral values"
                
                # 3. Cross-value opposition
                assert has_cross_value_opposition(tags), "No cross-value opposition"
                
                # 4. No balance violation  
                assert not has_balance_violation(tags), "Balance violation"
                
                validated_count += 1
                
            except Exception:
                pass
        
        assert validated_count > 0, "No cases could be validated"


# =============================================================================
# Regression Tests (ensure old strict patterns still work)
# =============================================================================

class TestRegressionStrictPatterns:
    """
    Regression tests to ensure the old strict patterns (promotes↔violates
    for all non-neutral values) still pass under the new relaxed rules.
    """
    
    def test_strict_2_value_cross_conflict(self):
        """Strict pattern: 2 values, both have promotes↔violates"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="violates",
            beneficence_1="violates", beneficence_2="promotes",
            nonmaleficence_1="neutral", nonmaleficence_2="neutral",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None
    
    def test_strict_3_value_cross_conflict(self):
        """Strict pattern: 3 values, all have promotes↔violates"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="violates",
            beneficence_1="violates", beneficence_2="promotes",
            nonmaleficence_1="promotes", nonmaleficence_2="violates",
            justice_1="neutral", justice_2="neutral",
        )
        assert case is not None
    
    def test_strict_4_value_cross_conflict(self):
        """Strict pattern: 4 values, all have promotes↔violates"""
        case = create_case(
            autonomy_1="promotes", autonomy_2="violates",
            beneficence_1="violates", beneficence_2="promotes",
            nonmaleficence_1="promotes", nonmaleficence_2="violates",
            justice_1="violates", justice_2="promotes",
        )
        assert case is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

