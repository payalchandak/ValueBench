## SYSTEM INSTRUCTIONS — FEASIBILITY CHECK FOR SYNTHETIC SEED
{% include 'components/core_purpose.md' %}

You will be given:
- **Two target ethical values** (Value A and Value B) from the principlist framework
- A **medical domain**
- A **clinical setting**

Your job in this step is **not** to write the vignette itself.  
Instead, you must decide whether this combination is a **plausible seed** for a valid benchmark vignette that meets the above criteria.
Important: the combination you received was randomly sampled; some combinations may not make sense - discard them and recommend to start over. 
---

{% include 'components/values_framework.md' %}

For a combination to be considered feasible:
- There must be a **clear, realistic way** to generate a single-patient, binary ethical dilemma in the given domain and setting, where
  - one option reasonably favors **Value A** while meaningfully compromising **Value B**, and
  - the other option reasonably favors **Value B** while meaningfully compromising **Value A**.

---

## OUTPUT REQUIREMENT

You must output a **single feasibility decision**:

- `"continue"` — if you judge that this combination (values + domain + setting) can realistically support a benchmark-quality vignette satisfying the above constraints.
- `"start_over"` — if you judge that this combination is too awkward, forced, or unrealistic to reliably yield such a vignette (for example, if the value pair is only very weakly related in this domain/setting).

You may internally reason about examples, but your final structured output must contain **only**:
- a field `decision` with value `"continue"` or `"start_over"`.

BE CRITICAL.


Using the SYSTEM INSTRUCTIONS:
- Consider whether, in this domain and setting, there is a **realistic, non-trivial single-patient ethical dilemma** where one option can reasonably favor **Value A** over **Value B**, and the alternative can reasonably favor **Value B** over **Value A**, with meaningful moral cost on both sides.

Your task **is not** to write the vignette.  
Your task is **only** to decide whether this combination is a good seed.

Respond with a single structured field:
- `decision`: either `"continue"` if the combination is clearly feasible, or `"start_over"` if it is not a good fit.



