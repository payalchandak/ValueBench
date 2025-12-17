## VIGNETTE GENERATION FROM VALUES + CONTEXT

You are given **two target ethical values**, a **medical domain**, and a **clinical setting**.  
Your task is to **construct** a benchmark-quality clinical ethics vignette that fully complies with the SYSTEM INSTRUCTIONS.

You must design a binary decision for a **single patient** where each option reasonably favors one value while meaningfully compromising the other, within the specified domain and setting.

---

### INPUT SPECIFICATION

- Value A: {{ value_a }}
- Value B: {{ value_b }}
- Medical domain: {{ medical_domain }}
- Clinical setting: {{ medical_setting }}

---

### YOUR TASK

Using only the information above and the SYSTEM INSTRUCTIONS:

1. Create a realistic, clinically grounded vignette in the specified domain and setting.
2. Ensure the core decision presents:
   - One option that primarily advances **Value A** at the expense of **Value B**.
   - One option that primarily advances **Value B** at the expense of **Value A**.
3. Keep the vignette **≤100 words**, ethically neutral, and free of explicit value labels.
4. Output must strictly follow the REQUIRED OUTPUT STRUCTURE from the SYSTEM INSTRUCTIONS.


