#!/usr/bin/env python3
"""CLI script to run LLM decision evaluation.

This script evaluates multiple LLMs on approved ethical dilemma cases,
collecting multiple responses per model-case pair with automatic resume support.

Usage:
    # Run evaluation with default config
    uv run python src/run_llm_evaluation.py
    
    # Override config values
    uv run python src/run_llm_evaluation.py execution.runs_per_model=3
    
    # Use explicit case IDs
    uv run python src/run_llm_evaluation.py case_selection.mode=explicit case_selection.case_ids=[case1,case2]
    
    # Change output directory
    uv run python src/run_llm_evaluation.py output.dir=data/my_results

The script uses Hydra for configuration management and is fully resumable - 
if interrupted, running it again will pick up where it left off.
"""

from src.llm_decisions import run_evaluation


if __name__ == "__main__":
    # Hydra handles all CLI argument parsing via decorator
    run_evaluation()
