from pydantic import BaseModel
from all_the_llms import LLM
from dotenv import load_dotenv
from prompt_manager import PromptManager

load_dotenv()

class CodeReview(BaseModel):
    review: str

class ImprovedCode(BaseModel):
    code: str

llm = LLM("gpt-4o")
pm = PromptManager()

# Initial code to improve
code_snippet = "def login(user, pass):\n    print(pass)\n    return True"
focus_areas = ["Security Risks", "Python Standards"]

print("=" * 60)
print("SELF-IMPROVEMENT LOOP")
print("=" * 60)
print(f"\n📝 INITIAL CODE:\n{code_snippet}\n")

# Run 5 iterations of review -> improve
for i in range(5):
    print(f"\n{'='*60}")
    print(f"🔄 ITERATION {i + 1}")
    print("=" * 60)
    
    # Step 1: Get code review
    review_prompt = pm.build("workflows/code_review", {
        "code_snippet": code_snippet,
        "focus_areas": focus_areas
    })
    review_result = llm.structured_completion(
        messages=review_prompt["messages"],
        response_model=CodeReview,
    )
    print(f"\n📋 REVIEW:\n{review_result.review}")
    
    # Step 2: Improve code based on review
    improve_prompt = pm.build("workflows/code_improve", {
        "code_snippet": code_snippet,
        "review": review_result.review
    })
    improved_result = llm.structured_completion(
        messages=improve_prompt["messages"],
        response_model=ImprovedCode,
    )
    
    # Update code for next iteration
    code_snippet = improved_result.code
    print(f"\n✨ IMPROVED CODE:\n{code_snippet}")

print(f"\n{'='*60}")
print("🏁 FINAL RESULT")
print("=" * 60)
print(f"\n{code_snippet}")
