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
    node_frameworks: set[str] = field(default_factory=set)
    node_package_manager: str = "npm"  # npm, pnpm, or yarn
    node_scripts: dict[str, str] = field(default_factory=dict)
    node_start_port: int = 3000


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

# Node.js framework markers detected in package.json dependencies
NODE_FRAMEWORK_MARKERS = {
    "nextjs": ["next"],
    "express": ["express"],
    "nestjs": ["@nestjs/core"],
    "nuxt": ["nuxt"],
    "vite": ["vite"],
    "remix": ["@remix-run/node"],
    "astro": ["astro"],
    "svelte": ["svelte"],
    "react": ["react"],
    "vue": ["vue"],
    "angular": ["@angular/core"],
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
            result.node_frameworks = self._detect_node_frameworks(result.node_packages)
            result.node_package_manager = self._detect_node_package_manager()
            result.node_scripts = self._parse_node_scripts()
            result.entry_points.extend(self._find_node_entry_points(result))

        if "go" in result.languages:
            result.entry_points.extend(self._find_go_entry_points())
        if "rust" in result.languages:
            result.entry_points.extend(self._find_rust_entry_points())
        if "java" in result.languages:
            result.entry_points.extend(self._find_java_entry_points())
        if "ruby" in result.languages:
            result.entry_points.extend(self._find_ruby_entry_points())

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

    def _detect_node_frameworks(self, node_packages: dict[str, str]) -> set[str]:
        frameworks = set()
        pkg_names = set(node_packages.keys())
        for framework, markers in NODE_FRAMEWORK_MARKERS.items():
            if any(m in pkg_names for m in markers):
                frameworks.add(framework)
        return frameworks

    def _detect_node_package_manager(self) -> str:
        if (self.repo_path / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (self.repo_path / "yarn.lock").exists():
            return "yarn"
        return "npm"

    def _parse_node_scripts(self) -> dict[str, str]:
        pkg_json = self.repo_path / "package.json"
        if not pkg_json.exists():
            return {}
        try:
            data = json.loads(pkg_json.read_text())
            return data.get("scripts", {})
        except Exception:
            return {}

    def _find_node_entry_points(self, result: AnalysisResult) -> list[dict[str, str]]:
        entry_points = []
        scripts = result.node_scripts
        pkg_mgr = result.node_package_manager

        # Detect the primary app type and port from scripts
        if "nextjs" in result.node_frameworks:
            port = self._extract_port(scripts.get("dev", "") + scripts.get("start", ""), 3000)
            result.node_start_port = port
            entry_points.append({
                "file": "package.json",
                "type": "nextjs",
                "name": "Next.js App",
            })
        elif "nuxt" in result.node_frameworks:
            port = self._extract_port(scripts.get("dev", "") + scripts.get("start", ""), 3000)
            result.node_start_port = port
            entry_points.append({
                "file": "package.json",
                "type": "nuxt",
                "name": "Nuxt App",
            })
        elif "vite" in result.node_frameworks:
            port = self._extract_port(scripts.get("dev", "") + scripts.get("preview", ""), 5173)
            result.node_start_port = port
            entry_points.append({
                "file": "package.json",
                "type": "vite",
                "name": "Vite App",
            })
        elif "express" in result.node_frameworks or "nestjs" in result.node_frameworks:
            port = self._extract_port(scripts.get("start", ""), 3000)
            result.node_start_port = port
            name = "NestJS" if "nestjs" in result.node_frameworks else "Express"
            entry_points.append({
                "file": "package.json",
                "type": "node-server",
                "name": f"{name} Server",
            })
        elif scripts.get("start") or scripts.get("dev"):
            # Generic Node.js app with a start script
            port = self._extract_port(scripts.get("start", "") + scripts.get("dev", ""), 3000)
            result.node_start_port = port
            entry_points.append({
                "file": "package.json",
                "type": "node-app",
                "name": "Node App",
            })

        return entry_points

    def _find_go_entry_points(self) -> list[dict[str, str]]:
        entry_points = []
        # Check for go.mod (Go modules project)
        if (self.repo_path / "go.mod").exists():
            # Look for main.go or cmd/ pattern
            for fpath in self.repo_path.rglob("main.go"):
                parts = fpath.parts
                if any(skip in parts for skip in ("vendor", ".git", "node_modules")):
                    continue
                rel = fpath.relative_to(self.repo_path)
                entry_points.append({
                    "file": str(rel.parent) if str(rel.parent) != "." else ".",
                    "type": "go",
                    "name": "Go App",
                })
                break  # One entry point is enough
        if not entry_points and (self.repo_path / "Makefile").exists():
            entry_points.append({"file": "Makefile", "type": "go-make", "name": "Go App"})
        return entry_points

    def _find_rust_entry_points(self) -> list[dict[str, str]]:
        entry_points = []
        cargo = self.repo_path / "Cargo.toml"
        if cargo.exists():
            entry_points.append({"file": "Cargo.toml", "type": "rust", "name": "Rust App"})
        return entry_points

    def _find_java_entry_points(self) -> list[dict[str, str]]:
        entry_points = []
        if (self.repo_path / "pom.xml").exists():
            entry_points.append({"file": "pom.xml", "type": "maven", "name": "Java App"})
        elif (self.repo_path / "build.gradle").exists() or (self.repo_path / "build.gradle.kts").exists():
            entry_points.append({"file": "build.gradle", "type": "gradle", "name": "Java App"})
        return entry_points

    def _find_ruby_entry_points(self) -> list[dict[str, str]]:
        entry_points = []
        if (self.repo_path / "Gemfile").exists():
            # Check for Rails
            try:
                gemfile = (self.repo_path / "Gemfile").read_text(errors="ignore")
                if "rails" in gemfile.lower():
                    entry_points.append({"file": "Gemfile", "type": "rails", "name": "Rails App"})
                elif "sinatra" in gemfile.lower():
                    entry_points.append({"file": "Gemfile", "type": "sinatra", "name": "Sinatra App"})
                else:
                    entry_points.append({"file": "Gemfile", "type": "ruby", "name": "Ruby App"})
            except Exception:
                entry_points.append({"file": "Gemfile", "type": "ruby", "name": "Ruby App"})
        return entry_points

    @staticmethod
    def _extract_port(command: str, default: int) -> int:
        """Try to find a port number in a command string."""
        import re
        # Match patterns like --port 3000, -p 3000, PORT=3000, :3000
        match = re.search(r'(?:--port[= ]|PORT[= ]|-p[= ])(\d+)', command)
        if match:
            return int(match.group(1))
        return default

    def _suggest_system_packages(self, result: AnalysisResult) -> list[str]:
        pkgs = ["git", "git-lfs", "curl", "wget"]
        if "python" in result.languages:
            pkgs.extend(["build-essential", "python3-dev"])
        if "javascript" in result.languages or "typescript" in result.languages:
            pkgs.extend(["nodejs", "npm"])
        if "cpp" in result.languages:
            pkgs.extend(["cmake", "g++"])
        if "go" in result.languages:
            pkgs.append("golang")
        if "rust" in result.languages:
            pkgs.extend(["build-essential", "pkg-config", "libssl-dev"])
        if "java" in result.languages:
            pkgs.extend(["openjdk-17-jdk", "maven"])
        if "ruby" in result.languages:
            pkgs.extend(["ruby-full", "build-essential"])
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
