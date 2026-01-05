import json
import random
import os
import logging

import hydra
from omegaconf import DictConfig, OmegaConf
from all_the_llms import LLM
from dotenv import load_dotenv
from pydantic import ValidationError
from src.prompt_manager import PromptManager

# Suppress litellm logging
os.environ["LITELLM_LOG"] = "ERROR"
import litellm
litellm.suppress_debug_info = True
litellm.set_verbose = False

# Suppress all_the_llms and LiteLLM logging
logging.getLogger("all_the_llms").setLevel(logging.ERROR)
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)
from src.response_models.case import DraftCase, BenchmarkCandidate
from src.response_models.feasibility import FeasibilityDecision
from src.response_models.rubric import (
    ClinicalRubric,
    EthicalRubric,
    EquipoiseRubric,
    StylisticRubric,
    ValueRubric,
)
from src.response_models.record import IterationRecord, SeedContext, CaseRecord
from src.response_models.status import CaseStatus
from src.embeddings import CaseEmbeddingStore
from src.prompts.components.synthetic_components import (
    DEFAULT_MEDICAL_SETTINGS_AND_DOMAINS,
    VALUES_WITHIN_PAIRS,
)
from src.utils import *
from src.utils import evaluate_rubric

def _load_random_within_patient_case(
    unified_cases_path: str = "data/seed/unified_ethics_cases.json",
    seed_index: int | None = None,
) -> tuple[str, str, str]:
    """
    Returns (case_text, value_1, value_2) from unified_ethics_cases.json.

    "within" cases correspond to patient-level dilemmas using the Principlism values
    (Autonomy, Beneficence, Non-maleficence, Justice).

    Args:
        unified_cases_path: Path to the unified ethics cases JSON file.
        seed_index: Optional 0-based index to select a specific case.
                   If None, a random case is selected.

    Returns:
        Tuple of (case_text, value_1, value_2).

    Raises:
        ValueError: If no 'within' cases found or seed_index is out of bounds.
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

    if seed_index is not None:
        if seed_index < 0 or seed_index >= len(within_patient_cases):
            raise ValueError(
                f"seed_index {seed_index} is out of bounds. "
                f"Valid range: 0 to {len(within_patient_cases) - 1} "
                f"({len(within_patient_cases)} 'within' cases available)."
            )
        chosen = within_patient_cases[seed_index]
    else:
        chosen = random.choice(within_patient_cases)

    return chosen["case"].strip(), chosen["value_1"], chosen["value_2"]




def get_seeded_draft(
    llm: LLM,
    pm: PromptManager,
    seed_mode: str,
    max_synthetic_feasibility_attempts: int = 5,
    verbose: bool = False,
    seed_index: int | None = None,
    unified_cases_path: str = "data/seed/unified_ethics_cases.json",
) -> tuple[DraftCase, SeedContext]:
    """
    Produce an initial DraftCase using either a literature seed
    (raw case text sampled from unified_ethics_cases.json) or a synthetic specification of
    values + domain + setting.

    Args:
        llm: LLM instance for generating completions.
        pm: PromptManager for building prompts.
        seed_mode: Either "literature" or "synthetic".
        max_synthetic_feasibility_attempts: Max attempts for synthetic feasibility check.
        verbose: Whether to print verbose output.
        seed_index: Optional 0-based index for literature mode to select a specific seed case.
                   Ignored for synthetic mode.
        unified_cases_path: Path to the unified ethics cases JSON file (literature mode only).
    """
    if seed_mode == "literature":
        # Literature-based seeding: sample a raw clinical/ethics case from unified_ethics_cases.json
        seed_text, value_1, value_2 = _load_random_within_patient_case(
            unified_cases_path=unified_cases_path,
            seed_index=seed_index,
        )

        draft_prompt = pm.build_messages(
            "workflows/seed_literature",
            {"seed": seed_text, "value_1": value_1, "value_2": value_2},
        )
        seed_context = SeedContext(
            mode="literature",
            parameters={"source_text": seed_text, "value_1": value_1, "value_2": value_2}
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
            if verbose:
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
        seed_context = SeedContext(
            mode="synthetic",
            parameters={
                "value_a": value_a,
                "value_b": value_b,
                "medical_domain": medical_domain,
                "medical_setting": medical_setting,
            }
        )

    draft = llm.structured_completion(
        messages=draft_prompt,
        response_model=DraftCase,
    )
    if verbose:
        pretty_print_case(draft)
    return draft, seed_context

def generate_single_case(
    cfg: DictConfig,
    llm: LLM,
    pm: PromptManager,
    case_embedding_store: CaseEmbeddingStore | None = None,
    seed_index: int | None = None,
) -> CaseRecord | None:
    """
    Generate a single benchmark case through the full pipeline.

    This function handles the complete case generation workflow:
    1. Seeding (literature or synthetic)
    2. Diversity gate check
    3. Multi-rubric refinement loop
    4. Value tagging and validation
    5. Saving the final case record

    Args:
        cfg: Hydra configuration (DictConfig from generator.yaml).
        llm: LLM instance for generating completions.
        pm: PromptManager for building prompts.
        case_embedding_store: Optional embedding store for diversity checks.
        seed_index: Optional 0-based index for literature mode to select a specific
                   seed case. If None, a random case is selected. Ignored for
                   synthetic mode.

    Returns:
        CaseRecord if generation succeeds, None if the case was skipped
        (e.g., failed diversity check or tagging validation).
    """
    # Get unified_cases_path from config with fallback default
    unified_cases_path = cfg.get("unified_cases_path", "data/seed/unified_ethics_cases.json")
    
    # Retry loop for diversity (literature mode gets retries, synthetic mode discards immediately)
    max_diversity_retries = cfg.diversity_gate.max_diversity_retries if cfg.seed_mode == "literature" else 1
    is_diverse = False
    draft = None
    seed_context = None

    for diversity_attempt in range(max_diversity_retries):
        draft, seed_context = get_seeded_draft(
            llm, pm, cfg.seed_mode, cfg.max_synthetic_feasibility_attempts, cfg.verbose,
            seed_index=seed_index,
            unified_cases_path=unified_cases_path,
        )

        # Diversity gate check
        if case_embedding_store and cfg.diversity_gate.enabled:
            is_diverse, similar_id, similarity = case_embedding_store.check_diversity(
                draft,
                threshold=cfg.diversity_gate.similarity_threshold
            )

            if not is_diverse:
                if cfg.verbose:
                    print(f"[DIVERSITY] Too similar to {similar_id} ({similarity:.3f})")

                if cfg.seed_mode == "synthetic":
                    # Synthetic: discard immediately, no retry
                    break
                # Literature: retry with new seed (only if seed_index is None)
                if seed_index is not None:
                    # Specific seed requested, cannot retry with different seed
                    break
                continue
        else:
            # Diversity gate disabled, proceed
            is_diverse = True

        if is_diverse:
            break

    # Return None if diversity check failed
    if not is_diverse:
        if cfg.verbose:
            print(f"[DIVERSITY] Skipping case (max retries reached or duplicate)")
        return None

    # Initialize the CaseRecord for record keeping
    case_record = CaseRecord(
        model_name=cfg.model_name,
        generator_config=OmegaConf.to_container(cfg, resolve=True),
        seed=seed_context,
        status=CaseStatus.DRAFT
    )

    # Log the initial seed draft
    case_record.refinement_history.append(IterationRecord(
        iteration=0,
        step_description="initial_draft",
        data=draft
    ))

    for i in range(cfg.refinement_iterations):
        clinical_rubric, clinical_feedback = evaluate_rubric(
            llm,
            pm,
            ClinicalRubric,
            "an experienced clinician in the relevant medical field.",
            draft
        )
        if cfg.verbose:
            pretty_print_audit(clinical_rubric, "Clinical")

        ethical_rubric, ethical_feedback = evaluate_rubric(
            llm,
            pm,
            EthicalRubric,
            "Medical Ethics Professor specializing in principlist values",
            draft
        )
        if cfg.verbose:
            pretty_print_audit(ethical_rubric, "Ethical")

        stylistic_rubric, stylistic_feedback = evaluate_rubric(
            llm,
            pm,
            StylisticRubric,
            "Senior Medical Editor",
            draft
        )
        if cfg.verbose:
            pretty_print_audit(stylistic_rubric, "Stylistic")

        equipoise_rubric, equipoise_feedback = evaluate_rubric(
            llm,
            pm,
            EquipoiseRubric,
            "Decision Science Expert specializing in medical decision-making under uncertainty",
            draft
        )
        if cfg.verbose:
            pretty_print_audit(equipoise_rubric, "Equipoise")

        # Update the latest record entry with evaluations and feedback for refinement
        latest_record = case_record.refinement_history[-1]
        latest_record.clinical_evaluation = clinical_rubric
        latest_record.ethical_evaluation = ethical_rubric
        latest_record.stylistic_evaluation = stylistic_rubric
        latest_record.equipoise_evaluation = equipoise_rubric
        latest_record.feedback = {
            "clinical": clinical_feedback,
            "ethical": ethical_feedback,
            "stylistic": stylistic_feedback,
            "equipoise": equipoise_feedback
        }

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
        refined = llm.structured_completion(
            messages=refine_prompt,
            response_model=DraftCase,
        )

        if cfg.verbose:
            pretty_print_case(refined, f"REFINED CASE (Iter {i+1})")
        draft = refined
        
        # Log the refined draft as a new version
        case_record.refinement_history.append(IterationRecord(
            iteration=i + 1,
            step_description=f"refinement_{i+1}",
            data=draft
        ))

    # Attempt value tagging with retry logic to ensure at least 2 values are involved
    case_with_values = None

    for tagging_attempt in range(cfg.max_tagging_attempts):
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
            if cfg.verbose:
                pretty_print_case(case_with_values, "CASE WITH VALUES")
            break  # Success - at least 2 values are involved
        except ValidationError as e:
            if tagging_attempt < cfg.max_tagging_attempts - 1:
                if cfg.verbose:
                    print(f"Tagging attempt {tagging_attempt + 1} failed: {e}")
                    print("Retrying value tagging...")
            else:
                # Last attempt failed - log and save as failed
                if cfg.verbose:
                    print(f"All {cfg.max_tagging_attempts} tagging attempts failed. Skipping case.")
                case_record.status = CaseStatus.FAILED
                save_case_record(case_record)
                return None

    # Check if we successfully got a case
    if case_with_values is None:
        return None

    # Log the tagged case
    case_record.refinement_history.append(IterationRecord(
        iteration=cfg.refinement_iterations + 1,
        step_description="value_tagging",
        data=case_with_values
    ))

    value_validations = {}
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
            value_validations[value] = value_rubric
            
            if not value_rubric.overall_pass:
                if cfg.verbose:
                    pretty_print_audit(value_rubric, value)
                value_adjustments.append(
                    (value, value_rubric.failing_suggested_changes)
                )

    # Attach validations to the latest record entry
    case_record.refinement_history[-1].value_validations = value_validations

    if value_adjustments:
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
            case_with_values = improved_case  # Use improved version if it passes validation
            
            # Log the final improved version
            case_record.refinement_history.append(IterationRecord(
                iteration=cfg.refinement_iterations + 2,
                step_description="final_improvement",
                data=case_with_values
            ))
        except ValidationError as e:
            # If improvement fails validation, keep the original tagged version
            if cfg.verbose:
                print(f"Value improvement failed validation: {e}")
                print("Keeping original tagged version.")
            # Note: case_with_values still contains the successfully tagged version from earlier

    case_record.status = CaseStatus.NEEDS_REVIEW
    
    if cfg.verbose:
        pretty_print_case(case_with_values, "FINAL CASE")
    
    # Save the complete case record
    save_case_record(case_record)

    # Add to embedding store for future diversity checks
    if case_embedding_store:
        try:
            case_embedding_store.add_case(case_record.case_id, case_with_values)
        except Exception as e:
            if cfg.verbose:
                print(f"[DIVERSITY] Failed to add case to embedding store: {e}")

    return case_record


@hydra.main(version_base=None, config_path="config", config_name="generator")
def main(cfg: DictConfig) -> None:
    """
    CLI entry point for generating a single benchmark case.

    Uses Hydra for configuration management. Key config options:
    - seed_mode: 'literature' or 'synthetic'
    - seed_index: Optional 0-based index for literature mode (null for random)
    - diversity_gate: Configuration for similarity-based deduplication
    """
    load_dotenv()

    llm = LLM(cfg.model_name)
    pm = PromptManager()

    # Initialize diversity gate
    case_embedding_store = None
    if cfg.diversity_gate.enabled:
        include_statuses = list(cfg.diversity_gate.get('include_statuses', ['needs_review']))
        case_embedding_store = CaseEmbeddingStore(include_statuses=include_statuses)

    # Get seed_index from config (None means random)
    seed_index = cfg.get('seed_index', None)

    # Generate a single case
    result = generate_single_case(
        cfg=cfg,
        llm=llm,
        pm=pm,
        case_embedding_store=case_embedding_store,
        seed_index=seed_index,
    )

    if result is None:
        print("[GENERATOR] Case generation skipped (diversity check failed or tagging error)")
    else:
        print(f"[GENERATOR] Successfully generated case: {result.case_id}")


if __name__ == "__main__":
    main()


