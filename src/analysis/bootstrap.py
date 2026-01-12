"""Bootstrap index generation for statistical analysis.

Provides functionality to generate shared bootstrap indices that ensure
all metrics computed across different models are directly comparable.
When the same indices are used, bootstrap sample i from model A and
bootstrap sample i from model B use the exact same resampled cases.
"""

import numpy as np
from numpy.typing import NDArray


def bootstrap_indices(
    n_cases: int,
    n_samples: int = 1000,
    seed: int | None = None,
) -> NDArray[np.intp]:
    """Generate bootstrap resampling indices.
    
    Creates a matrix of indices for bootstrap resampling. Each row represents
    one bootstrap sample, containing n_cases indices drawn with replacement
    from [0, n_cases). Using the same indices across different analyses
    ensures comparability.
    
    Args:
        n_cases: Number of cases in the original dataset.
        n_samples: Number of bootstrap samples to generate. Default is 1000.
        seed: Random seed for reproducibility. If None, results are not reproducible.
    
    Returns:
        Array of shape (n_samples, n_cases) containing integer indices.
        indices[i, j] is the j-th case index for bootstrap sample i.
    
    Example:
        >>> indices = bootstrap_indices(n_cases=100, n_samples=1000, seed=42)
        >>> indices.shape
        (1000, 100)
        >>> # Each row contains 100 indices in [0, 100), drawn with replacement
        >>> np.all((indices >= 0) & (indices < 100))
        True
        
        # Use shared indices to compare models:
        >>> result_a = value_preference(decisions, model="model_a", value="autonomy", indices=indices)
        >>> result_b = value_preference(decisions, model="model_b", value="autonomy", indices=indices)
        >>> # result_a.samples[i] and result_b.samples[i] used same resampled cases
        >>> diff = result_a.samples - result_b.samples
        >>> ci_diff = (np.percentile(diff, 2.5), np.percentile(diff, 97.5))
    
    Raises:
        ValueError: If n_cases <= 0 or n_samples <= 0.
    """
    if n_cases <= 0:
        raise ValueError(f"n_cases must be positive, got {n_cases}")
    if n_samples <= 0:
        raise ValueError(f"n_samples must be positive, got {n_samples}")
    
    rng = np.random.default_rng(seed)
    
    # Generate indices with replacement: each bootstrap sample draws n_cases
    # indices uniformly from [0, n_cases)
    indices = rng.integers(low=0, high=n_cases, size=(n_samples, n_cases))
    
    return indices
