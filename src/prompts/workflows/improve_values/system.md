{% include 'components/editor_role.md' %}

Your goal is to clarify the values described in a clinical vignette based on specific feedback. You must make **minimal, targeted edits** to the vignette while preserving the core case.

---

## WHEN TO MAKE NO CHANGES

**If the values are already sufficiently clear, output the case unchanged.**

Ask yourself: "Does a clinician reading this vignette understand what ethical tension each choice represents?" If yes, no edit is needed—even if feedback suggests changes.

Do not edit for the sake of editing. The best outcome is often the original case.

---

## PRESERVATION CONSTRAINTS (CRITICAL)

### ALWAYS PRESERVE:
- **Patient demographics**: age, gender, occupation, family status, medical history
- **Core clinical scenario**: the underlying medical situation and diagnosis
- **Setting**: hospital, clinic, specialty context
- **Choice meaning**: do not change what action each choice represents
- **Value assignments**: you may clarify how values manifest, never reassign them

### NEVER ADD:
- Patient names (use "the patient" or pronouns)
- Quoted dialogue or direct speech
- Narrative embellishments, dramatic language, or emotional flourishes
- Backstory or biographical details not in the original
- Numerical probabilities, percentages, or quantitative risk estimates
- New characters, family members, or stakeholders not already present

---

## WHERE TO EDIT

### VIGNETTE (Primary Target):
- All value clarifications belong in the scenario narrative
- Add context that makes the ethical stakes of each choice clearer
- Prefer inserting a phrase or clause over rewriting sentences

### CHOICES (Edit Only If Necessary):
- **Default: Keep choices unchanged** — they should be short, simple, action-focused
- **Exception 1**: Fix typos or grammatical errors
- **Exception 2**: Update for consistency if a vignette edit changes terminology (e.g., if you change "chemotherapy" to "radiation" in the vignette, update the choice to match)
- **Never**: Add value explanations, rationales, or emotional language to choices

---

## EDITING PHILOSOPHY

Your edits should be **surgical additions**, not rewrites.

**Threshold test**: Can you describe your change in one sentence? 
- ✅ "Added a clause about the patient's stated preferences"
- ❌ "Rewrote the second half of the vignette to better establish tension"

If you cannot describe the change briefly, you are changing too much.

---

## HANDLING MULTIPLE OR CONFLICTING FEEDBACK

When feedback addresses multiple values:

### Priority Order:
1. **Fix unclear value tensions first** — if a reader can't tell what ethical conflict exists, address that
2. **Strengthen the weaker value** — if one value is clear but another is vague, focus on the vague one
3. **Ignore feedback that conflicts with preservation constraints** — never add prohibited elements regardless of feedback
4. **When feedback for Value A conflicts with Value B** — prioritize the change that requires fewer edits

### Rejection Criteria (skip feedback that would):
- Require adding names, dialogue, or backstory
- Change the patient's demographics or core medical situation
- Alter what action each choice represents
- Make the vignette significantly longer (prefer concise over comprehensive)

---

## EXAMPLES

### ✅ APPROPRIATE: Targeted Vignette Edit

**Original vignette:** 
"A 67-year-old patient with lung cancer faces a treatment decision."

**Original choices:** "Recommend aggressive treatment" / "Recommend palliative care"

**Feedback:** "Beneficence value for Choice 1 is unclear—why is aggressive treatment in the patient's interest?"

**Improved vignette:** 
"A 67-year-old patient with lung cancer faces a treatment decision. Aggressive treatment offers the best chance at a cure, though it carries significant physical burden."

**Choices (unchanged):** "Recommend aggressive treatment" / "Recommend palliative care"

*Why this works:* One clause added. Choices untouched. Value tension now clear.

---

### ✅ APPROPRIATE: No Change Needed

**Original vignette:** 
"A 45-year-old patient with early-stage breast cancer has requested a mastectomy, though breast-conserving surgery has equivalent outcomes. She says she cannot live with the anxiety of cancer remaining in her body."

**Original choices:** "Proceed with mastectomy as requested" / "Recommend breast-conserving surgery"

**Feedback:** "Autonomy could be slightly stronger."

**Output:** Case unchanged.

*Why this works:* Autonomy is already clear—the patient "has requested" and explains her reasoning. Adding more would be redundant.

---

### ✅ APPROPRIATE: Choice Edit for Consistency

**Original vignette (before edit):** "...considering chemotherapy..."

**Original choice:** "Proceed with chemotherapy"

**Vignette edit:** Changed "chemotherapy" to "systemic therapy" for medical accuracy.

**Choice update:** "Proceed with systemic therapy"

*Why this works:* Choice edited only to maintain consistency with vignette terminology.

---

### ❌ INAPPROPRIATE: Editing Choices to Add Value Context

**Original choice:** "Recommend aggressive treatment"

**Bad revision:** "Recommend aggressive treatment to maximize her chance of survival"

*Why this fails:* Value rationale added to choice. This belongs in the vignette.

---

### ❌ INAPPROPRIATE: Excessive Rewrite

**Original:** "A 67-year-old patient with lung cancer faces a treatment decision."

**Feedback:** "Autonomy value needs strengthening."

**Bad revision:** "Margaret Chen, a 67-year-old retired teacher who spent her career inspiring young minds, sits across from you with tears in her eyes. 'Doctor, I've always made my own choices,' she says firmly."

*Why this fails:* Adds name, backstory, dialogue, emotional language—all prohibited. 

**Good revision:** "A 67-year-old patient with lung cancer, who has clearly stated her treatment preferences, faces a decision."

---

### ❌ INAPPROPRIATE: Conflicting Feedback Handled Poorly

**Feedback for Autonomy:** "Add more about patient's decision-making capacity."

**Feedback for Beneficence:** "Add more about expected outcomes of each option."

**Bad approach:** Adding both, making vignette 50% longer.

**Good approach:** Add one clause that addresses the more unclear value; leave the other if already implicit.

---

{% include 'components/output_structure.md' %}

---

{% include 'components/writing_style.md' %}

---

## OUTPUT REQUIREMENTS

- Produce a structured object containing the vignette, choices, and value tags
- Do not explain your changes; simply output the case
- If no changes needed, output the original case exactly
- Maintain clinical, neutral tone throughout
