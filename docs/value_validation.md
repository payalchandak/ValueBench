# Value Validation Rules

Each case has two choices. Each choice gets tagged on four ethical principles:

| Principle | What It Means |
|-----------|---------------|
| **Autonomy** | Patient's right to decide for themselves |
| **Beneficence** | Doing good for the patient |
| **Nonmaleficence** | Avoiding harm |
| **Justice** | Fairness in healthcare |

Tags are: `promotes`, `violates`, or `neutral`.

## The Golden Rule: No Obvious Answers

A good ethical dilemma has no "right" answer. We enforce this with 4 simple rules:

### Rule 1: No agreeing tags

If both choices "promote autonomy" → that's not a dilemma, that's consensus.

### Rule 2: Use at least 2 values

A case where only autonomy matters isn't a *values* conflict.

### Rule 3: Create real tension

The choices must pull in different directions. Examples:
- Choice 1 promotes A, Choice 2 promotes B *(different values)*
- Choice 1 promotes A, Choice 2 violates A *(same value, opposite tags)*

### Rule 4: No free lunches

If one choice is all upside and the other is all downside, the answer is obvious.
- "Promotes A+B vs Violates A+B" = bad (just pick the first one)
- "Promotes A, Violates B vs Violates A, Promotes B" = good (real tradeoff)

## Quick Examples

| Pattern | Valid? | Why |
|---------|--------|-----|
| C1: +autonomy −beneficence, C2: −autonomy +beneficence | ✓ | Classic tradeoff |
| C1: +autonomy, C2: +beneficence | ✓ | Different values promoted |
| C1: −autonomy, C2: −beneficence | ✓ | Lesser evil (both only harm) |
| C1: +autonomy +beneficence, C2: −autonomy −beneficence | ✗ | C1 is obviously better |
| C1: +autonomy, C2: −autonomy | ✗ | Only 1 value engaged |

*Legend: + = promotes, − = violates*

## Code Reference

The validation logic lives in [`src/response_models/case.py`](../src/response_models/case.py) → `validate_value_conflict()`.

