"""Runner infrastructure for LLM decision evaluation.

This module provides utilities for:
- Loading and filtering cases
- Managing decision records with atomic I/O
- Main execution loop with resume support
"""

import json
import logging
import tempfile
import shutil
import time
from pathlib import Path

import hydra
from omegaconf import DictConfig, OmegaConf
from tqdm import tqdm
from all_the_llms import LLM
from src.response_models.case import BenchmarkCandidate
from src.response_models.record import CaseRecord
from src.response_models.status import CaseStatus
from src.llm_decisions.models import DecisionRecord, ModelDecisionData, RunResult
from src.llm_decisions.parser import parse_response
from src.prompt_manager import PromptManager

# Suppress LiteLLM logging and informational output
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("all_the_llms.model_router").setLevel(logging.WARNING)
logging.getLogger("all_the_llms.llm").setLevel(logging.WARNING)

# Suppress LiteLLM's "Provider List" and debug info messages printed to stdout
import litellm
litellm.suppress_debug_info = True


def _load_case_record(case_file: Path) -> CaseRecord | None:
    """Helper to load a case record from file."""
    try:
        with open(case_file, 'r') as f:
            return CaseRecord(**json.load(f))
    except Exception as e:
        print(f"Warning: Failed to load case from {case_file}: {e}")
        return None


def _get_case_files(cases_dir: Path) -> list[Path]:
    """Helper to get and validate case files."""
    if not cases_dir.exists():
        raise ValueError(f"Cases directory does not exist: {cases_dir}")
    
    case_files = list(cases_dir.glob("case_*.json"))
    if not case_files:
        raise ValueError(f"No case files found in {cases_dir}")
    
    return case_files


def get_approved_case_ids(cases_dir: str | Path = "data/cases") -> list[str]:
    """Get list of all approved case IDs.
    
    Args:
        cases_dir: Path to directory containing case JSON files
    
    Returns:
        List of case IDs with APPROVED status
        
    Raises:
        ValueError: If cases directory doesn't exist or has no case files
    """
    case_files = _get_case_files(Path(cases_dir))
    
    approved_ids = []
    for case_file in case_files:
        record = _load_case_record(case_file)
        if record and record.status == CaseStatus.APPROVED and record.final_case:
            approved_ids.append(record.case_id)
    
    return approved_ids


def load_case_by_id(case_id: str, cases_dir: str | Path = "data/cases") -> BenchmarkCandidate:
    """Load a single case by its ID.
    
    Args:
        case_id: The case ID to load
        cases_dir: Path to directory containing case JSON files
    
    Returns:
        BenchmarkCandidate object for the requested case
        
    Raises:
        ValueError: If case is not found, not approved, or has no valid final_case
    """
    cases_dir = Path(cases_dir)
    matching_files = list(cases_dir.glob(f"case_{case_id}_*.json"))
    
    if not matching_files:
        raise ValueError(f"Case ID not found: {case_id}")
    if len(matching_files) > 1:
        raise ValueError(f"Multiple files found for case {case_id}: {[f.name for f in matching_files]}")
    
    record = _load_case_record(matching_files[0])
    if not record:
        raise ValueError(f"Failed to load case {case_id}")
    
    if record.case_id != case_id:
        raise ValueError(f"File contains case_id {record.case_id}, expected {case_id}")
    if record.status != CaseStatus.APPROVED:
        raise ValueError(f"Case {case_id} has status '{record.status.value}', not 'approved'")
    if not record.final_case:
        raise ValueError(f"Case {case_id} is approved but has no valid final_case")
    
    return record.final_case


def sanitize_model_name(model: str) -> str:
    """Convert model identifier to filesystem-safe name.
    
    Example: 'openai/gpt-4o' -> 'openai-gpt-4o'
    """
    return model.replace('/', '-')


