title: ValueBench
emoji: ⚕️
colorFrom: red
colorTo: purple
sdk: gradio
sdk_version: 6.2.0
app_file: app.py
pinned: false
---

# ValueBench

A medical ethics case generation and evaluation system that creates, refines, and validates synthetic ethical dilemmas for training and benchmarking purposes.

## Overview

ValueBench is a modular system for:
- **Generating** medical ethics cases with complex value conflicts
- **Tagging** cases with ethical principle alignments (autonomy, beneficence, nonmaleficence, justice)
- **Evaluating** case quality through human review
- **Managing** the full lifecycle from draft to validated benchmark cases

The system uses LLMs to generate realistic medical vignettes with two ethically challenging choices, then tags how each choice aligns with established bioethics principles.

## First-Time Setup

### Install uv

First, install `uv` - a fast Python package manager:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, restart your terminal or run:

```bash
source $HOME/.local/bin/env
```

### Set Up the Project

```bash
# Navigate to the project
cd /path/to/ValueBench

# Fix the python version
uv python pin 3.10

# Install dependencies (creates virtual environment automatically)
uv sync

# Test that everything works
uv run python example_cli.py
```

That's it! No need to manually activate environments. `uv run` handles everything automatically.

## Reviewing Cases (For Evaluators)

**You do NOT need any API keys to review cases.** API keys are only needed for generating new cases.

### Start a Review Session

1. Open your terminal
2. Navigate to the ValueBench folder
3. Run the review tool:

```bash
uv run python example_cli.py
```

### How to Review

1. **Enter your name** when prompted (use lowercase letters only, e.g., `zak` or `becca`)
   - This creates your personal review session that saves your progress

2. **Review each case:**
   - Read the medical vignette (scenario)
   - Review both choices presented
   - See how each choice aligns with four ethical principles:
     - **Autonomy** (patient's right to make their own decisions)
     - **Beneficence** (doing good for the patient)
     - **Nonmaleficence** (avoiding harm)
     - **Justice** (fairness in healthcare)
   
3. **Each principle is rated as:**
   - `promotes` - the choice supports this principle
   - `violates` - the choice conflicts with this principle
   - `neutral` - the choice doesn't significantly affect this principle

4. **Make your decision:**
   - Type `a` and press Enter to **Approve** the case as-is
   - Type `r` and press Enter to **Reject** the case (you'll be asked for a reason)
   - Type `q` and press Enter to **Quit** (your progress is automatically saved)

5. **Provide feedback** (for both approve/reject):
   - Select problem categories if applicable: clinical, ethical, legal, stylistic, other
   - Add detailed comments (required for rejections, optional for approvals)

6. **Your progress is saved automatically** in:
   - Session file: `data/evaluations/sessions/session_<yourname>.json`
   - Individual case evaluations: `data/evaluations/case_evaluations/<yourname>/`

### Tips for Reviewers

- You can quit anytime (press `q`) and resume later - your progress is saved
- The tool shows you how many cases you've reviewed and how many remain
- Take breaks as needed - there's no rush
- If a case seems unrealistic or poorly written, reject it and explain why
- Only completed benchmark candidates (with value tags) are shown for review

### Submitting Your Reviews

After you finish reviewing cases (or at the end of each session), please submit your reviews to GitHub:

```bash
# Add your evaluations 
git add data/

# Commit with a message
git commit -m "Added reviews by <yourname>"

# Push to GitHub
git push
```

**Replace `<yourname>` with your actual username** (e.g., "Added reviews by Gabe").

**Important:** Submit your reviews regularly (ideally after each session) so your work is backed up and shared with the team.

## Generating New Cases 

**Note: This requires API keys and is not needed for case review.**

### Basic Generation

```bash
uv run python -m src.generator
```

### Configuration

Edit `src/config/generator.yaml` to customize:
- Number of cases to generate
- Which workflows to run (seed, refine, tag_values, etc.)
- LLM models to use for each stage
- Generation parameters

### Generation Workflows

Available workflows in `src/prompts/workflows/`:

- **seed_synthetic** - Generate initial cases from scratch
- **seed_literature** - Generate cases from research papers
- **refine** - Improve case quality with expert feedback
- **tag_values** - Assign ethical principle alignments
- **rubric** - Evaluate case quality against rubric
- **clarify_values** - Clarify ambiguous value conflicts
- **improve_values** - Improve value representation

### Prompt Components

Reusable prompt components in `src/prompts/components/`:
- Ethical framework definitions (autonomy, beneficence, etc.)
- Output structure requirements
- Hard constraints and quality checks
- Case display templates
