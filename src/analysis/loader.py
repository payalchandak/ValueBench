"""Data loading utilities for LLM decision analysis."""

import json
from pathlib import Path

from src.human_decisions.models import ParticipantRegistry
from src.llm_decisions.models import DecisionRecord

# Default path to LLM decisions data
DEFAULT_LLM_DECISIONS_DIR = Path(__file__).parent.parent.parent / "data" / "llm_decisions"

# Default path to human decisions data
DEFAULT_HUMAN_DECISIONS_DIR = Path(__file__).parent.parent.parent / "data" / "human_decisions"


def load_llm_decisions(
    data_dir: str | Path = DEFAULT_LLM_DECISIONS_DIR,
) -> list[DecisionRecord]:
    """Load all LLM decision records from JSON files.
    
    Reads all JSON files from the specified directory and parses them
    into DecisionRecord objects.
    
    Args:
        data_dir: Directory containing LLM decision JSON files. Defaults to
            data/llm_decisions/ relative to the project root.
    
    Returns:
        List of DecisionRecord objects, one per case.
    
    Raises:
        FileNotFoundError: If the data directory does not exist.
        ValueError: If a JSON file cannot be parsed as a DecisionRecord.
    
    Example:
        >>> decisions = load_llm_decisions()
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


def load_human_decisions(
    data_dir: str | Path = DEFAULT_HUMAN_DECISIONS_DIR,
) -> list[DecisionRecord]:
    """Load all human decision records from JSON files.
    
    Reads all JSON files from the specified directory (excluding
    participant_registry.json) and parses them into DecisionRecord objects.
    Human decisions use the same schema as LLM decisions, with humans
    appearing in the models dict as 'human/participant_{hash[:8]}'.
    
    Args:
        data_dir: Directory containing human decision JSON files. Defaults to
            data/human_decisions/ relative to the project root.
    
    Returns:
        List of DecisionRecord objects, one per case.
    
    Raises:
        FileNotFoundError: If the data directory does not exist.
        ValueError: If a JSON file cannot be parsed as a DecisionRecord.
    
    Example:
        >>> decisions = load_human_decisions()
        >>> for record in decisions:
        ...     human_models = [m for m in record.models if m.startswith("human/")]
        ...     print(f"Case {record.case_id}: {len(human_models)} human respondents")
    """
    data_dir = Path(data_dir)
    
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Path is not a directory: {data_dir}")
    
    decisions: list[DecisionRecord] = []
    json_files = sorted(data_dir.glob("*.json"))
    
    for json_path in json_files:
        # Skip the participant registry file
        if json_path.name == "participant_registry.json":
            continue
            
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


def load_participant_registry(
    path: str | Path | None = None,
) -> ParticipantRegistry:
    """Load the participant registry from JSON.
    
    The participant registry contains metadata about all survey participants,
    including their anonymous ID, name, email, expertise, and timestamps.
    
    Args:
        path: Path to the registry JSON file. Defaults to
            data/human_decisions/participant_registry.json
    
    Returns:
        ParticipantRegistry object. Returns an empty registry if the file
        doesn't exist.
    
    Example:
        >>> registry = load_participant_registry()
        >>> len(registry)  # Number of participants
        42
        >>> info = registry.get("participant_a3f8c2d1")
        >>> info.name
        'Dr. Jane Smith'
    """
    return ParticipantRegistry.load(path)


def load_all_decisions(
    llm_dir: str | Path = DEFAULT_LLM_DECISIONS_DIR,
    human_dir: str | Path = DEFAULT_HUMAN_DECISIONS_DIR,
) -> list[DecisionRecord]:
    """Load and merge all LLM and human decision records.
    
    This unified loader combines decisions from both LLM evaluations and human
    survey responses. For each case that appears in either source, the models
    dicts are merged into a single DecisionRecord.
    
    LLM models appear in the models dict as 'openai/gpt-4o', 'anthropic/claude-3',
    etc. Human participants appear as 'human/participant_{hash[:8]}'.
    
    Args:
        llm_dir: Directory containing LLM decision JSON files. Defaults to
            data/llm_decisions/ relative to the project root.
        human_dir: Directory containing human decision JSON files. Defaults to
            data/human_decisions/ relative to the project root.
    
    Returns:
        List of DecisionRecord objects with merged models from both sources.
        Cases that only exist in one source are included with only that
        source's models.
    
    Raises:
        FileNotFoundError: If a specified directory does not exist.
        ValueError: If a JSON file cannot be parsed, or if the same model
            key appears in both LLM and human data for a case.
    
    Example:
        >>> decisions = load_all_decisions()
        >>> for record in decisions:
        ...     llm_models = [m for m in record.models if not m.startswith("human/")]
        ...     human_models = [m for m in record.models if m.startswith("human/")]
        ...     print(f"Case {record.case_id}: {len(llm_models)} LLMs, {len(human_models)} humans")
    """
    # Load from both sources, handling missing directories gracefully
    llm_dir = Path(llm_dir)
    human_dir = Path(human_dir)
    
    llm_records: list[DecisionRecord] = []
    human_records: list[DecisionRecord] = []
    
    if llm_dir.exists() and llm_dir.is_dir():
        llm_records = load_llm_decisions(llm_dir)
    
    if human_dir.exists() and human_dir.is_dir():
        # Check if there are any case files (not just the registry)
        case_files = [f for f in human_dir.glob("*.json") if f.name != "participant_registry.json"]
        if case_files:
            human_records = load_human_decisions(human_dir)
    
    # Index by case_id for merging
    llm_by_case: dict[str, DecisionRecord] = {r.case_id: r for r in llm_records}
    human_by_case: dict[str, DecisionRecord] = {r.case_id: r for r in human_records}
    
    # Get all unique case IDs
    all_case_ids = set(llm_by_case.keys()) | set(human_by_case.keys())
    
    merged_records: list[DecisionRecord] = []
    
    for case_id in sorted(all_case_ids):
        llm_record = llm_by_case.get(case_id)
        human_record = human_by_case.get(case_id)
        
        if llm_record and human_record:
            # Merge models from both sources
            merged_models = dict(llm_record.models)
            
            # Check for overlapping keys (shouldn't happen with proper prefixing)
            overlap = set(merged_models.keys()) & set(human_record.models.keys())
            if overlap:
                raise ValueError(
                    f"Case {case_id} has overlapping model keys in LLM and human data: {overlap}"
                )
            
            merged_models.update(human_record.models)
            
            # Use the LLM record's case definition as the base
            merged_record = DecisionRecord(
                case_id=case_id,
                case=llm_record.case,
                models=merged_models,
            )
            merged_records.append(merged_record)
        elif llm_record:
            merged_records.append(llm_record)
        else:
            # Only human record exists
            merged_records.append(human_record)  # type: ignore
    
    return merged_records
