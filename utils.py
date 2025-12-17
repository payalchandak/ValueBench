from pydantic import BaseModel
from typing import Type, Optional
import textwrap

def format_criteria(model: Type[BaseModel]) -> str:
    """
    Converts a Pydantic model's fields into a clean Markdown checklist.
    """
    lines = []
    # In Pydantic V2, we access .model_fields
    for name, field_info in model.model_fields.items():
        # Skip internal helper fields if strictly needed, 
        # but usually we just want everything defined in the Rubric
        if field_info.description:
            lines.append(f"- **{name}**: {field_info.description}")
            
    return "\n".join(lines)

def pretty_print_case(case, title: str = "DRAFT CASE"):
    """
    Prints a formatted, readable view of a DraftCase.
    """
    # 1. Define visual separators
    thick_line = "=" * 60
    thin_line = "-" * 60
    
    # 2. Handle field naming variations (choice_1 vs choice1)
    # This makes the util robust if you change your Pydantic model later
    c1 = getattr(case, "choice_1", getattr(case, "choice1", "N/A"))
    c2 = getattr(case, "choice_2", getattr(case, "choice2", "N/A"))
    
    print(f"\n{thick_line}")
    print(f" {title.upper()} ".center(60, "="))
    print(f"{thick_line}\n")
    
    # 3. Print Vignette (wrapped to 80 chars for readability)
    print("VIGNETTE:")
    print(textwrap.fill(case.vignette, width=80))
    
    print(f"\n{thin_line}")
    print(" DECISION MATRIX ".center(60))
    print(f"{thin_line}\n")
    
    # 4. Print Choices
    print(f" [A] {c1}")
    print(f" [B] {c2}")
    
    print(f"\n{thick_line}\n")


def pretty_print_audit(rubric, agent_name: str):
    """
    Prints a scorecard style summary of a specific agent's critique.
    """
    pass_icon = "✅" if rubric.overall_pass else "❌"
    
    print(f"\n--- {agent_name} Report {pass_icon} ---")
    
    if rubric.overall_pass:
        print("Result: PASSED")
    else:
        print(f"Result: FAILED ({rubric.num_failing} issues)")
        print("\nCRITICAL FIXES REQUIRED:")
        
        # Uses the helper method we defined in the RubricBase class earlier
        suggestions = rubric.failing_suggested_changes
        for field, suggestion in suggestions.items():
            print(f"  • {field.upper()}:")
            print(f"    {suggestion}")
    print("----------------------------------\n")

def pretty_print_seed_candidate(value_a, value_b, medical_domain, medical_setting, decision):
    print(
        f"\nSYNTHETIC SEED CANDIDATE → values=({value_a}, {value_b}), "
        f"domain={medical_domain}, setting={medical_setting}"
            )
    print("----------------------------------\n")
    if decision == "continue":
        print("\nFeasibility decision: CONTINUE (proceeding to vignette generation).")
    else:
        print("\nFeasibility decision: START_OVER (resampling seed combination).")
    print("----------------------------------\n")