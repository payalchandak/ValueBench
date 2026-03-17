"""
Dry-run / draft mode for the generation pipeline.

Runs the full pipeline (seed → refine → tag → validate) on custom seed text,
printing every intermediate result without writing any files.

Usage:
    1. Paste your seed text into SEED_TEXT below
    2. Optionally set VALUE_1 and VALUE_2 (leave as None to let the LLM infer them)
    3. Run: python -m src.draft_run
"""

import os
import sys
import logging

from dotenv import load_dotenv
from all_the_llms import LLM
from pydantic import ValidationError

os.environ["LITELLM_LOG"] = "ERROR"
import litellm
litellm.suppress_debug_info = True
litellm.set_verbose = False
logging.getLogger("all_the_llms").setLevel(logging.ERROR)
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)

from src.prompt_manager import PromptManager
from src.response_models.case import DraftCase, BenchmarkCandidate
from src.response_models.rubric import (
    ClinicalRubric,
    EthicalRubric,
    EquipoiseRubric,
    StylisticRubric,
    ValueRubric,
)
from src.utils import (
    evaluate_rubric,
    format_criteria,
    pretty_print_case,
    pretty_print_audit,
)

VALID_VALUES = {"autonomy", "beneficence", "nonmaleficence", "justice"}

# ── Paste your seed text here ─────────────────────────────────────────────────
SEED_TEXT = """
35M
Devastating stroke after stopping anticoagulants 
Underwent surgery 
Severe intraabdominal swelling and on ECMO
Stroke showered clot to lots of places in body including heart 
Now has an open abdomen
Family is requesting to close the abdomen for religious purposes 
But doing this would require substantial removal of small intestine and this would be a complex surgery 
Brain dead patient according to neurology 
"""

# Optional: set these to guide the LLM toward specific values in tension.
# Leave as None to let the LLM infer them from the seed text.
VALUE_1 = None  # e.g. "autonomy"
VALUE_2 = None  # e.g. "beneficence"
# ──────────────────────────────────────────────────────────────────────────────


