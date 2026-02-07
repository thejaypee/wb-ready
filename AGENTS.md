# AGENTS.md - Development Guide for Agentic Coding Agents

This file provides essential information for agentic coding agents working with this NVIDIA AI Workbench repository converter project.

## Project Overview

This is a Streamlit application that converts GitHub repositories into NVIDIA AI Workbench-ready projects by analyzing dependencies and generating configuration files.

Key components:
- `code/src/main.py` - Streamlit UI implementing the 4-step workflow
- `code/src/repository_analyzer.py` - Analyzes repos for languages, frameworks, dependencies
- `code/src/config_generator.py` - Generates Workbench config files (spec.yaml, apt.txt, etc.)
- `code/src/github_client.py` - Handles GitHub API operations

## Build/Lint/Test Commands

### Installation
```bash
pip install -r requirements.txt
```

### Running the Application
```bash
# From project root
cd code && streamlit run src/main.py

# Inside Workbench container
cd /project/code && python -m streamlit run src/main.py --server.port=8501 --server.address=0.0.0.0
```

### Testing
This project currently doesn't have unit tests. To manually test functionality:
1. Run the application locally
2. Enter a GitHub repository URL to analyze
3. Verify the analysis results
4. Check the generated configuration files
5. Test the "Convert & Push" functionality with a test repository

To test individual modules:
```bash
# Test repository analysis
cd code
python -c "from src.repository_analyzer import RepositoryAnalyzer; print(RepositoryAnalyzer('/path/to/test/repo').analyze())"

# Test config generation
cd code
python -c "from src.config_generator import ConfigGenerator; print(ConfigGenerator.generate_spec_yaml('test-project', 'Test desc', analysis_result))"
```

### Linting
This project does not currently have configured linting tools. When adding linting:

```bash
# Example if flake8 was added:
flake8 code/

# Example if black was added:
black --check code/
```

### Type Checking
This project does not currently have configured type checking. When adding type checking:

```bash
# Example if mypy was added:
mypy code/
```

## Code Style Guidelines

### Imports
1. Standard library imports first, then third-party, then local imports
2. Use absolute imports with `src.` prefix when importing from project modules
3. Group imports logically with a blank line between groups
4. Avoid wildcard imports (`from module import *`)

Example:
```python
import os
import sys
from pathlib import Path

import streamlit as st
import yaml

from src.github_client import GitHubClient
from src.repository_analyzer import RepositoryAnalyzer
```

### Formatting
1. Follow PEP 8 style guide
2. Use 4 spaces for indentation (no tabs)
3. Maximum line length of 88 characters (recommended for compatibility with Black)
4. Use double quotes for strings unless single quotes are needed to avoid escaping
5. Place trailing commas in multiline constructs

### Naming Conventions
1. Variables and functions: `snake_case`
2. Classes: `PascalCase`
3. Constants: `UPPER_SNAKE_CASE`
4. Private members: prefixed with underscore `_private_variable`
5. Use descriptive names that convey purpose

### Types
1. Use type hints for function parameters and return values
2. Prefer built-in types when possible
3. Use `typing` module for complex types (Union, Optional, etc.)

Example:
```python
from typing import List, Dict, Optional

def analyze_repository(repo_path: str) -> AnalysisResult:
    pass

def generate_spec(project_name: str, description: str, analysis: AnalysisResult) -> str:
    pass
```

### Error Handling
1. Use specific exception types rather than generic `except:` clauses
2. Include meaningful error messages
3. Log errors appropriately for debugging
4. Gracefully handle expected errors (e.g., network issues, missing files)
5. Use try/except blocks around external API calls

Example:
```python
try:
    client = GitHubClient(token)
    repo_info = client.get_repository_info(repo_url)
except ValueError as e:
    st.error(f"Invalid repository: {e}")
    return
except Exception as e:
    st.error(f"Unexpected error: {e}")
    return
```

### Documentation
1. Use docstrings for all public modules, classes, and functions
2. Follow Google Python Style Guide for docstrings
3. Include type information in docstrings when not using type hints
4. Comment complex logic and non-obvious implementations

### Data Classes
1. Use `@dataclass` for simple data containers
2. Define default values appropriately
3. Use `field(default_factory=list)` for mutable defaults

### Streamlit Best Practices
1. Use `st.session_state` for persistent data across reruns
2. Structure UI with headers, dividers, and columns for clarity
3. Provide helpful placeholder text and tooltips
4. Use appropriate widget types (buttons for actions, inputs for data)
5. Handle loading states with `st.spinner()` and progress indicators

### Git Operations
1. Always handle `git.GitCommandError` exceptions
2. Clean up temporary directories with `shutil.rmtree()`
3. Use shallow clones (`depth=1`) when full history isn't needed
4. Properly inject tokens for private repository access

### YAML Generation
1. Use `yaml.dump()` with `sort_keys=False` to preserve order
2. Validate generated YAML conforms to Workbench spec requirements
3. Use appropriate data structures (lists vs dictionaries) as required by the spec

### Workbench Specification Compliance
1. Ensure `spec.yaml` follows v2 format
2. Use correct `layout` entries with proper `path`, `type`, and `storage` values
3. Maintain required fields in `environment.base` and `execution.apps`
4. Follow naming conventions for apps and labels

## Project-Specific Conventions

### AnalysisResult Class
The `AnalysisResult` dataclass in `repository_analyzer.py` is central to the application. When modifying:
1. Maintain backward compatibility
2. Use appropriate default values
3. Keep field names consistent with their purpose

### Configuration Generation
When modifying `config_generator.py`:
1. Ensure all generated files match Workbench expectations
2. Maintain consistency in port assignments and health checks
3. Update base images appropriately for different frameworks

### GitHub Client
When working with `github_client.py`:
1. Always handle authentication properly
2. Implement appropriate retry logic for API calls
3. Clean up temporary repositories and forks
4. Respect GitHub rate limits

## Dependencies
Core dependencies are listed in `requirements.txt`:
- streamlit: UI framework
- pygithub: GitHub API client
- gitpython: Git operations
- pyyaml: YAML processing
- requests: HTTP requests

When adding new dependencies:
1. Pin major.minor versions for stability
2. Update requirements.txt
3. Consider impact on Workbench container build times
4. Verify compatibility with Python 3.10+

## File Structure
```
wb-ready/
├── code/
│   └── src/
│       ├── main.py              # Streamlit UI
│       ├── github_client.py     # GitHub operations
│       ├── repository_analyzer.py # Repo analysis
│       └── config_generator.py  # Config generation
├── .project/                    # Workbench config for this project
│   ├── spec.yaml
│   ├── apt.txt
│   ├── requirements.txt
│   └── postBuild.bash
└── requirements.txt             # Project dependencies
```

Always maintain this structure and ensure imports work correctly both locally and in Workbench.