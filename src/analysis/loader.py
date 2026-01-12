"""Data loading utilities for LLM decision analysis."""

import json
from pathlib import Path

from src.llm_decisions.models import DecisionRecord

# Default path to LLM decisions data
DEFAULT_DECISIONS_DIR = Path(__file__).parent.parent.parent / "data" / "llm_decisions"


def load_decisions(
    data_dir: str | Path = DEFAULT_DECISIONS_DIR,
) -> list[DecisionRecord]:
    """Load all LLM decision records from JSON files.
    
    Reads all JSON files from the specified directory and parses them
    into DecisionRecord objects.
    
    Args:
        data_dir: Directory containing decision JSON files. Defaults to
            data/llm_decisions/ relative to the project root.
    
    Returns:
        List of DecisionRecord objects, one per case.
    
    Raises:
        FileNotFoundError: If the data directory does not exist.
        ValueError: If a JSON file cannot be parsed as a DecisionRecord.
    
    Example:
        >>> decisions = load_decisions()
        >>> len(decisions) > 0
        True
        >>> decisions[0].case_id  # UUID string
        '065d7abf-...'
    """
    data_dir = Path(data_dir)
    
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Path is not a directory: {data_dir}")
    
    decisions: list[DecisionRecord] = []
    json_files = sorted(data_dir.glob("*.json"))
    
    for json_path in json_files:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        try:
            record = DecisionRecord.model_validate(data)
            decisions.append(record)
        except Exception as e:
            raise ValueError(
                f"Failed to parse {json_path.name} as DecisionRecord: {e}"
            ) from e
    
    return decisions