def get_decision_record(
    case_id: str,
    output_dir: str | Path = "data/llm_decisions",
    cases_dir: str | Path = "data/cases"
) -> DecisionRecord:
    """Load existing decision record or create new one for a case.
    
    Enables resume functionality - if a record already exists with partial
    results, it will be loaded and can be continued.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    record_path = output_dir / f"{case_id}.json"
    
    if record_path.exists():
        with open(record_path, 'r') as f:
            record = DecisionRecord(**json.load(f))
        
        if record.case_id != case_id:
            raise ValueError(f"Record file contains case_id {record.case_id}, expected {case_id}")
        
        return record
    
    # Create new record
    case = load_case_by_id(case_id, cases_dir)
    return DecisionRecord(case_id=case_id, case=case)


def save_decision_record(record: DecisionRecord, output_dir: str | Path = "data/llm_decisions") -> None:
    """Save decision record to JSON with atomic write."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    record_path = output_dir / f"{record.case_id}.json"
    
    # Atomic write: write to temp file, then move
    with tempfile.NamedTemporaryFile(mode='w', dir=output_dir, delete=False, suffix='.tmp') as tmp_file:
        tmp_file.write(record.model_dump_json(indent=2))
        tmp_file.flush()
        tmp_path = tmp_file.name
    
    shutil.move(tmp_path, record_path)


def get_or_create_model_data(record: DecisionRecord, model_name: str, temperature: float) -> ModelDecisionData:
    """Get existing model data or create new entry in the record."""
    if model_name not in record.models:
        record.models[model_name] = ModelDecisionData(temperature=temperature)
    return record.models[model_name]


def call_target_llm(
    llm: LLM,
    case: BenchmarkCandidate,
    temperature: float,
    max_api_retries: int = 3,
    backoff_base: float = 2.0,
    prompt_manager: PromptManager | None = None
) -> dict:
    """Call target LLM with physician recommendation prompt and retry logic."""
    if prompt_manager is None:
        prompt_manager = PromptManager()
    
    messages = prompt_manager.build_messages(
        "workflows/physician_recommendation",
        {
            "vignette": case.vignette,
            "choice_1": case.choice_1.choice,
            "choice_2": case.choice_2.choice
        }
    )
    
    last_exception = None
    
    for attempt in range(max_api_retries):
        try:
            response = llm.completion(messages=messages, temperature=temperature)
            
            # Convert response to dict
            if hasattr(response, 'model_dump'):
                return response.model_dump()
            elif hasattr(response, 'dict'):
                return response.dict()
            else:
                return dict(response)
                
        except Exception as e:
            last_exception = e
            
            if attempt == max_api_retries - 1:
                break
            
            delay = backoff_base ** attempt
            print(f"Warning: LLM call failed (attempt {attempt + 1}/{max_api_retries}): {e}")
            print(f"Retrying in {delay:.1f} seconds...")
            time.sleep(delay)
    
    raise Exception(f"Failed to get response after {max_api_retries} attempts") from last_exception


def get_case_ids_from_config(config: DictConfig, cases_dir: str | Path = "data/cases") -> list[str]:
    """Get list of case IDs based on config selection mode."""
    case_selection = config.get("case_selection", {})
    mode = case_selection.get("mode", "approved")
    
    if mode == "approved":
        return get_approved_case_ids(cases_dir)
    
    elif mode == "all":
        case_files = _get_case_files(Path(cases_dir))
        case_ids = []
        for case_file in case_files:
            record = _load_case_record(case_file)
            if record:
                case_ids.append(record.case_id)
        return case_ids
    
    elif mode == "explicit":
        case_ids = case_selection.get("case_ids", [])
        if not case_ids:
            raise ValueError("case_selection mode is 'explicit' but case_ids list is empty")
        return list(case_ids)
    
    else:
        raise ValueError(f"Invalid case_selection mode: '{mode}'. Must be 'approved', 'all', or 'explicit'")


def _parse_with_retry(
    case: BenchmarkCandidate,
    response_text: str,
    parser_llm: LLM,
    prompt_manager: PromptManager,
    max_retries: int,
    backoff_base: float
) -> str | None:
    """Parse LLM response with retry logic."""
    for attempt in range(max_retries):
        try:
            parsed_decision = parse_response(
                choice_1_text=case.choice_1.choice,
                choice_2_text=case.choice_2.choice,
                llm_response=response_text,
                parser_llm=parser_llm,
                prompt_manager=prompt_manager
            )
            return parsed_decision.selected_choice
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(backoff_base ** attempt)
            else:
                tqdm.write(f"PARSE ERROR: {e}")
                return None


