"""Generates NVIDIA AI Workbench configuration files from analysis results."""

import yaml
from repository_analyzer import AnalysisResult


class ConfigGenerator:

    @staticmethod
    def generate_spec_yaml(
        project_name: str,
        description: str,
        analysis: AnalysisResult,
        default_branch: str = "main",
    ) -> str:
        project_name = project_name.lower().replace("_", "-").replace(" ", "-")

        spec = {
            "specVersion": "v2",
            "specMinorVersion": 2,
            "meta": {
                "name": project_name,
                "image": f"project-{project_name}",
                "description": description or f"Workbench project: {project_name}",
                "labels": [],
                "createdOn": "",
                "defaultBranch": default_branch,
            },
            "layout": [
                {"path": "code/", "type": "code", "storage": "git"},
                {"path": "data/", "type": "data", "storage": "gitignore"},
                {"path": "models/", "type": "models", "storage": "gitlfs"},
                {"path": "data/scratch/", "type": "data", "storage": "gitignore"},
            ],
            "environment": ConfigGenerator._build_environment(analysis),
            "execution": ConfigGenerator._build_execution(analysis),
        }
        return yaml.dump(spec, default_flow_style=False, sort_keys=False, width=120)

    @staticmethod
    def _build_environment(analysis: AnalysisResult) -> dict:
        # Parse base image into registry + image parts
        parts = analysis.base_image.split("/", 1)
        registry = parts[0] if len(parts) > 1 else "nvcr.io"
        image = parts[1] if len(parts) > 1 else parts[0]

        is_gpu = analysis.has_gpu_requirements
        labels = ["ubuntu", "python3"]
        if "pytorch" in analysis.detected_frameworks:
            labels.append("pytorch")
        if "tensorflow" in analysis.detected_frameworks:
            labels.append("tensorflow")

        # Build base apps (JupyterLab comes with python-basic)
        base_apps = []
        if "python-basic" in analysis.base_image:
            base_apps.append({
                "name": "jupyterlab",
                "type": "jupyterlab",
                "class": "webapp",
                "start_command": "jupyter lab --allow-root --port 8888 --ip 0.0.0.0 --no-browser --NotebookApp.base_url=\\$PROXY_PREFIX --NotebookApp.default_url=/lab --NotebookApp.allow_origin='*'",
                "health_check_command": "[ \\$(echo url=\\$(jupyter lab list | head -n 2 | tail -n 1 | cut -f1 -d'' '' | grep -v ''Currently'' | sed \"s@/?@/lab?@g\") | curl -o /dev/null -s -w ''%{http_code}'' --config -) == ''200'' ]",
                "stop_command": "jupyter lab stop 8888",
                "user_msg": "",
                "logfile_path": "",
                "timeout_seconds": 60,
                "icon_url": "",
                "webapp_options": {
                    "autolaunch": False,
                    "port": "8888",
                    "proxy": {"trim_prefix": False},
                    "url_command": "jupyter lab list | head -n 2 | tail -n 1 | cut -f1 -d' ' | grep -v 'Currently'",
                },
            })

        env = {
            "base": {
                "registry": registry,
                "image": image,
                "build_timestamp": "",
                "name": ConfigGenerator._friendly_image_name(image),
                "supported_architectures": ["amd64"],
                "cuda_version": analysis.cuda_version,
                "description": f"NVIDIA {ConfigGenerator._friendly_image_name(image)} Container",
                "entrypoint_script": "",
                "labels": labels,
                "apps": base_apps,
                "programming_languages": ["python3"] if "python" in analysis.languages else [],
                "icon_url": "",
                "image_version": "",
                "os": "linux",
                "os_distro": "ubuntu",
                "os_distro_release": "22.04",
                "schema_version": "v2",
                "user_info": {"uid": "", "gid": "", "username": ""},
                "package_managers": [
                    {
                        "name": "apt",
                        "binary_path": "/usr/bin/apt",
                        "installed_packages": analysis.system_packages,
                    },
                    {
                        "name": "pip",
                        "binary_path": "/usr/local/bin/pip",
                        "installed_packages": [],
                    },
                ],
                "package_manager_environment": {"name": "", "target": ""},
            },
            "compose_file_path": "",
        }

        # Add secrets for common API keys
        secrets = []
        if is_gpu:
            secrets.append({"variable": "NVIDIA_API_KEY", "description": "NVIDIA API key from build.nvidia.com"})
        env["secrets"] = secrets

        return env

    @staticmethod
    def _build_execution(analysis: AnalysisResult) -> dict:
        apps = []

        # Generate app entries for each detected entry point
        for ep in analysis.entry_points:
            app = ConfigGenerator._app_for_entry_point(ep)
            if app:
                apps.append(app)

        # Always include VS Code
        apps.append({
            "name": "VS Code",
            "type": "vs-code",
            "class": "native",
            "start_command": "",
            "health_check_command": "[ \\$(ps aux | grep \".vscode-server\" | grep -v grep | wc -l ) -gt 4 ] && [ \\$(ps aux | grep \"/.vscode-server/bin/.*/node .* net.createConnection\" | grep -v grep | wc -l) -gt 0 ]",
            "stop_command": "",
            "user_msg": "",
            "logfile_path": "",
            "timeout_seconds": 120,
            "icon_url": "",
        })

        gpu_count = 1 if analysis.has_gpu_requirements else 0
        return {
            "apps": apps,
            "resources": {
                "gpu": {"requested": gpu_count},
                "sharedMemoryMB": 2048 if analysis.has_gpu_requirements else 1024,
            },
            "secrets": [],
            "mounts": [
                {"type": "project", "target": "/project/", "description": "Project directory", "options": "rw"},
            ],
        }

    @staticmethod
    def _app_for_entry_point(ep: dict) -> dict | None:
        t = ep["type"]
        f = ep["file"]
        name = ep["name"]

        if t == "streamlit":
            return {
                "name": f"{name} UI",
                "type": "custom",
                "class": "webapp",
                "start_command": f"cd /project && python -m streamlit run {f} --server.port=8501 --server.address=0.0.0.0 --server.baseUrlPath=$PROXY_PREFIX",
                "health_check_command": "curl -f http://localhost:8501/_stcore/health",
                "stop_command": f"pkill -f 'streamlit run {f}'",
                "user_msg": "",
                "logfile_path": "",
                "timeout_seconds": 60,
                "icon_url": "",
                "webapp_options": {
                    "autolaunch": True,
                    "port": "8501",
                    "proxy": {"trim_prefix": False},
                    "url": "http://localhost:8501",
                },
            }
        elif t == "flask":
            return {
                "name": f"{name} API",
                "type": "custom",
                "class": "webapp",
                "start_command": f"cd /project && python {f}",
                "health_check_command": "curl -f http://localhost:5000/",
                "stop_command": f"pkill -f 'python {f}'",
                "user_msg": "",
                "logfile_path": "",
                "timeout_seconds": 60,
                "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "5000", "proxy": {"trim_prefix": False}, "url": "http://localhost:5000"},
            }
        elif t == "fastapi":
            module = f.replace("/", ".").replace(".py", "")
            return {
                "name": f"{name} API",
                "type": "custom",
                "class": "webapp",
                "start_command": f"cd /project && uvicorn {module}:app --host 0.0.0.0 --port 8000",
                "health_check_command": "curl -f http://localhost:8000/docs",
                "stop_command": "pkill -f uvicorn",
                "user_msg": "",
                "logfile_path": "",
                "timeout_seconds": 60,
                "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "8000", "proxy": {"trim_prefix": False}, "url": "http://localhost:8000"},
            }
        elif t == "gradio":
            return {
                "name": f"{name} UI",
                "type": "custom",
                "class": "webapp",
                "start_command": f"cd /project && python {f}",
                "health_check_command": "curl -f http://localhost:7860/",
                "stop_command": f"pkill -f 'python {f}'",
                "user_msg": "",
                "logfile_path": "",
                "timeout_seconds": 60,
                "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "7860", "proxy": {"trim_prefix": False}, "url": "http://localhost:7860"},
            }
        return None

    @staticmethod
    def _friendly_image_name(image: str) -> str:
        if "pytorch" in image:
            return "PyTorch"
        if "tensorflow" in image:
            return "TensorFlow"
        if "cuda" in image:
            return "CUDA"
        if "python-basic" in image:
            return "Python Basic"
        return "Base"

    @staticmethod
    def generate_apt_txt(system_packages: list[str]) -> str:
        return "\n".join(sorted(set(system_packages))) + "\n"

    @staticmethod
    def generate_requirements_txt(python_packages: list[str]) -> str:
        return "\n".join(python_packages) + "\n"

    @staticmethod
    def generate_postbuild_bash(analysis: AnalysisResult) -> str:
        lines = [
            "#!/bin/bash",
            "set -e",
            "",
            'echo "=== AI Workbench Project Setup ==="',
            "",
            "# Install system packages from apt.txt",
            "if [ -f /project/.project/apt.txt ]; then",
            '    echo "Installing system packages..."',
            "    apt-get update -qq",
            "    xargs -a /project/.project/apt.txt apt-get install -y -qq",
            "fi",
            "",
            "# Install Python dependencies",
            "if [ -f /project/.project/requirements.txt ]; then",
            '    echo "Installing Python requirements..."',
            "    pip install --upgrade pip",
            "    pip install -r /project/.project/requirements.txt",
            "fi",
            "",
            "# Also install from repo root requirements.txt if present",
            "if [ -f /project/requirements.txt ]; then",
            '    echo "Installing project requirements..."',
            "    pip install -r /project/requirements.txt",
            "fi",
            "",
            "# Install Node.js dependencies if needed",
            "if [ -f /project/package.json ]; then",
            '    echo "Installing Node.js dependencies..."',
            "    npm install --prefix /project",
            "fi",
            "",
            "# Initialize Git LFS",
            "git lfs install",
            "",
            "# Create Workbench directories",
            "mkdir -p /project/data /project/models /project/data/scratch",
            "",
            'echo "=== Setup Complete ==="',
        ]
        return "\n".join(lines) + "\n"
