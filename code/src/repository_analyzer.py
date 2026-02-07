"""Analyzes a repository to detect languages, frameworks, dependencies, and entry points."""

import json
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import toml as _toml  # pip install toml
        class tomllib:
            @staticmethod
            def loads(s): return _toml.loads(s)
    except ModuleNotFoundError:
        tomllib = None  # pyproject.toml parsing disabled
from dataclasses import dataclass, field


@dataclass
class AnalysisResult:
    languages: set[str] = field(default_factory=set)
    python_packages: list[str] = field(default_factory=list)
    node_packages: dict[str, str] = field(default_factory=dict)
    system_packages: list[str] = field(default_factory=list)
    has_gpu_requirements: bool = False
    detected_frameworks: set[str] = field(default_factory=set)
    entry_points: list[dict[str, str]] = field(default_factory=list)
    base_image: str = "nvcr.io/nvidia/ai-workbench/python-basic:1.0.2"
    cuda_version: str = ""
    has_dockerfile: bool = False
    has_compose: bool = False


# Frameworks detected by scanning Python source for these strings
FRAMEWORK_MARKERS = {
    "streamlit": ["import streamlit", "from streamlit"],
    "flask": ["from flask import", "Flask(__name__)"],
    "fastapi": ["from fastapi import", "FastAPI("],
    "django": ["django.conf", "DJANGO_SETTINGS_MODULE"],
    "pytorch": ["import torch", "from torch"],
    "tensorflow": ["import tensorflow", "from tensorflow"],
    "gradio": ["import gradio", "from gradio"],
    "jupyter": [".ipynb"],
}

GPU_PACKAGES = {
    "torch", "pytorch", "tensorflow", "tensorflow-gpu",
    "jax", "jaxlib", "cupy", "rapids", "numba",
    "nvidia-cuda", "nvidia-cudnn", "onnxruntime-gpu",
}

LANGUAGE_EXTENSIONS = {
    "python": ["*.py"],
    "javascript": ["*.js", "*.jsx", "*.mjs"],
    "typescript": ["*.ts", "*.tsx"],
    "go": ["*.go"],
    "rust": ["*.rs"],
    "java": ["*.java"],
    "cpp": ["*.cpp", "*.cc", "*.hpp", "*.h"],
    "ruby": ["*.rb"],
}


class RepositoryAnalyzer:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        if not self.repo_path.exists():
            raise ValueError(f"Path does not exist: {repo_path}")

    def analyze(self) -> AnalysisResult:
        result = AnalysisResult()
        result.languages = self._detect_languages()
        result.has_dockerfile = (self.repo_path / "Dockerfile").exists()
        result.has_compose = (
            (self.repo_path / "docker-compose.yml").exists()
            or (self.repo_path / "docker-compose.yaml").exists()
            or (self.repo_path / "compose.yaml").exists()
        )

        if "python" in result.languages:
            result.python_packages = self._parse_python_requirements()
            result.has_gpu_requirements = self._check_gpu(result.python_packages)
            result.detected_frameworks = self._detect_frameworks()
            result.entry_points = self._find_entry_points()

        if "javascript" in result.languages or "typescript" in result.languages:
            result.node_packages = self._parse_node_packages()

        result.system_packages = self._suggest_system_packages(result)
        result.base_image = self._suggest_base_image(result)
        if result.has_gpu_requirements:
            result.cuda_version = "12.3"
        return result

    def _detect_languages(self) -> set[str]:
        languages = set()
        for lang, patterns in LANGUAGE_EXTENSIONS.items():
            for pattern in patterns:
                if any(self.repo_path.rglob(pattern)):
                    languages.add(lang)
                    break
        return languages

    def _parse_python_requirements(self) -> list[str]:
        packages = []
        # requirements.txt
        for req_file in self.repo_path.rglob("requirements*.txt"):
            try:
                for line in req_file.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        packages.append(line)
            except Exception:
                continue

        # pyproject.toml
        pyproject = self.repo_path / "pyproject.toml"
        if pyproject.exists() and tomllib is not None:
            try:
                data = tomllib.loads(pyproject.read_text())
                deps = data.get("project", {}).get("dependencies", [])
                packages.extend(deps)
            except Exception:
                pass

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for pkg in packages:
            name = pkg.lower().split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip()
            if name not in seen:
                seen.add(name)
                unique.append(pkg)
        return unique

    def _parse_node_packages(self) -> dict[str, str]:
        pkg_json = self.repo_path / "package.json"
        if not pkg_json.exists():
            return {}
        try:
            data = json.loads(pkg_json.read_text())
            deps = {}
            deps.update(data.get("dependencies", {}))
            deps.update(data.get("devDependencies", {}))
            return deps
        except Exception:
            return {}

    def _check_gpu(self, packages: list[str]) -> bool:
        for pkg in packages:
            name = pkg.lower().split("==")[0].split(">=")[0].strip()
            if any(g in name for g in GPU_PACKAGES):
                return True
        return False

    def _detect_frameworks(self) -> set[str]:
        frameworks = set()
        for py_file in self.repo_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                for framework, markers in FRAMEWORK_MARKERS.items():
                    if any(marker in content for marker in markers):
                        frameworks.add(framework)
            except Exception:
                continue
        # Check for Jupyter notebooks
        if any(self.repo_path.rglob("*.ipynb")):
            frameworks.add("jupyter")
        return frameworks

    def _find_entry_points(self) -> list[dict[str, str]]:
        entry_points = []
        common_names = [
            "main.py", "app.py", "run.py", "server.py", "api.py",
            "manage.py", "cli.py", "wsgi.py",
        ]
        for name in common_names:
            for fpath in self.repo_path.rglob(name):
                # Skip venv/node_modules
                parts = fpath.parts
                if any(skip in parts for skip in ("venv", ".venv", "node_modules", "__pycache__", ".git")):
                    continue
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                app_type = "python"
                if "streamlit" in content:
                    app_type = "streamlit"
                elif "Flask" in content:
                    app_type = "flask"
                elif "FastAPI" in content:
                    app_type = "fastapi"
                elif "gradio" in content:
                    app_type = "gradio"

                rel_path = fpath.relative_to(self.repo_path)
                entry_points.append({
                    "file": str(rel_path),
                    "type": app_type,
                    "name": fpath.stem.replace("_", " ").title(),
                })
        return entry_points

    def _suggest_system_packages(self, result: AnalysisResult) -> list[str]:
        pkgs = ["git", "git-lfs", "curl", "wget"]
        if "python" in result.languages:
            pkgs.extend(["build-essential", "python3-dev"])
        if "cpp" in result.languages:
            pkgs.extend(["cmake", "g++"])
        if "go" in result.languages:
            pkgs.append("golang")
        if "rust" in result.languages:
            pkgs.append("rustc")
        if result.has_gpu_requirements:
            pkgs.append("nvidia-cuda-toolkit")
        return sorted(set(pkgs))

    def _suggest_base_image(self, result: AnalysisResult) -> str:
        if "pytorch" in result.detected_frameworks:
            return "nvcr.io/nvidia/pytorch:24.01-py3"
        if "tensorflow" in result.detected_frameworks:
            return "nvcr.io/nvidia/tensorflow:24.01-tf2-py3"
        if result.has_gpu_requirements:
            return "nvcr.io/nvidia/cuda:12.3.0-runtime-ubuntu22.04"
        return "nvcr.io/nvidia/ai-workbench/python-basic:1.0.2"
