from all_the_llms import LLM
from dotenv import load_dotenv
from prompt_manager import PromptManager
from case_models import DraftCase, BenchmarkCandidate
from rubric_models import ClinicalRubric, EthicalRubric, StylisticRubric
from utils import *
load_dotenv()
llm = LLM("claude-sonnet-4.5")
pm = PromptManager()

with open("seed.txt", "r") as f:
    seed_text = f.read().strip()

draft_prompt = pm.build_messages("workflows/seed_draft", {
    "seed": seed_text
})
draft = llm.structured_completion(
    messages=draft_prompt,
    response_model=DraftCase,
)
pretty_print_case(draft)

# todo: embedding based diversity gate 

for i in range(2): 

    clinical_rubric_prompt = pm.build_messages("workflows/rubric", {
        "role_name": "Senior Attending Physician and Medical Director",
        "rubric_criteria": format_criteria(ClinicalRubric),
        "vignette": draft.vignette,
        "choice_1": draft.choice_1,
        "choice_2": draft.choice_2,
    })
    clinical_rubric = llm.structured_completion(
        messages=clinical_rubric_prompt,
        response_model=ClinicalRubric,
    )
    print(f"Passing: {clinical_rubric.overall_pass}")
    pretty_print_audit(clinical_rubric, "Clinical")

    ethical_rubric_prompt = pm.build_messages("workflows/rubric", {
        "role_name": "Medical Ethics Professor specializing in principlist values",
        "rubric_criteria": format_criteria(EthicalRubric),
        "vignette": draft.vignette,
        "choice_1": draft.choice_1,
        "choice_2": draft.choice_2,
    })
    ethical_rubric = llm.structured_completion(
        messages=ethical_rubric_prompt,
        response_model=EthicalRubric,
    )
    print(f"Passing: {ethical_rubric.overall_pass}")

    stylistic_rubric_prompt = pm.build_messages("workflows/rubric", {
        "role_name": "Senior Medical Editor",
        "rubric_criteria": format_criteria(StylisticRubric),
        "vignette": draft.vignette,
        "choice_1": draft.choice_1,
        "choice_2": draft.choice_2,
    })
    stylistic_rubric = llm.structured_completion(
        messages=stylistic_rubric_prompt,
        response_model=StylisticRubric,
    )
    print(f"Passing: {stylistic_rubric.overall_pass}")  
    
    clinical_feedback = clinical_rubric.all_suggested_changes if not clinical_rubric.overall_pass else "No issues detected."
    ethical_feedback = ethical_rubric.all_suggested_changes if not ethical_rubric.overall_pass else "No issues detected."
    stylistic_feedback = stylistic_rubric.all_suggested_changes if not stylistic_rubric.overall_pass else "No issues detected."

    refine_prompt = pm.build_messages(
        "workflows/refine",
        {
            "old_vignette": draft.vignette,
            "old_choice_1": draft.choice_1,
            "old_choice_2": draft.choice_2,
            "clinical_feedback": clinical_feedback,
            "ethical_feedback": ethical_feedback,
            "style_feedback": stylistic_feedback
        }
    )
    refined = llm.structured_completion(
        messages=refine_prompt,
        response_model=DraftCase
    )

    pretty_print_case(refined)

    draft = refined





import ipdb; ipdb.set_trace()

print(draft)