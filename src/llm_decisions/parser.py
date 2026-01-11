"""Parser for extracting LLM decisions from free-text responses.

This module provides functionality to parse LLM responses and extract which
choice was selected (choice_1, choice_2, or REFUSAL) using GPT-4o-mini with
structured completions.
"""

from all_the_llms import LLM
from src.llm_decisions.models import ParsedDecision
from src.prompt_manager import PromptManager


def parse_response(
    choice_1_text: str,
    choice_2_text: str,
    llm_response: str,
    parser_llm: LLM | None = None,
    prompt_manager: PromptManager | None = None
) -> ParsedDecision:
    """Parse an LLM's free-text response to extract which choice was selected.
    
    Uses GPT-4o-mini with structured completion to reliably extract whether the
    LLM recommended choice_1, choice_2, or refused to make a recommendation.
    
    Args:
        choice_1_text: The text of the first choice (Option A)
        choice_2_text: The text of the second choice (Option B)
        llm_response: The LLM's free-text response to the clinical scenario
        parser_llm: Optional LLM instance for parsing (defaults to GPT-4o-mini if not provided)
        prompt_manager: Optional PromptManager instance (will create one if not provided)
        
    Returns:
        ParsedDecision with selected_choice set to "choice_1", "choice_2", or "REFUSAL"
        
    Example:
        >>> # Simplest usage - creates parser and prompt manager automatically
        >>> result = parse_response(
        ...     choice_1_text="Prioritize patient autonomy",
        ...     choice_2_text="Override patient wishes for safety",
        ...     llm_response="I recommend prioritizing the patient's autonomy..."
        ... )
        >>> result.selected_choice
        'choice_1'
    """
    # Create parser LLM if not provided
    if parser_llm is None:
        parser_llm = LLM("openai/gpt-4o-mini")
    
    # Create PromptManager if not provided
    if prompt_manager is None:
        prompt_manager = PromptManager()
    
    # Build messages using the prompt manager
    messages = prompt_manager.build_messages(
        "workflows/parse_decision",
        {
            "choice_1_text": choice_1_text,
            "choice_2_text": choice_2_text,
            "llm_response": llm_response
        }
    )
    
    # Use structured completion to get reliable extraction
    parsed = parser_llm.structured_completion(
        messages=messages,
        response_model=ParsedDecision
    )
    
    return parsed
