# WB-Ready: Universal NVIDIA AI Workbench Repository Converter

A Streamlit app that converts any GitHub repository into an NVIDIA AI Workbench-ready project by analyzing its dependencies and generating all required `.project/` configuration files.

## What it does

1. **Analyzes** a GitHub repo: detects languages, frameworks, Python/Node deps, GPU requirements, and entry points
2. **Generates** Workbench config: `spec.yaml`, `apt.txt`, `requirements.txt`, `postBuild.bash`
3. **Forks** the repo to your account, adds the config, and pushes — original repo stays untouched

## Running in NVIDIA AI Workbench

Clone this project into Workbench. The **WB-Ready Converter** app launches automatically via the apps panel (Streamlit on port 8501).

## Running locally

```bash
pip install -r requirements.txt
cd code
streamlit run src/main.py
```

## Requirements

- Python 3.10+
- GitHub personal access token with `repo` scope

## Supported detection

| Category | What's detected |
|----------|----------------|
| Languages | Python, JavaScript/TypeScript, Go, Rust, Java, C++, Ruby |
| Frameworks | Streamlit, Flask, FastAPI, Django, Gradio, PyTorch, TensorFlow, Jupyter |
| Dependencies | requirements.txt, pyproject.toml, package.json |
| GPU | torch, tensorflow, jax, cupy, rapids, numba, onnxruntime-gpu |
| Entry points | main.py, app.py, run.py, server.py, api.py, manage.py |

## Generated files

| File | Purpose |
|------|---------|
| `.project/spec.yaml` | Workbench project specification (v2 format) |
| `.project/apt.txt` | System packages to install |
| `.project/requirements.txt` | Python packages to install |
| `.project/postBuild.bash` | Setup script that runs after container build |

## Project structure

```
wb-ready/
├── .project/
│   ├── spec.yaml          # This project's Workbench config
│   ├── apt.txt
│   ├── requirements.txt
│   └── postBuild.bash
├── code/
│   └── src/
│       ├── main.py                 # Streamlit UI
│       ├── github_client.py        # Clone, fork, push via GitHub API
│       ├── repository_analyzer.py  # Detect languages/frameworks/deps
│       └── config_generator.py     # Generate Workbench config files
├── data/                  # Runtime data (gitignored)
├── models/                # Model files (Git LFS)
├── requirements.txt       # Python deps
└── apt.txt               # System deps
```
