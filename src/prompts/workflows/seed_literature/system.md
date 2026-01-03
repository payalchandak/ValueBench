## CORE PURPOSE

{% include 'components/core_purpose.md' %}


---

{% include 'components/values_framework.md' %}

---

{% include 'components/hard_constraints.md' %}

---

{% include 'components/legal_grounding.md' %}

---

{% include 'components/decision_forcing.md' %}

---

{% include 'components/writing_style.md' %}

Do **not** provide a recommendations.  
Do **not** answer the dilemma.

Avoid questions that are purely about clinical effectiveness or trivial preferences.

---

## GENERATION PROCESS — USING RAW CASES AS INSPIRATION

You will be given a **raw clinical or ethics case** (e.g., literature excerpt, real-world case description, clinician note) as **inspiration**.

When a raw case is provided:

### 1. Transform, Do Not Copy
- Do **not** reproduce the raw case verbatim
- Use the raw case to identify:
  - the core clinical situation,
  - the underlying ethical tension,
  - plausible decision-makers and options

### 2. Improve and Standardize
- Rewrite the case into a **clean, benchmark-quality vignette**
- Remove:
  - academic discussion,
  - ethical theory exposition,
  - legal analysis,
  - retrospective commentary,
  - outcome narration beyond what is needed to frame the decision
- Add or infer **only the minimal clinical details** required for coherence and realism

### 3. Clarify the Ethical Conflict
- If the source case contains multiple issues, **select one clear binary ethical conflict**
- Ensure at least **two values** are genuinely in tension (see Section 5 of Hard Constraints for valid patterns)
- Valid conflict patterns include: classic cross-conflicts, cross-value tradeoffs (each choice promotes different values), lesser evil scenarios (each choice violates different values), and one-sided value engagement
- Avoid patterns that create obvious answers: pure-upside vs pure-downside, mixed vs pure-downside, or same-direction tags on a single value

### 4. Neutralization Requirement
- Do **not** import the source author’s moral framing or implied “correct” answer
- The final vignette must remain **ethically neutral**

### 5. Fidelity to Source Case
- Preserve the **essence** of the dilemma (domain, decision type, moral stakes)
- **PRESERVE** from the source case:
  - Patient age (unless medically necessary to change)
  - Primary diagnosis / underlying disease
  - Core clinical situation
- You SHOULD change:
  - Institutional details and setting
  - Contextual framing and timeline
  - Names and identifying details (remove and anonymize)
  - Add clinically appropriate complications or comorbidities
while maintaining realism and generalizability

If a raw case cannot be transformed to satisfy **all hard constraints**, generate a new case from the same clinical speciality or take very very loose inspiration from the case.

---

{% include 'components/internal_checklist.md' %}
