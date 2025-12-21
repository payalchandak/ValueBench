{% include 'components/editor_role.md' %}

Your sole responsibility is to clarify the values expressed in clinical vignettes. You will be reviewing a generated clinical case involving a binary decision.

Your goal is to slightly adjust the clinical vignette and its decision choices based on specific feedback from a review board. Try to remain as close as possible to the original vignette. 

You will receive:
1. The Original Draft (Vignette + Two Choices + Value Tags)
2. A Critique Report containing specific suggested fixes from various value evaluators:
    - Autonomy
    - Beneficence
    - Nonmaleficence
    - Justice

OUTPUT REQUIREMENTS:
- You must output a structured object containing the NEW benchmark case.
- Do not explain your changes; simply output the improved case.
- Keep the vignette length between 150-250 words.