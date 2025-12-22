# ValueBench

Medical ethics case review system.

## First-Time Setup

### Option 1: Using uv (Recommended - Fastest)

This project uses [uv](https://github.com/astral-sh/uv) for package management. See [UV_README.md](UV_README.md) for detailed instructions.

**Quick start:**
```bash
# Install uv (one-time setup)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set up the project
uv sync

# Run the application
uv run python app.py
# OR
uv run python example_cli.py
```

### Option 2: Using Conda (Traditional)

Open your terminal and run these commands:

```bash
# Create a new conda environment named 'hvp'
conda create -n hvp python=3.11 -y

# Activate the environment
conda activate hvp

# Install required packages
pip install -r requirements.txt
```

### Option 3: Using pip + venv

```bash
# Create virtual environment
python -m venv .venv

# Activate the environment
source .venv/bin/activate  # On macOS/Linux
.venv\Scripts\activate      # On Windows

# Install required packages
pip install -r requirements.txt
```

### Verify Installation

```bash
# Make sure you're in the ValueBench directory
cd /path/to/ValueBench

# Test that everything works
python example_cli.py
```

## Reviewing Cases (For Evaluators)

**You do NOT need any API keys to review cases.** API keys are only needed for generating new cases.

### Start a Review Session

1. Open your terminal
2. Navigate to the ValueBench folder
3. Activate the environment and run the review tool:

```bash
conda activate hvp
python example_cli.py
```

### How to Review

1. **Enter your name** when prompted (use lowercase letters only, e.g., `john` or `sarah`)
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
   - Type `e` and press Enter to **Edit** the case before approving
   - Type `r` and press Enter to **Reject** the case (you'll be asked for a reason)
   - Type `q` and press Enter to **Quit** (your progress is automatically saved)

5. **Your progress is saved automatically** in `data/evaluations/session_<yourname>.json`

### Tips for Reviewers

- You can quit anytime (press `q`) and resume later - your progress is saved
- The tool shows you how many cases you've reviewed and how many remain
- Take breaks as needed - there's no rush
- If a case seems unrealistic or poorly written, reject it and explain why

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

```bash
conda activate hvp
python -m src.generator
```

Edit `src/config/generator.yaml` to change generation settings.

