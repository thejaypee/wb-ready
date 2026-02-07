# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

WB-Ready is a Streamlit application that converts any GitHub repository into an NVIDIA AI Workbench-ready project. It analyzes a repo's dependencies and generates the `.project/` configuration files that Workbench requires.

## Architecture

The app has three core modules under `code/src/`:

- **repository_analyzer.py** — Clones a repo and scans it to detect languages, frameworks (Streamlit/Flask/FastAPI/Gradio/PyTorch/TensorFlow), Python and Node dependencies, GPU requirements, and application entry points.
- **config_generator.py** — Takes analysis results and produces Workbench config files: `spec.yaml` (v2 format), `apt.txt`, `requirements.txt`, and `postBuild.bash`.
- **github_client.py** — Handles GitHub API operations: fetching repo metadata, cloning (with token injection for private repos), forking to the user's account, and committing/pushing changes.
- **main.py** — Streamlit UI that wires the three modules together in a 4-step workflow (analyze → review → configure → convert & push).

## NVIDIA AI Workbench spec.yaml format

The generated spec.yaml must follow `specVersion: v2`. Key rules:
- `meta.labels` must be a YAML list `[]`, never a dict
- `layout` entries need `path`, `type` (code/data/models), and `storage` (git/gitlfs/gitignore)
- `environment.base.labels` must be a list
- Apps in `execution.apps` need `start_command`, `health_check_command`, `webapp_options` with port
- The reference implementation is in the sibling project `NVIDIA-workbench-example-downloadable-nim/.project/spec.yaml`

## Commands

```bash
# Install deps
pip install -r requirements.txt

# Run the app (from project root)
cd code && streamlit run src/main.py

# Run inside Workbench container
cd /project/code && python -m streamlit run src/main.py --server.port=8501 --server.address=0.0.0.0
```

## Import structure

`main.py` adds `code/` to `sys.path`, then imports via `from src.module import ...`. This works both when running from the `code/` directory directly and when Workbench launches from `/project/code`.
