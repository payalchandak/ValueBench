#!/usr/bin/env python3
"""
Quick start script for the ValueBench case viewer
"""

import subprocess
import sys
from pathlib import Path

def main():
    # Viewer directory and project root
    viewer_dir = Path(__file__).parent
    project_root = viewer_dir.parent
    
    print("=" * 60)
    print("ValueBench Case Viewer")
    print("=" * 60)
    print()
    print("Starting web server...")
    print()
    print("Once started, open your browser to:")
    print("  → http://localhost:5001")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    try:
        subprocess.run(
            ["uv", "run", "python", "-m", "viewer.app"],
            cwd=project_root,
            check=True
        )
    except KeyboardInterrupt:
        print("\n\nShutting down viewer...")
        sys.exit(0)
    except subprocess.CalledProcessError as e:
        print(f"\nError running viewer: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

