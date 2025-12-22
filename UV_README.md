# UV Package Management Setup

This project uses [uv](https://github.com/astral-sh/uv) for fast Python package management. UV is a modern Python package installer and resolver written in Rust, offering 10-100x faster performance than pip.

## Installation

### Step 1: Install uv

Choose one of the following methods:

**macOS/Linux (Recommended):**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Using pip (if you already have Python):**
```bash
pip install uv
```

**Using Homebrew (macOS):**
```bash
brew install uv
```

**Using cargo (if you have Rust installed):**
```bash
cargo install uv
```

After installation, restart your terminal or run:
```bash
source $HOME/.cargo/env  # For curl install
```

### Step 2: Verify Installation

Check that uv is installed:
```bash
uv --version
```

## Project Setup

### Option 1: Using uv sync (Recommended)

This is the simplest way to set up the project:

```bash
# Navigate to the project directory
cd /path/to/ValueBench

# Create virtual environment and install all dependencies
uv sync
```

This command will:
- Create a `.venv` virtual environment (if it doesn't exist)
- Install all dependencies from `pyproject.toml`
- Generate a `uv.lock` file for reproducible installs

### Option 2: Using requirements.txt (Backward Compatible)

If you prefer to use the existing `requirements.txt`:

```bash
# Create virtual environment
uv venv

# Activate the virtual environment
source .venv/bin/activate  # On macOS/Linux
# OR
.venv\Scripts\activate     # On Windows

# Install from requirements.txt
uv pip install -r requirements.txt
```

### Option 3: Manual Setup

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On macOS/Linux
.venv\Scripts\activate     # On Windows

# Install the project in editable mode
uv pip install -e .
```

## Usage

### Running Commands

**Run commands directly with uv (no activation needed):**
```bash
# Run the GUI application
uv run python app.py

# Run the CLI example
uv run python example_cli.py

# Run any Python script
uv run python script.py
```

**Or activate the environment manually:**
```bash
source .venv/bin/activate  # On macOS/Linux
.venv\Scripts\activate     # On Windows

# Then run commands normally
python app.py
python example_cli.py
```

### Managing Dependencies

**Add a new dependency:**
```bash
uv add package-name
```

**Add a dependency with version constraint:**
```bash
uv add "package-name>=1.0.0"
```

**Add a development dependency:**
```bash
uv add --dev package-name
```

**Remove a dependency:**
```bash
uv remove package-name
```

**Update all dependencies:**
```bash
uv sync --upgrade
```

**Update a specific package:**
```bash
uv sync --upgrade-package package-name
```

**Sync dependencies (install/update based on pyproject.toml):**
```bash
uv sync
```

### Working with requirements.txt

**Export current dependencies to requirements.txt:**
```bash
uv pip compile pyproject.toml -o requirements.txt
```

**Install from requirements.txt:**
```bash
uv pip install -r requirements.txt
```

## Project Structure

- `pyproject.toml` - Main project configuration and dependencies (for uv)
- `requirements.txt` - Traditional requirements file (maintained for compatibility)
- `uv.lock` - Lock file for reproducible installs (auto-generated, should be committed)

## Benefits of uv

- **Speed**: 10-100x faster than pip
- **Reliability**: Better dependency resolution
- **Reproducibility**: Lock file ensures consistent installs across environments
- **Compatibility**: Works with both `pyproject.toml` and `requirements.txt`
- **No activation needed**: Use `uv run` to execute commands without activating the environment

## Migration from pip/conda

If you're currently using conda or pip:

1. **Install uv** (see Step 1 above)

2. **Set up the project:**
   ```bash
   uv sync
   ```

3. **Run your application:**
   ```bash
   uv run python app.py
   ```

That's it! No need to manually create or activate virtual environments.

## Troubleshooting

### uv command not found

After installation, you may need to:
- Restart your terminal
- Add uv to your PATH manually
- On macOS/Linux: `source $HOME/.cargo/env`

### Virtual environment issues

If you encounter issues with the virtual environment:
```bash
# Remove existing virtual environment
rm -rf .venv

# Recreate it
uv sync
```

### Lock file conflicts

If `uv.lock` has conflicts:
```bash
# Regenerate the lock file
uv lock
```

## Additional Resources

- [uv Documentation](https://docs.astral.sh/uv/)
- [uv GitHub Repository](https://github.com/astral-sh/uv)
- [uv Quick Start Guide](https://docs.astral.sh/uv/getting-started/)

