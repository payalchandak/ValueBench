"""Value weight estimation via logistic regression.

Estimates how strongly an LLM weighs each value dimension when making
ethical tradeoffs, using logistic regression on choice probabilities.
"""

from typing import Union
import warnings

import numpy as np
from numpy.typing import NDArray
import statsmodels.api as sm

from src.analysis.metrics import _get_alignment
from src.analysis.result_types import ValueWeightsResult
from src.llm_decisions.models import DecisionRecord
from src.response_models.case import VALUE_NAMES


def _build_regression_data(
    decisions: list[DecisionRecord],
    model: str,
    case_indices: NDArray[np.intp] | None = None,
) -> tuple[NDArray[np.floating], NDArray[np.floating], NDArray[np.intp]]:
    """Build feature matrix and target vector for logistic regression.
    
    Args:
        decisions: List of DecisionRecord objects
        model: Model identifier
        case_indices: Optional array of case indices to include (for bootstrap).
            If None, uses all cases with valid data.
    
    Returns:
        Tuple of (X, y, n_trials) where:
        - X: Feature matrix of shape (n_cases, n_values) with Δ_value columns
        - y: Target vector of shape (n_cases,) with P(choice_1) values
        - n_trials: Array of shape (n_cases,) with total_valid_runs per case
    
    Raises:
        ValueError: If no valid cases found for the model
    """
    # Collect data for all cases (or specified subset)
    X_rows: list[list[float]] = []
    y_values: list[float] = []
    n_trials_values: list[int] = []
    
    # Determine which indices to process and their bootstrap weights
    if case_indices is not None:
        # For bootstrap: count how many times each case is selected
        unique_indices, counts = np.unique(case_indices, return_counts=True)
        index_weights = dict(zip(unique_indices, counts))
    else:
        index_weights = None
    
    for idx, record in enumerate(decisions):
        # Skip if not in requested indices (for bootstrap)
        if index_weights is not None and idx not in index_weights:
            continue
        
        # Skip if model didn't evaluate this case
        if model not in record.models:
            continue
        
        model_data = record.models[model]
        summary = model_data.summary
        
        # Skip if no valid (non-refusal) runs
        if summary.total_valid_runs == 0:
            continue
        
        # Compute Δ_value = align(C1, value) - align(C2, value) for each value
        delta_row = []
        for value in VALUE_NAMES:
            align_c1 = _get_alignment(record.case.choice_1, value)
            align_c2 = _get_alignment(record.case.choice_2, value)
            delta_row.append(float(align_c1 - align_c2))
        
        # P(choice_1) and number of trials
        p_c1 = summary.choice_1_count / summary.total_valid_runs
        n_trials = summary.total_valid_runs
        
        # For bootstrap: multiply weight by bootstrap count instead of duplicating rows
        if index_weights is not None:
            bootstrap_count = index_weights[idx]
            X_rows.append(delta_row)
            y_values.append(p_c1)
            n_trials_values.append(n_trials * bootstrap_count)
        else:
            X_rows.append(delta_row)
            y_values.append(p_c1)
            n_trials_values.append(n_trials)
    
    if len(X_rows) == 0:
        raise ValueError(f"Model '{model}' has no valid runs on any case")
    
    X = np.array(X_rows, dtype=np.float64)
    y = np.array(y_values, dtype=np.float64)
    n_trials = np.array(n_trials_values, dtype=np.intp)
    
    return X, y, n_trials


def _fit_logistic_regression(
    X: NDArray[np.floating],
    y: NDArray[np.floating],
    n_trials: NDArray[np.intp],
) -> tuple[dict[str, float], dict[str, float] | None, dict[str, float] | None]:
    """Fit logistic regression and return coefficients.
    
    Uses GLM with Binomial family and logit link, no intercept.
    
    Args:
        X: Feature matrix of shape (n_cases, n_values)
        y: Target vector of shape (n_cases,) with proportions
        n_trials: Array of shape (n_cases,) with trial counts per case
    
    Returns:
        Tuple of (coefficients dict, std_errors dict or None, p_values dict or None)
    """
    # Handle edge cases
    # If y is all 0s or all 1s, logistic regression will fail
    if np.all(y == 0) or np.all(y == 1):
        # Return zeros with None for std errors and p-values
        return {v: 0.0 for v in VALUE_NAMES}, None, None
    
    # Check if X has any variation
    if np.all(X == 0):
        return {v: 0.0 for v in VALUE_NAMES}, None, None
    
    try:
        # Suppress convergence warnings during bootstrap
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            warnings.filterwarnings("ignore", message=".*converge.*")
            
            # GLM with Binomial family expects (successes, failures) or proportion with weights
            # We use proportion as y and n_trials as frequency weights
            glm_model = sm.GLM(
                y,
                X,
                family=sm.families.Binomial(link=sm.families.links.Logit()),
                freq_weights=n_trials,
            )
            
            result = glm_model.fit(disp=False, cov_type='HC3')
            
            coefficients = {v: float(result.params[i]) for i, v in enumerate(VALUE_NAMES)}
            std_errors = {v: float(result.bse[i]) for i, v in enumerate(VALUE_NAMES)}
            p_values = {v: float(result.pvalues[i]) for i, v in enumerate(VALUE_NAMES)}
            
            return coefficients, std_errors, p_values
            
    except Exception:
        # If fitting fails (e.g., perfect separation), return zeros
        return {v: 0.0 for v in VALUE_NAMES}, None, None


