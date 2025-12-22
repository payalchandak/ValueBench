#!/usr/bin/env python3
"""
HuggingFace Spaces Entry Point

This file is used when deploying to HuggingFace Spaces.
It imports and launches the GUI application.
"""

from src.gui import create_interface
from src.gui.app import CustomTheme

# Create and launch the interface
demo = create_interface()

# For HuggingFace Spaces, Gradio will automatically detect and launch this
if __name__ == "__main__":
    theme = CustomTheme()
    demo.launch(theme=theme)

