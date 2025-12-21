import json
import random

import hydra
from omegaconf import DictConfig
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
from utils import evaluate_rubric

def _load_random_within_patient_case(
    unified_cases_path: str = "unified_ethics_cases.json",
) -> tuple[str, str, str]:
    """
    Returns (case_text, value_1, value_2) sampled from unified_ethics_cases.json.

    "within" cases correspond to patient-level dilemmas using the Principlism values
    (Autonomy, Beneficence, Non-maleficence, Justice).
    """
    with open(unified_cases_path, "r") as f:
        cases = json.load(f)

    within_patient_cases = [c for c in cases if c.get("scenario_type") == "within"]

    if not within_patient_cases:
        raise ValueError(
            f"No 'within' patient cases found in {unified_cases_path!r}. "
            "Expected entries with scenario_type='within' and value_1/value_2 in "
            "{autonomy, beneficence, non-maleficence, justice}."
        )

    chosen = random.choice(within_patient_cases)
    return chosen["case"].strip(), chosen["value_1"], chosen["value_2"]




def get_seeded_draft(
    llm: LLM,
    pm: PromptManager,
    seed_mode: str,
    max_synthetic_feasibility_attempts: int = 5,
) -> DraftCase:
    """
    Produce an initial DraftCase using either a literature seed
    (raw case text sampled from unified_ethics_cases.json) or a synthetic specification of
    values + domain + setting.
    """
    if seed_mode == "literature":
        # Literature-based seeding: sample a raw clinical/ethics case from unified_ethics_cases.json
        seed_text, value_1, value_2 = _load_random_within_patient_case()

        draft_prompt = pm.build_messages(
            "workflows/seed_literature",
            {"seed": seed_text, "value_1": value_1, "value_2": value_2},
        )
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

@hydra.main(version_base=None, config_path="config", config_name="generator")
def main(cfg: DictConfig) -> None:
    load_dotenv()

    llm = LLM(cfg.model_name)
    pm = PromptManager()

    draft = get_seeded_draft(
        llm, pm, cfg.seed_mode, cfg.max_synthetic_feasibility_attempts
    )

    # todo: embedding based diversity gate

    for _ in range(cfg.refinement_iterations):
        clinical_rubric, clinical_feedback = evaluate_rubric(
            llm,
            pm,
            ClinicalRubric,
            "an experienced clinician in the relevant medical field.",
            draft
        )
        print(f"Passing: {clinical_rubric.overall_pass}")
        pretty_print_audit(clinical_rubric, "Clinical")

        ethical_rubric, ethical_feedback = evaluate_rubric(
            llm,
            pm,
            EthicalRubric,
            "Medical Ethics Professor specializing in principlist values",
            draft
        )
        print(f"Passing: {ethical_rubric.overall_pass}")
        pretty_print_audit(ethical_rubric, "Ethical")

        stylistic_rubric, stylistic_feedback = evaluate_rubric(
            llm,
            pm,
            StylisticRubric,
            "Senior Medical Editor",
            draft
        )
        print(f"Passing: {stylistic_rubric.overall_pass}")
        pretty_print_audit(stylistic_rubric, "Stylistic")
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