def value_weights(
    decisions: list[DecisionRecord],
    model: str,
    indices: NDArray[np.intp] | None = None,
) -> ValueWeightsResult:
    """Estimate value weights for a model via logistic regression.
    
    Fits a logistic regression predicting P(choice_1) from value alignment
    differences: logit(P(c1)) = Σ β_v × Δ_v, where Δ_v = align(C1, v) - align(C2, v).
    
    Positive β_v indicates the model prefers choices that promote value v
    (or avoid violating it). The magnitude indicates the strength of preference.
    
    Uses GLM with Binomial family and no intercept, weighted by the number
    of runs per case to account for varying precision in P(choice_1) estimates.
    
    Args:
        decisions: List of DecisionRecord objects from load_llm_decisions()
        model: Model identifier (e.g., "openai/gpt-5.2")
        indices: Optional bootstrap indices from bootstrap_indices(). If None,
            returns point estimate with standard errors from statsmodels.
            If provided, fits model for each bootstrap sample.
    
    Returns:
        ValueWeightsResult containing:
        - coefficients: Dict of β values for each value
        - std_errors: Dict of standard errors (only for point estimate)
        - bootstrap_samples: Dict of β sample arrays (only if indices provided)
    
    Raises:
        ValueError: If model has no valid runs on any case
    
    Example:
        >>> decisions = load_llm_decisions()
        >>> # Point estimate with standard errors
        >>> result = value_weights(decisions, "openai/gpt-5.2")
        >>> print(result.coefficients)
        {'autonomy': 0.8, 'beneficence': 1.2, 'nonmaleficence': 0.9, 'justice': 0.5}
        >>> print(result.std_errors)
        {'autonomy': 0.1, 'beneficence': 0.15, ...}
        
        >>> # Bootstrapped for confidence intervals
        >>> indices = bootstrap_indices(n_cases=len(decisions), n_samples=1000, seed=42)
        >>> result = value_weights(decisions, "openai/gpt-5.2", indices=indices)
        >>> result.ci("autonomy", 95)
        (0.65, 0.95)
    """
    if indices is None:
        # Point estimate: fit on all data
        X, y, n_trials = _build_regression_data(decisions, model)
        coefficients, std_errors, p_values = _fit_logistic_regression(X, y, n_trials)
        
        return ValueWeightsResult(
            coefficients=coefficients,
            std_errors=std_errors,
            p_values=p_values,
            bootstrap_samples=None,
        )
    
    # Bootstrapped: fit on each resampled dataset
    n_samples = indices.shape[0]
    bootstrap_samples: dict[str, list[float]] = {v: [] for v in VALUE_NAMES}
    
    for i in range(n_samples):
        try:
            X, y, n_trials = _build_regression_data(decisions, model, indices[i])
            coefficients, _, _ = _fit_logistic_regression(X, y, n_trials)
            
            for v in VALUE_NAMES:
                bootstrap_samples[v].append(coefficients[v])
        except ValueError:
            # Skip bootstrap samples with no valid data
            continue
    
    # Convert to numpy arrays
    bootstrap_arrays = {v: np.array(samples) for v, samples in bootstrap_samples.items()}
    
    # Point estimate is mean of bootstrap samples
    coefficients = {v: float(np.mean(bootstrap_arrays[v])) for v in VALUE_NAMES}
    
    return ValueWeightsResult(
        coefficients=coefficients,
        std_errors=None,
        p_values=None,
        bootstrap_samples=bootstrap_arrays,
    )
