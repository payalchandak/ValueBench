import random

from all_the_llms import LLM
from dotenv import load_dotenv
from prompt_manager import PromptManager
from response_models.case import DraftCase, BenchmarkCandidate
from response_models.feasibility import FeasibilityDecision
from response_models.rubric import (
    ClinicalRubric,
    EthicalRubric,
    StylisticRubric,
    ValueRubric,
)
from prompts.components.synthetic_components import (
    DEFAULT_MEDICAL_SETTINGS_AND_DOMAINS,
    VALUES_WITHIN_PAIRS,
)
from utils import *


# Choose whether to seed from a raw literature case ("literature") or a synthetic seed vignette ("synthetic").
SEED_MODE = "synthetic"  # options: "literature", "synthetic"


def get_seeded_draft(
    llm: LLM,
    pm: PromptManager,
    seed_mode: str,
    max_synthetic_feasibility_attempts: int = 5,
) -> DraftCase:
    """
    Produce an initial DraftCase using either a literature seed
    (raw case text from seed.txt) or a synthetic specification of
    values + domain + setting.
    """
    if seed_mode == "literature":
        # Literature-based seeding: read a raw clinical/ethics case from seed.txt
        with open("seed.txt", "r") as f:
            seed_text = f.read().strip()

        draft_prompt = pm.build_messages("workflows/seed_literature", {"seed": seed_text})
    else:
        # Synthetic seeding: sample a bounded number of times from value pairs and
        # curated (setting, domain) pairs, with a feasibility gate to avoid bad combos.
        value_a = value_b = medical_domain = medical_setting = None
        decision = "start_over"

        for _ in range(max_synthetic_feasibility_attempts):
            value_a, value_b = random.choice(VALUES_WITHIN_PAIRS)
            medical_setting, medical_domain = random.choice(DEFAULT_MEDICAL_SETTINGS_AND_DOMAINS)

            feasibility_prompt = pm.build_messages(
                "workflows/seed_synthetic_feasibility",
                {
                    "value_a": value_a,
                    "value_b": value_b,
                    "medical_domain": medical_domain,
                    "medical_setting": medical_setting,
                },
            )
            feasibility_decision = llm.structured_completion(
                messages=feasibility_prompt,
                response_model=FeasibilityDecision,
            )
            decision = feasibility_decision.decision
            pretty_print_seed_candidate(
                value_a, value_b, medical_domain, medical_setting, decision
            )

            if decision == "continue":
                break

        # If all attempts requested "start_over", fall back to the last sampled combination.
        draft_prompt = pm.build_messages(
            "workflows/seed_synthetic",
            {
                "value_a": value_a,
                "value_b": value_b,
                "medical_domain": medical_domain,
                "medical_setting": medical_setting,
            },
        )

    draft = llm.structured_completion(
        messages=draft_prompt,
        response_model=DraftCase,
    )
    pretty_print_case(draft)
    return draft

def main() -> None:
    load_dotenv()
    llm = LLM("gpt-5-mini", routing_judge="gpt-5-mini")
    pm = PromptManager()

    draft = get_seeded_draft(llm, pm, SEED_MODE)

    # todo: embedding based diversity gate

    for _ in range(2):
        clinical_rubric_prompt = pm.build_messages(
            "workflows/rubric",
            {
                "role_name": "Senior Attending Physician and Medical Director",
                "rubric_criteria": format_criteria(ClinicalRubric),
                "vignette": draft.vignette,
                "choice_1": draft.choice_1,
                "choice_2": draft.choice_2,
            },
        )
        clinical_rubric = llm.structured_completion(
            messages=clinical_rubric_prompt,
            response_model=ClinicalRubric,
        )
        print(f"Passing: {clinical_rubric.overall_pass}")
        pretty_print_audit(clinical_rubric, "Clinical")

        ethical_rubric_prompt = pm.build_messages(
            "workflows/rubric",
            {
                "role_name": "Medical Ethics Professor specializing in principlist values",
                "rubric_criteria": format_criteria(EthicalRubric),
                "vignette": draft.vignette,
                "choice_1": draft.choice_1,
                "choice_2": draft.choice_2,
            },
        )
        ethical_rubric = llm.structured_completion(
            messages=ethical_rubric_prompt,
            response_model=EthicalRubric,
        )
        print(f"Passing: {ethical_rubric.overall_pass}")
        pretty_print_audit(ethical_rubric, "Ethical")

        stylistic_rubric_prompt = pm.build_messages(
            "workflows/rubric",
            {
                "role_name": "Senior Medical Editor",
                "rubric_criteria": format_criteria(StylisticRubric),
                "vignette": draft.vignette,
                "choice_1": draft.choice_1,
                "choice_2": draft.choice_2,
            },
        )
        stylistic_rubric = llm.structured_completion(
            messages=stylistic_rubric_prompt,
            response_model=StylisticRubric,
        )
        print(f"Passing: {stylistic_rubric.overall_pass}")
        pretty_print_audit(stylistic_rubric, "Stylistic")

        clinical_feedback = (
            clinical_rubric.all_suggested_changes
            if not clinical_rubric.overall_pass
            else "No issues detected."
        )
        ethical_feedback = (
            ethical_rubric.all_suggested_changes
            if not ethical_rubric.overall_pass
            else "No issues detected."
        )
        stylistic_feedback = (
            stylistic_rubric.all_suggested_changes
            if not stylistic_rubric.overall_pass
            else "No issues detected."
        )
        refine_prompt = pm.build_messages(
            "workflows/refine",
            {
                "old_vignette": draft.vignette,
                "old_choice_1": draft.choice_1,
                "old_choice_2": draft.choice_2,
                "clinical_feedback": clinical_feedback,
                "ethical_feedback": ethical_feedback,
                "style_feedback": stylistic_feedback,
            },
        )
        refined = llm.structured_completion(
            messages=refine_prompt,
            response_model=DraftCase,
        )

        pretty_print_case(refined, "REFINED CASE")
        draft = refined

    value_tags_prompt = pm.build_messages(
        "workflows/tag_values",
        {
            "vignette": draft.vignette,
            "choice_1": draft.choice_1,
            "choice_2": draft.choice_2,
        },
    )

    case_with_values = llm.structured_completion(
        messages=value_tags_prompt,
        response_model=BenchmarkCandidate,
    )
    pretty_print_case(case_with_values, "CASE WITH VALUES")

    value_adjustments = []
    for value in ["autonomy", "beneficence", "nonmaleficence", "justice"]:
        tag_1 = case_with_values.choice_1.__dict__[value]
        tag_2 = case_with_values.choice_2.__dict__[value]
        if tag_1 != "neutral" or tag_2 != "neutral":
            value_rubric_prompt = pm.build_messages(
                "workflows/clarify_values",
                {
                    "role_name": "",
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
            if not value_rubric.overall_pass:
                pretty_print_audit(value_rubric, value)
                value_adjustments.append(
                    (value, value_rubric.failing_suggested_changes)
                )

    if value_adjustments:
        value_improvements_prompt = pm.build_messages(
            "workflows/improve_values",
            {
                "old_vignette": draft.vignette,
                "old_choice_1": draft.choice_1,
                "old_choice_2": draft.choice_2,
                "value_adjustments": value_adjustments,
            },
        )
        case_with_values = llm.structured_completion(
            messages=value_improvements_prompt,
            response_model=BenchmarkCandidate,
        )

    pretty_print_case(case_with_values, "FINAL CASE")


if __name__ == "__main__":
    main()


