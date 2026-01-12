"""Type definitions for statistical analysis of LLM decision data.

Provides result containers for bootstrap-based inference:
- BootstrapResult: Generic container for any bootstrapped metric
- ValueWeightsResult: Specialized container for logistic regression coefficients
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import NDArray


@dataclass
class BootstrapResult:
    """Container for bootstrap sample results with summary statistics.
    
    Holds an array of bootstrap samples and provides methods to compute
    point estimates and confidence intervals. When multiple metrics use
    shared bootstrap indices, their samples are directly comparable
    (i.e., samples[i] from different results use the same resampled data).
    
    Attributes:
        samples: 1D array of bootstrap sample values, shape (n_samples,)
    
    Example:
        >>> result = BootstrapResult(samples=np.array([0.5, 0.52, 0.48, 0.51]))
        >>> result.mean
        0.5025
        >>> result.ci(95)
        (0.48, 0.52)
    """
    
    samples: NDArray[np.floating]
    
    @property
    def mean(self) -> float:
        """Mean of bootstrap samples (point estimate)."""
        return float(np.mean(self.samples))
    
    @property
    def std(self) -> float:
        """Standard deviation of bootstrap samples (standard error estimate)."""
        return float(np.std(self.samples, ddof=1))
    
    @property
    def median(self) -> float:
        """Median of bootstrap samples."""
        return float(np.median(self.samples))
    
    def ci(self, confidence: float = 95) -> tuple[float, float]:
        """Compute percentile confidence interval.
        
        Uses the percentile method: the interval is defined by the
        (alpha/2) and (1 - alpha/2) percentiles of the bootstrap distribution.
        
        Args:
            confidence: Confidence level as a percentage (0-100). Default is 95.
        
        Returns:
            Tuple of (lower_bound, upper_bound) for the confidence interval.
        
        Example:
            >>> result.ci(95)  # 95% CI
            (0.42, 0.58)
            >>> result.ci(90)  # 90% CI
            (0.44, 0.56)
        """
        alpha = (100 - confidence) / 2
        lower = float(np.percentile(self.samples, alpha))
        upper = float(np.percentile(self.samples, 100 - alpha))
        return (lower, upper)
    
    def __repr__(self) -> str:
        ci_low, ci_high = self.ci(95)
        return f"BootstrapResult(mean={self.mean:.4f}, 95% CI=[{ci_low:.4f}, {ci_high:.4f}], n={len(self.samples)})"


@dataclass
class ValueWeightsResult:
    """Container for logistic regression coefficients estimating value weights.
    
    Holds β coefficients from regressing P(choice_1) on value alignment
    differences (Δ_value = align(C1, value) - align(C2, value)).
    
    The coefficients represent the log-odds impact of each value dimension
    on choice probability. Positive β means the model favors choices that
    promote that value; negative β means the model avoids violations.
    
    Attributes:
        coefficients: Dict mapping value name to β coefficient (point estimate)
        std_errors: Optional dict mapping value name to standard error from
            statsmodels (available for point estimates from regression)
        p_values: Optional dict mapping value name to p-value from statsmodels
            (available for point estimates from regression)
        bootstrap_samples: Optional dict mapping value name to array of
            bootstrap β samples, shape (n_samples,) each. Present when
            bootstrap indices were provided.
    
    Example:
        >>> result = ValueWeightsResult(
        ...     coefficients={"autonomy": 0.8, "beneficence": 1.2, ...},
        ...     std_errors={"autonomy": 0.1, "beneficence": 0.15, ...},
        ...     p_values={"autonomy": 0.001, "beneficence": 0.0001, ...}
        ... )
        >>> result.coefficients["autonomy"]
        0.8
        >>> result.get_bootstrap_result("autonomy")
        BootstrapResult(mean=0.79, 95% CI=[0.65, 0.92], n=1000)
    """
    
    coefficients: dict[str, float]
    std_errors: Optional[dict[str, float]] = None
    p_values: Optional[dict[str, float]] = None
    bootstrap_samples: Optional[dict[str, NDArray[np.floating]]] = None
    
    def get_bootstrap_result(self, value: str) -> Optional[BootstrapResult]:
        """Get BootstrapResult for a specific value's coefficient.
        
        Args:
            value: Name of the value (e.g., "autonomy", "beneficence")
        
        Returns:
            BootstrapResult for that value's β coefficient, or None if
            bootstrap_samples is not available.
        
        Raises:
            KeyError: If the value is not in the results.
        """
        if self.bootstrap_samples is None:
            return None
        
        if value not in self.bootstrap_samples:
            raise KeyError(f"Value '{value}' not found in bootstrap samples")
        
        return BootstrapResult(samples=self.bootstrap_samples[value])
    
    def ci(self, value: str, confidence: float = 95) -> Optional[tuple[float, float]]:
        """Get confidence interval for a specific value's coefficient.
        
        If bootstrap samples are available, uses percentile method.
        Otherwise, returns None (use std_errors for approximate CIs).
        
        Args:
            value: Name of the value
            confidence: Confidence level as percentage (0-100)
        
        Returns:
            Tuple of (lower, upper) bounds, or None if no bootstrap samples.
        """
        result = self.get_bootstrap_result(value)
        if result is None:
            return None
        return result.ci(confidence)
    
    @property
    def values(self) -> list[str]:
        """List of value names in the results."""
        return list(self.coefficients.keys())
    
    def __repr__(self) -> str:
        coef_strs = [f"{v}={c:.3f}" for v, c in self.coefficients.items()]
        bootstrapped = "bootstrapped" if self.bootstrap_samples else "point estimate"
        return f"ValueWeightsResult({', '.join(coef_strs)}) [{bootstrapped}]"
