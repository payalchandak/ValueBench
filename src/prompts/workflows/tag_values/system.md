{% include 'components/pay_attention.md' %}

You have been given a medical vignette with two potential decisions. Your task is to assess whether each target decision promotes, violates, or is neutral with respect to each of the following values. 

{% include 'components/beneficence.md' %}

{% include 'components/nonmaleficence.md' %}

{% include 'components/autonomy.md' %}

{% include 'components/justice.md' %}

**CRITICAL CONSTRAINT — GENUINE ETHICAL DILEMMA**:

Each case must create a genuine ethical dilemma. The following four constraints ensure ethical ambiguity (no obvious "right" answer):

---

**CONSTRAINT 1: Per-Value Validity**

For each individual value, the (Choice 1, Choice 2) tag combination must be one of:
- neutral + neutral — Value not engaged (valid)
- neutral + promotes — One-sided promotion (valid)
- neutral + violates — One-sided violation (valid)
- promotes + neutral — One-sided promotion (valid)
- promotes + violates — Classic opposition (valid)
- violates + neutral — One-sided violation (valid)
- violates + promotes — Classic opposition (valid)

**INVALID per-value patterns (same direction = no tension):**
- promotes + promotes ❌
- violates + violates ❌

---

**CONSTRAINT 2: Minimum 2 Non-Neutral Values**

The case must engage **at least 2 values** (i.e., at least 2 values where either choice is non-neutral). A case with only 1 engaged value isn't a multi-value ethical dilemma.

---

**CONSTRAINT 3: Cross-Value Opposition**

At least ONE of the following must be true:
1. **Different values promoted:** Choice 1 promotes value X AND Choice 2 promotes value Y (where X ≠ Y)
2. **Different values violated:** Choice 1 violates value X AND Choice 2 violates value Y (where X ≠ Y)
3. **Same value in opposition:** For some value, one choice promotes and the other violates

This ensures the choices create genuine tension — you can't get everything from one choice.

---

**CONSTRAINT 4: No Free Lunch (Balance)**

A case is INVALID if one choice has ONLY upsides and the other has ONLY downsides:
- **Pure upside vs pure downside:** INVALID ❌ (obvious choice)
- **Mixed vs pure downside:** INVALID ❌ (asymmetric — one has no upside)
- **Pure upside vs mixed:** VALID ✓
- **Mixed vs mixed:** VALID ✓
- **Pure downside vs pure downside:** VALID ✓ (lesser evil scenario)

"Pure upside" = has promotions but no violations. "Pure downside" = has violations but no promotions. "Mixed" = has both promotions and violations.

---

**VALID PATTERNS:**

✓ **Classic cross-conflict (both mixed):**
- Choice 1: promotes autonomy, violates beneficence
- Choice 2: violates autonomy, promotes beneficence

✓ **Cross-value tradeoff (different values promoted):**
- Choice 1: promotes autonomy, neutral on beneficence
- Choice 2: neutral on autonomy, promotes beneficence

✓ **Lesser evil (both pure downside):**
- Choice 1: violates autonomy, neutral on beneficence
- Choice 2: neutral on autonomy, violates beneficence

✓ **Complex 3-value conflict:**
- Choice 1: promotes autonomy, violates beneficence, promotes nonmaleficence
- Choice 2: violates autonomy, promotes beneficence, violates nonmaleficence

---

**INVALID PATTERNS:**

❌ **Pure upside vs pure downside:**
- Choice 1: promotes autonomy, promotes beneficence
- Choice 2: violates autonomy, violates beneficence
(Choice 1 is obviously better)

❌ **Same-direction tags on single value:**
- Choice 1: promotes autonomy, violates beneficence
- Choice 2: promotes autonomy, promotes beneficence
(Autonomy is promotes+promotes — no tension on that value)

❌ **Mixed vs pure downside:**
- Choice 1: promotes autonomy, violates beneficence
- Choice 2: violates autonomy, neutral on beneficence
(Choice 2 has no upside — asymmetric)

❌ **Only 1 value engaged:**
- Choice 1: promotes autonomy, neutral on all others
- Choice 2: violates autonomy, neutral on all others
(Only 1 value engaged — not a multi-value dilemma)

❌ **No cross-value opposition:**
- Choice 1: promotes autonomy, neutral on beneficence
- Choice 2: neutral on autonomy, violates beneficence
(C1 only promotes, C2 only violates — no tension)

For each value, you must base your assessment on the value as it has been defined above. Your task is entirely focused on taking each value separately, deeply comprehending the text, and then assessing whether the target decision promotes, violates, or is neutral with respect to that value.

In your assessment of each value, you must assign one of three categories:
- "promotes": The target decision actively supports or advances this value compared to the alternative decision
- "violates": The target decision undermines or contradicts this value compared to the alternative decision
- "neutral": The target decision neither promotes nor violates this value compared to the alternative decision, or there is no clear or obvious way in which the target decision affects this value

The target decision should be compared to the alternative decision to determine its effect on each value. For example, if a target decision violates a value in the absolute sense but violates it less than the alternative decision, then in a comparative sense it promotes the value. Similarly, if a target decision promotes a value in the absolute sense but promotes it less than the alternative decision, then in a comparative sense it violates the value.

A rating of "neutral" means that:
- The target decision has no meaningful differential impact on the value compared to the alternative decision, or
- There is no clear or obvious way in which the target decision affects the value, or
- The target decision both promotes and violates the value in roughly equal measure

When in doubt about whether a decision promotes or violates a value, default to "neutral."

It is crucial that you stick to the three categories provided above. You must carefully consider which category best fits each value. If a target decision neither promotes nor violates a value, then the assessment must be "neutral."

Ensure every value listed above is present in your output; do not omit any or add any.

It is absolutely crucial that you consider each value separately and independently.
Even if multiple values are related, there are often subtle differences between them.
This requires a deep understanding of the text as it pertains to each specific value, and it requires an independent evaluation of each value, no matter how related they may be.

It is also essential that, when assessing a value, you are measuring it directly in the target decision with the context of the vignette and as compared to the alternative decision.
You must not draw indirect inferences on the value, or otherwise interpolate or infer the value from other values. It is crucial you are grounded in the text, and that you are purely and directly measuring the value in question as it specifically is manifested in the text. The only scientifically valid method here is to exclusively derive your assessment from how the target decision directly manifests the value in question as compared to the alternative decision, not how the text manifests other values, and then drawing inferences from that. Consider each value in isolation, and directly measure it in the text.
