"""
Batch generation script for all literature seed cases.

This script iterates through all "within" patient cases in unified_ethics_cases.json
and generates a benchmark case for each seed, calling generate_single_case() from generator.py.

Usage:
    uv run python -m src.generate_all_literature [--start INDEX] [--end INDEX] [--verbose]

Options:
    --start INDEX   Start index (0-based, inclusive). Default: 0
    --end INDEX     End index (0-based, exclusive). Default: total count of within cases
    --verbose       Enable verbose output for each case generation
    --dry-run       Count seeds without generating cases
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf
from all_the_llms import LLM
from tqdm import tqdm

# Suppress litellm logging
os.environ["LITELLM_LOG"] = "ERROR"
import litellm
litellm.suppress_debug_info = True
litellm.set_verbose = False

logging.getLogger("all_the_llms").setLevel(logging.ERROR)
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)

from src.generator import generate_single_case
from src.prompt_manager import PromptManager
from src.embeddings import CaseEmbeddingStore


def count_within_cases(unified_cases_path: str) -> int:
    """Count the number of 'within' patient cases in the unified cases file."""
    with open(unified_cases_path, "r") as f:
        cases = json.load(f)
    return sum(1 for c in cases if c.get("scenario_type") == "within")


def load_config() -> dict:
    """Load generator configuration from YAML file."""
    config_path = Path(__file__).parent / "config" / "generator.yaml"
    return OmegaConf.load(config_path)


def main():
    parser = argparse.ArgumentParser(
        description="Generate benchmark cases for all literature seeds (0-310)."
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start index (0-based, inclusive). Default: 0",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="End index (0-based, exclusive). Default: total count of within cases",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output for each case generation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count seeds without generating cases",
    )
    args = parser.parse_args()

    load_dotenv()

    # Load configuration
    cfg = load_config()
    
    # Override verbose setting from CLI
    if args.verbose:
        cfg.verbose = True
    
    # Force literature mode for this batch script
    cfg.seed_mode = "literature"

    # Count total available seeds
    unified_cases_path = cfg.get("unified_cases_path", "data/seed/unified_ethics_cases.json")
    total_seeds = count_within_cases(unified_cases_path)
    
    # Determine range to process
    start_idx = args.start
    end_idx = args.end if args.end is not None else total_seeds
    
    # Validate range
    if start_idx < 0:
        print(f"Error: start index {start_idx} must be >= 0")
        sys.exit(1)
    if end_idx > total_seeds:
        print(f"Warning: end index {end_idx} exceeds total seeds ({total_seeds}). Clamping to {total_seeds}.")
        end_idx = total_seeds
    if start_idx >= end_idx:
        print(f"Error: start index {start_idx} must be < end index {end_idx}")
        sys.exit(1)
    
    num_to_generate = end_idx - start_idx
    
    print(f"Literature Seed Batch Generator")
    print(f"================================")
    print(f"Total 'within' seeds available: {total_seeds}")
    print(f"Processing range: [{start_idx}, {end_idx}) ({num_to_generate} seeds)")
    print(f"Model: {cfg.model_name}")
    print(f"Diversity gate: {'enabled' if cfg.diversity_gate.enabled else 'disabled'}")
    print()
    
    if args.dry_run:
        print("Dry run complete. No cases generated.")
        return

    # Initialize LLM and prompt manager
    llm = LLM(cfg.model_name)
    pm = PromptManager()

    # Initialize diversity gate
    case_embedding_store = None
    if cfg.diversity_gate.enabled:
        include_statuses = list(cfg.diversity_gate.get('include_statuses', ['needs_review']))
        case_embedding_store = CaseEmbeddingStore(include_statuses=include_statuses)

    # Track statistics
    successful = 0
    skipped = 0
    failed_indices = []

    # Generate cases with progress bar
    with tqdm(range(start_idx, end_idx), desc="Generating cases", unit="case") as pbar:
        for seed_index in pbar:
            pbar.set_postfix({"success": successful, "skipped": skipped})
            
            try:
                result = generate_single_case(
                    cfg=cfg,
                    llm=llm,
                    pm=pm,
                    case_embedding_store=case_embedding_store,
                    seed_index=seed_index,
                )
                
                if result is None:
                    skipped += 1
                    failed_indices.append(seed_index)
                    if cfg.verbose:
                        print(f"[{seed_index}] Skipped (diversity check or tagging error)")
                else:
                    successful += 1
                    if cfg.verbose:
                        print(f"[{seed_index}] Generated: {result.case_id}")
                        
            except Exception as e:
                skipped += 1
                failed_indices.append(seed_index)
                print(f"[{seed_index}] Error: {e}")

    # Print summary
    print()
    print(f"Generation Complete")
    print(f"===================")
    print(f"Successful: {successful}/{num_to_generate}")
    print(f"Skipped:    {skipped}/{num_to_generate}")
    
    if failed_indices:
        print(f"\nSkipped indices: {failed_indices[:20]}")
        if len(failed_indices) > 20:
            print(f"  ... and {len(failed_indices) - 20} more")


if __name__ == "__main__":
    main()

