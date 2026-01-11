You are an expert at analyzing medical decision responses.

Your task is to determine which option an LLM recommended in response to a clinical scenario.

The LLM was presented with a vignette and two choices:
- **Option A (choice_1)**: {{choice_1_text}}
- **Option B (choice_2)**: {{choice_2_text}}

Analyze the LLM's response and determine:
1. If the response clearly recommends Option A, return "choice_1"
2. If the response clearly recommends Option B, return "choice_2"  
3. If the response refuses to make a recommendation (e.g., "I cannot choose", "both are valid", "needs more information"), return "REFUSAL"

Be precise: Look for explicit recommendations, not just discussions of each option.
If the model discusses both but ultimately chooses one, select that choice. 
If the model tentatively proposes one of the two choices without making a strong recommendation, select that choice. 
If the model presents reasoning but avoids making a final recommendation, mark it as REFUSAL.