def _run_single_evaluation(
    llm: LLM,
    case: BenchmarkCandidate,
    temperature: float,
    max_api_retries: int,
    max_parse_retries: int,
    backoff_base: float,
    parser_llm: LLM,
    prompt_manager: PromptManager
) -> RunResult | None:
    """Run a single evaluation and return the result."""
    try:
        # Call target LLM
        full_response = call_target_llm(
            llm=llm,
            case=case,
            temperature=temperature,
            max_api_retries=max_api_retries,
            backoff_base=backoff_base,
            prompt_manager=prompt_manager
        )
        
        # Extract and parse response
        response_text = full_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed_choice = _parse_with_retry(
            case, response_text, parser_llm, prompt_manager, max_parse_retries, backoff_base
        )
        
        if not parsed_choice:
            return None
        
        return RunResult(full_response=full_response, parsed_choice=parsed_choice)
        
    except Exception as e:
        tqdm.write(f"ERROR: {e}")
        return None


@hydra.main(version_base=None, config_path="../config", config_name="decisions")
def run_evaluation(cfg: DictConfig, cases_dir: str | Path = "data/cases", verbose: bool = True) -> None:
    """Main execution loop for LLM decision evaluation with resume support."""
    # Extract config values
    case_ids = get_case_ids_from_config(cfg, cases_dir)
    
    if verbose:
        print(f"\nLoaded config: {len(cfg.models)} models, {len(case_ids)} cases, {cfg.execution.runs_per_model} runs per model")
        print(f"Total evaluations: {len(cfg.models) * len(case_ids) * cfg.execution.runs_per_model:,}")
        print(f"Output directory: {cfg.output.dir}\n")
    
    # Initialize shared resources
    prompt_manager = PromptManager()
    parser_llm = LLM(cfg.execution.parser_model)
    
    # Create model instances once and reuse them
    model_llms = {}
    for model_name in cfg.models:
        model = LLM(model_name)
        print(f"Looking for {model_name} and found {model.model_name}")
        model_llms[model_name] = model
    
    total_runs_completed = 0
    total_expected_runs = len(cfg.models) * len(case_ids) * cfg.execution.runs_per_model
    
    # Main loop with progress bars
    for case_id in tqdm(case_ids, desc="Cases", position=0, disable=not verbose):
        try:
            record = get_decision_record(case_id, cfg.output.dir, cases_dir)
        except Exception as e:
            tqdm.write(f"ERROR: Failed to load case {case_id}: {e}")
            continue
        
        for model_name in tqdm(cfg.models, desc="Models", position=1, leave=False, disable=not verbose):
            try:
                model_data = get_or_create_model_data(record, model_name, cfg.execution.temperature)
                runs_completed = model_data.runs_completed
                
                if runs_completed >= cfg.execution.runs_per_model:
                    total_runs_completed += cfg.execution.runs_per_model
                    continue
                
                # Run missing evaluations
                runs_pbar = tqdm(
                    range(runs_completed, cfg.execution.runs_per_model),
                    desc="Runs",
                    position=2,
                    leave=False,
                    disable=not verbose,
                    initial=runs_completed,
                    total=cfg.execution.runs_per_model
                )
                
                for _ in runs_pbar:
                    try:
                        result = _run_single_evaluation(
                            llm=model_llms[model_name],
                            case=record.case,
                            temperature=cfg.execution.temperature,
                            max_api_retries=cfg.retry.max_api_retries,
                            max_parse_retries=cfg.retry.max_parse_retries,
                            backoff_base=cfg.retry.backoff_base,
                            parser_llm=parser_llm,
                            prompt_manager=prompt_manager
                        )
                        
                        if result:
                            model_data.runs.append(result)
                            save_decision_record(record, cfg.output.dir)
                            total_runs_completed += 1
                            runs_pbar.set_postfix({"choice": result.parsed_choice})
                            
                    except KeyboardInterrupt:
                        if verbose:
                            tqdm.write("\n\nInterrupted by user. Saving progress...")
                            tqdm.write(f"Completed {total_runs_completed}/{total_expected_runs} runs ({100*total_runs_completed/total_expected_runs:.1f}%)")
                        save_decision_record(record, cfg.output.dir)
                        raise
                
                runs_pbar.close()
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                tqdm.write(f"ERROR with model {model_name}: {e}")
    
    if verbose:
        print(f"\n✓ Evaluation complete!")
        print(f"Total runs completed: {total_runs_completed}/{total_expected_runs} ({100*total_runs_completed/total_expected_runs:.1f}%)")
        print(f"Results saved to: {cfg.output.dir}")
