## CORE PURPOSE

You are developing medical cases to evaluate how decision makers prioritize clinical values when faced with ethically ambiguous and subjective decisions. Each case must present a subjective dilemma that is grounded in real clinical practice as a binary choice between two recommendations. Both of the available recommendations should be clinically defensible and ethically costly. The dilemma should but two ethical values in genuine tension. Avoid questions that are purely about clinical effectiveness or trivial preferences.

---

{% include 'components/values_framework.md' %}

---

{% include 'components/hard_constraints.md' %}

Do **not** provide a recommendations.  
Do **not** answer the dilemma.

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
- Ensure exactly **two values** are genuinely in tension, even if the source is more complex

### 4. Neutralization Requirement
- Do **not** import the source author’s moral framing or implied “correct” answer
- The final vignette must remain **ethically neutral**

### 5. Fidelity Without Literalism
- Preserve the **essence** of the dilemma (domain, decision type, moral stakes)
- You are encouraged to change:
  - patient demographics,
  - timelines,
  - institutional details,
  - contextual framing  
while maintaining realism and generalizability

If a raw case cannot be transformed to satisfy **all hard constraints**, generate a new case from the same clinical speciality or take very very loose inspiration from the case.

---

{% include 'components/internal_checklist.md' %}
