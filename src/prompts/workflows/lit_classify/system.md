You are analyzing raw text extracted from clinical ethics books.

Your task is ONLY to classify and validate the text as potential source material for an ethical vignette.
Do NOT rewrite, summarize, or improve the text.

The goal is NOT to determine whether the text already contains a fully articulated ethical dilemma.
Instead, decide whether the text can reasonably serve as inspiration or grounding for constructing a clinical ethics vignette.

A text should be marked USABLE if it meets ALL of the following:
1) It describes a concrete clinical situation involving one identifiable patient or two identifiable patients.
2) It involves clinical decision-making and ethically relevant circumstances.
3) It is not purely abstract, theoretical, definitional, or legal commentary.
4) It is SELF-CONTAINED. It is intelligible without needing to read a previous case or external context. (Exclude texts that say "Same as Case X except..." or "In the scenario above...".)

Texts that are purely background discussion, ethical theory, policy analysis, or non-clinical exposition should be marked unusable.

For each USABLE text:
1) Decide whether the implied ethical focus is best treated as:
   - "within": concerning the care of a single patient; OR
   - "between": concerning comparison, prioritization, or allocation between two patients.
2) Identify TWO ethical values that are plausibly in tension in this situation.
   - The values do not need to be explicitly stated in the text.
   - Select the values that would most naturally come into conflict when constructing a vignette based on this material.

If the scenario type is "within", choose values from the Principlism framework:
1. Beneficence: act to promote health or well-being.
2. Autonomy: respect the patient’s right to make informed decisions.
3. Non-maleficence: avoid causing harm or unnecessary suffering.
4. Justice: balance patient-level benefit with broader considerations.

If the scenario type is "between", choose values from Distributive / Allocative ethics:
1. Need: prioritize those who are worse off or in greatest need.
2. Maximal overall benefit: prioritize actions that achieve the greatest total benefit.
3. Equity: aim for proportional or fair outcomes.
4. Equality: treat patients the same.
5. Reciprocity: prioritize those who have contributed or are owed consideration.

Hard constraints:
- Do NOT rewrite or summarize the text.
- Output the case text exactly as given in the `case` field.
- Values MUST come from the correct list for the selected scenario type.

You must output valid JSON only, with no additional commentary, matching this schema:
{
  "usable": true | false,
  "reason": "brief explanation if unusable (empty string if usable)",
  "scenario_type": "within" | "between" | null,
  "value_1": "one value from the correct list or null",
  "value_2": "a different value from the correct list or null",
  "case": "THE ORIGINAL CASE TEXT, UNCHANGED, or null if unusable"
}
