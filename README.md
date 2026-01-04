# ValueBench

A medical ethics case generation and evaluation system that creates, refines, and validates synthetic ethical dilemmas for training and benchmarking purposes.

## Overview

ValueBench is a modular system for:
- **Generating** medical ethics cases with complex value conflicts
- **Tagging** cases with ethical principle alignments (autonomy, beneficence, nonmaleficence, justice)
- **Reviewing** cases through Google Sheets collaboration
- **Visualizing** cases and their relationships through embeddings

The system uses LLMs to generate realistic medical vignettes with two ethically challenging choices, then tags how each choice aligns with established bioethics principles.

## How Value Tagging Works

Cases are tagged with ethical principle alignments and validated to ensure genuine dilemmas with no obvious answers. See **[Value Validation Rules](docs/value_validation.md)** for details.

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
```

That's it! No need to manually activate environments. `uv run` handles everything automatically.

## Workflow Overview

ValueBench follows a **Generate → Export → Review → Import** workflow:

1. **Generate Cases** - Create new ethics cases using LLMs
2. **Export to Sheets** - Push cases to Google Sheets for collaborative review
3. **Review in Sheets** - Reviewers evaluate cases directly in the spreadsheet
4. **Import from Sheets** - Pull reviewed cases back with feedback attached

## Generating New Cases 

**Note: This requires API keys.**

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

## Google Sheets Review Workflow

Cases are reviewed collaboratively in Google Sheets. This requires one-time setup of Google Cloud credentials.

### Initial Setup (One Time)

1. **Create a Google Cloud Project** with Sheets API enabled
2. **Create a Service Account** and download the credentials JSON
3. **Save credentials** to `credentials/service_account.json`
4. **Create a Google Sheet** and share it with your service account email
5. **Configure** `src/sheets/sheets_config.yaml` with your spreadsheet ID

Verify setup:
```bash
uv run python -m src.sheets.verify_setup
```

### Export Cases to Sheets

Push cases to Google Sheets for review:

```bash
# Export all cases (replaces sheet content)
uv run python -m src.sheets.export_to_sheets

# Preview without writing
uv run python -m src.sheets.export_to_sheets --dry-run

# Add only new cases (preserves existing)
uv run python -m src.sheets.export_to_sheets --append
```

### Reviewing in Google Sheets

Once cases are exported, reviewers can:

1. **Open the shared Google Sheet**
2. **Review each case** - Read the vignette and both choices
3. **Verify value tags** - Check if autonomy/beneficence/nonmaleficence/justice alignments are correct
4. **Add reviewer info** - Fill in R1/R2 name and decision columns
5. **Add comments** - Provide feedback in the Reviewer Comments column

### Import Reviewed Cases

Pull reviewed cases back with feedback:

```bash
# Import all valid cases
uv run python -m src.sheets.import_from_sheets

# Preview what would be imported
uv run python -m src.sheets.import_from_sheets --dry-run

# Validate only (don't import)
uv run python -m src.sheets.import_from_sheets --validate-only

# Import even if validation warnings exist
uv run python -m src.sheets.import_from_sheets --force
```

The import process:
- Validates all cases against the schema
- Writes validation results back to the sheet
- Creates new refinement iterations with reviewer feedback
- Detects duplicate imports (skips unchanged cases)

## Browsing Cases (Viewer)

ValueBench includes a web-based viewer for browsing cases and exploring relationships.

### Start the Viewer

```bash
uv run python -m viewer.start_viewer
```

Then open http://localhost:5000 in your browser.

### Viewer Features

- **Case List** - Browse all generated cases with status indicators
- **Case Detail** - View full case content including:
  - Vignette and choices
  - Value alignments for each choice
  - Refinement history
  - Reviewer feedback (imported from Sheets)
- **Case Embeddings** - Visualize case similarity using PCA/t-SNE
- **Similar Cases** - Find cases with similar ethical dilemmas