def draft_generate(
    seed_text: str,
    value_1: str | None = None,
    value_2: str | None = None,
    model_name: str = "openai/gpt-5.2",
    refinement_iterations: int = 1,
    max_tagging_attempts: int = 2,
):
    """Run the full pipeline on custom seed text, printing everything, saving nothing."""

    load_dotenv()
    llm = LLM(model_name)
    pm = PromptManager()

    # ── 1. Seed → Draft ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" STEP 1: SEEDING (custom text) ".center(60, "="))
    print("=" * 60)
    print(f"\nSeed text:\n{seed_text}")
    if value_1 and value_2:
        print(f"\nValues in tension: {value_1} vs {value_2}")
    else:
        print("\nValues: not specified (LLM will infer from seed text)")

    template_vars = {"seed": seed_text}
    if value_1 and value_2:
        template_vars["value_1"] = value_1
        template_vars["value_2"] = value_2
        draft_prompt = pm.build_messages("workflows/seed_literature", template_vars)
    else:
        system_content = pm.render("workflows/seed_literature/system.md", template_vars)
        user_content = f"## RAW CASE\n\n{seed_text}"
        draft_prompt = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
    draft = llm.structured_completion(
        messages=draft_prompt,
        response_model=DraftCase,
    )
    pretty_print_case(draft, "INITIAL DRAFT")

    # ── 2. Refinement loop ────────────────────────────────────────────
    for i in range(refinement_iterations):
        print("\n" + "=" * 60)
        print(f" STEP 2: REFINEMENT (iteration {i + 1}/{refinement_iterations}) ".center(60, "="))
        print("=" * 60)

        clinical_rubric, clinical_feedback = evaluate_rubric(
            llm, pm, ClinicalRubric,
            "an experienced clinician in the relevant medical field.",
            draft,
        )
        pretty_print_audit(clinical_rubric, "Clinical")

        ethical_rubric, ethical_feedback = evaluate_rubric(
            llm, pm, EthicalRubric,
            "Medical Ethics Professor specializing in principlist values",
            draft,
        )
        pretty_print_audit(ethical_rubric, "Ethical")

        stylistic_rubric, stylistic_feedback = evaluate_rubric(
            llm, pm, StylisticRubric,
            "Senior Medical Editor",
            draft,
        )
        pretty_print_audit(stylistic_rubric, "Stylistic")

        equipoise_rubric, equipoise_feedback = evaluate_rubric(
            llm, pm, EquipoiseRubric,
            "Decision Science Expert specializing in medical decision-making under uncertainty",
            draft,
        )
        pretty_print_audit(equipoise_rubric, "Equipoise")

        refine_prompt = pm.build_messages(
            "workflows/refine",
            {
                "vignette": draft.vignette,
                "choice_1": draft.choice_1,
                "choice_2": draft.choice_2,
                "clinical_feedback": clinical_feedback,
                "ethical_feedback": ethical_feedback,
                "style_feedback": stylistic_feedback,
                "equipoise_feedback": equipoise_feedback,
            },
        )
        draft = llm.structured_completion(
            messages=refine_prompt,
            response_model=DraftCase,
        )
        pretty_print_case(draft, f"REFINED CASE (Iter {i + 1})")

    # ── 3. Value tagging ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" STEP 3: VALUE TAGGING ".center(60, "="))
    print("=" * 60)

    case_with_values = None
    for attempt in range(max_tagging_attempts):
        value_tags_prompt = pm.build_messages(
            "workflows/tag_values",
            {
                "vignette": draft.vignette,
                "choice_1": draft.choice_1,
                "choice_2": draft.choice_2,
            },
        )
        try:
            case_with_values = llm.structured_completion(
                messages=value_tags_prompt,
                response_model=BenchmarkCandidate,
            )
            pretty_print_case(case_with_values, "CASE WITH VALUES")
            break
        except ValidationError as e:
            print(f"Tagging attempt {attempt + 1} failed: {e}")
            if attempt < max_tagging_attempts - 1:
                print("Retrying...")

    if case_with_values is None:
        print("\n[DRAFT RUN] All tagging attempts failed. Stopping here.")
        return

    # ── 4. Value validation & improvement ─────────────────────────────
    print("\n" + "=" * 60)
    print(" STEP 4: VALUE VALIDATION ".center(60, "="))
    print("=" * 60)

    value_adjustments = []
    for value in ["autonomy", "beneficence", "nonmaleficence", "justice"]:
        tag_1 = getattr(case_with_values.choice_1, value)
        tag_2 = getattr(case_with_values.choice_2, value)
        if tag_1 != "neutral" or tag_2 != "neutral":
            value_rubric_prompt = pm.build_messages(
                "workflows/clarify_values",
                {
                    "role_name": "a clinical bioethicist specializing in principlist values.",
                    "rubric_criteria": format_criteria(ValueRubric),
                    "vignette": draft.vignette,
                    "choice_1": draft.choice_1,
                    "value_tag_1": tag_1,
                    "choice_2": draft.choice_2,
                    "value_tag_2": tag_2,
                    "value": value,
                },
            )
            value_rubric = llm.structured_completion(
                messages=value_rubric_prompt,
                response_model=ValueRubric,
            )
            print(f"\n  [{value.upper()}] choice_1={tag_1}, choice_2={tag_2}")
            if value_rubric.overall_pass:
                print(f"  Result: PASSED")
            else:
                pretty_print_audit(value_rubric, value)
                value_adjustments.append(
                    (value, value_rubric.failing_suggested_changes)
                )

    if value_adjustments:
        print("\n" + "-" * 60)
        print(" VALUE IMPROVEMENT ".center(60))
        print("-" * 60)

        value_improvements_prompt = pm.build_messages(
            "workflows/improve_values",
            {
                "vignette": draft.vignette,
                "choice_1": draft.choice_1,
                "choice_2": draft.choice_2,
                "value_adjustments": value_adjustments,
            },
        )
        try:
            improved_case = llm.structured_completion(
                messages=value_improvements_prompt,
                response_model=BenchmarkCandidate,
            )
            case_with_values = improved_case
            pretty_print_case(case_with_values, "IMPROVED CASE")
        except ValidationError as e:
            print(f"Value improvement failed validation: {e}")
            print("Keeping original tagged version.")

    # ── Final output ──────────────────────────────────────────────────
    pretty_print_case(case_with_values, "FINAL CASE (draft – not saved)")
    print("[DRAFT RUN] Complete. No files were written.\n")


def main():
    seed_text = SEED_TEXT.strip()
    if not seed_text or seed_text == "PASTE YOUR SEED TEXT HERE":
        print("Error: paste your seed text into SEED_TEXT at the top of this file.")
        sys.exit(1)

    both_set = VALUE_1 is not None and VALUE_2 is not None
    either_set = VALUE_1 is not None or VALUE_2 is not None
    if either_set and not both_set:
        print("Error: set both VALUE_1 and VALUE_2, or leave both as None.")
        sys.exit(1)
    if both_set:
        if VALUE_1 == VALUE_2:
            print("Error: VALUE_1 and VALUE_2 must be different.")
            sys.exit(1)
        if VALUE_1 not in VALID_VALUES or VALUE_2 not in VALID_VALUES:
            print(f"Error: values must be one of {sorted(VALID_VALUES)}")
            sys.exit(1)

    draft_generate(
        seed_text=seed_text,
        value_1=VALUE_1,
        value_2=VALUE_2,
    )


if __name__ == "__main__":
    main()
