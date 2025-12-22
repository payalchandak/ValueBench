# ValueBench Case Evaluator - HuggingFace Spaces

This is the HuggingFace Spaces deployment configuration for the ValueBench Case Evaluator GUI.

## Deployment

To deploy this on HuggingFace Spaces:

1. Create a new Space on [HuggingFace Spaces](https://huggingface.co/spaces)
2. Select "Gradio" as the SDK
3. Set the Python version to 3.10 or higher
4. Upload all files from this repository
5. The Space will automatically use `app.py` as the entry point

## Persistent Storage

For persistent storage on HuggingFace Spaces, you can:

1. Use HuggingFace Hub integration to store evaluations
2. Configure persistent storage volumes (if available on your Space tier)
3. Use environment variables to configure storage paths

## Environment Variables

You can set these environment variables in your Space settings:

- `CASES_DIR`: Path to cases directory (default: `data/cases`)
- `EVALUATIONS_DIR`: Path to evaluations directory (default: `data/evaluations`)

## Local Development

To run locally:

```bash
python app.py
```

Or directly from the GUI module:

```bash
python -m src.gui.app
```

The interface will be available at `http://127.0.0.1:7860`

