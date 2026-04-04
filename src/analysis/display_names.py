"""Readable labels for model and participant IDs used in plots and tables."""

from __future__ import annotations

MODEL_DISPLAY_NAMES: dict[str, str] = {
    "anthropic/claude-opus-4.5": "Claude Opus 4.5",
    "deepseek/deepseek-chat": "DeepSeek Chat",
    "google/gemini-3-pro-preview": "Gemini 3 Pro",
    "meta-llama/llama-4-maverick": "Meta Llama 4 Maverick",
    "mistralai/mistral-large-2512": "Mistral AI Large",
    "moonshotai/kimi-k2-thinking": "Moonshot AI Kimi K2",
    "openai/gpt-5.2": "OpenAI GPT 5.2",
    "perplexity/sonar-pro": "Perplexity Sonar Pro",
    "qwen/qwen3-max": "Qwen 3 Max",
    "x-ai/grok-4": "X-AI Grok 4",
    "baidu/ernie-4.5-vl-424b-a47b": "Baidu Ernie 4.5 VL",
    "z-ai/glm-4.6": "Zhipu AI GLM 4.6",
    "human_consensus": "Physician Consensus",
}


def get_display_name(model_id: str) -> str:
    """Return a short human-readable name for a model or participant ID."""
    if model_id in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[model_id]
    short_name = model_id.split("/")[-1]
    if short_name in MODEL_DISPLAY_NAMES:
        return MODEL_DISPLAY_NAMES[short_name]
    if model_id.startswith("human/"):
        parts = short_name.split("_")
        if len(parts) >= 2 and parts[1]:
            return "Physician " + parts[1][:4].upper()
        return short_name
    return short_name
