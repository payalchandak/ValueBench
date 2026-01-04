# ValueBench Case Evaluator GUI

A web-based GUI for evaluating ethical case scenarios with value alignment tracking.

## Features

- **Editable Vignettes**: Directly edit case vignettes before approving
- **Value Alignment Display**: Visual indicators (🟢 promotes, 🔴 violates, ⚪ neutral) for each ethical value
- **Approve/Reject Workflow**: Simple approval or rejection with optional notes
- **LLM Edit Requests**: Request AI-assisted edits (placeholder for future implementation)
- **Progress Tracking**: Real-time progress display and statistics
- **Persistent Storage**: All evaluations are saved locally

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure you have case data in `data/cases/` directory

## Running Locally

You can run the GUI in two ways:

**Option 1: Using the root app.py (recommended for HuggingFace Spaces compatibility)**
```bash
python app.py
```

**Option 2: Using the GUI module directly**
```bash
python -m src.gui.app
```

The interface will be available at `http://127.0.0.1:7860`

## Usage

1. **Initialize Session**: Enter your username (lowercase letters, numbers, hyphens, underscores) and click "Initialize Session"

2. **Review Case**: 
   - Read the vignette (you can edit it directly if needed)
   - Review the two choices with their value alignments
   - Value alignments are shown as:
     - 🟢 Green: Promotes the value
     - 🔴 Red: Violates the value
     - ⚪ Gray: Neutral

3. **Make Decision**:
   - **Approve**: Click "✅ Approve" to approve the case as-is or with your edits
   - **Reject**: Click "❌ Reject" to reject the case (you'll be prompted for a reason)

4. **Request LLM Edits**: (Coming soon) Enter a description of desired edits and click "📝 Request Edit"

5. **Navigation**: Use "⏭️ Next Case" to skip to the next case without making a decision

6. **Statistics**: Click "📊 Statistics" to view your evaluation progress

## Deployment to HuggingFace Spaces

See `README_SPACES.md` for deployment instructions.

## Data Storage

- Cases are stored in `data/cases/` (JSON files)
- Evaluations are stored in `data/evaluations/` (session files)
- Each user has their own session file: `session_{username}.json`

## Notes

- The LLM edit request feature is currently a placeholder and will be implemented in a future version
- All edits to vignettes are saved when you approve a case
- Rejection reasons are optional but recommended for tracking

