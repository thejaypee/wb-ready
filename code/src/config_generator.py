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

        # CPU-only setup - ignore GPU detection
        labels = ["ubuntu"]
        if "python" in analysis.languages:
            labels.append("python3")
        if "javascript" in analysis.languages or "typescript" in analysis.languages:
            labels.append("nodejs")
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
                "programming_languages": ConfigGenerator._programming_languages(analysis),
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
        # No GPU secrets needed for CPU-only setup
        env["secrets"] = []

        return env

    @staticmethod
    def _build_execution(analysis: AnalysisResult) -> dict:
        apps = []

        # Generate app entries for each detected entry point
        for ep in analysis.entry_points:
            app = ConfigGenerator._app_for_entry_point(ep, analysis)
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

        # Always use CPU-only resources
        return {
            "apps": apps,
            "resources": {
                "gpu": {"requested": 0},
                "sharedMemoryMB": 1024,
            },
            "secrets": [],
            "mounts": [
                {"type": "project", "target": "/project/", "description": "Project directory", "options": "rw"},
            ],
        }

    @staticmethod
    def _app_for_entry_point(ep: dict, analysis: AnalysisResult) -> dict | None:
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
        elif t in ("nextjs", "nuxt", "vite", "node-server", "node-app"):
            return ConfigGenerator._node_app_entry(ep, analysis)
        elif t == "go":
            pkg = ep["file"]
            return {
                "name": name, "type": "custom", "class": "webapp",
                "start_command": f"cd /project && go run ./{pkg}",
                "health_check_command": "curl -f http://localhost:8080/",
                "stop_command": "pkill -f 'go run'",
                "user_msg": "", "logfile_path": "", "timeout_seconds": 120, "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "8080", "proxy": {"trim_prefix": False}, "url": "http://localhost:8080"},
            }
        elif t == "go-make":
            return {
                "name": name, "type": "custom", "class": "webapp",
                "start_command": "cd /project && make run",
                "health_check_command": "curl -f http://localhost:8080/",
                "stop_command": "pkill -f '/project'",
                "user_msg": "", "logfile_path": "", "timeout_seconds": 120, "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "8080", "proxy": {"trim_prefix": False}, "url": "http://localhost:8080"},
            }
        elif t == "rust":
            return {
                "name": name, "type": "custom", "class": "webapp",
                "start_command": "cd /project && cargo run --release",
                "health_check_command": "curl -f http://localhost:8080/",
                "stop_command": "pkill -f 'target/release'",
                "user_msg": "", "logfile_path": "", "timeout_seconds": 180, "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "8080", "proxy": {"trim_prefix": False}, "url": "http://localhost:8080"},
            }
        elif t == "maven":
            return {
                "name": name, "type": "custom", "class": "webapp",
                "start_command": "cd /project && mvn spring-boot:run",
                "health_check_command": "curl -f http://localhost:8080/",
                "stop_command": "pkill -f 'spring-boot'",
                "user_msg": "", "logfile_path": "", "timeout_seconds": 180, "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "8080", "proxy": {"trim_prefix": False}, "url": "http://localhost:8080"},
            }
        elif t == "gradle":
            return {
                "name": name, "type": "custom", "class": "webapp",
                "start_command": "cd /project && ./gradlew bootRun",
                "health_check_command": "curl -f http://localhost:8080/",
                "stop_command": "pkill -f 'gradlew'",
                "user_msg": "", "logfile_path": "", "timeout_seconds": 180, "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "8080", "proxy": {"trim_prefix": False}, "url": "http://localhost:8080"},
            }
        elif t == "rails":
            return {
                "name": name, "type": "custom", "class": "webapp",
                "start_command": "cd /project && bundle exec rails server -b 0.0.0.0 -p 3000",
                "health_check_command": "curl -f http://localhost:3000/",
                "stop_command": "pkill -f 'rails server'",
                "user_msg": "", "logfile_path": "", "timeout_seconds": 120, "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "3000", "proxy": {"trim_prefix": False}, "url": "http://localhost:3000"},
            }
        elif t == "sinatra":
            return {
                "name": name, "type": "custom", "class": "webapp",
                "start_command": "cd /project && bundle exec ruby app.rb -o 0.0.0.0 -p 4567",
                "health_check_command": "curl -f http://localhost:4567/",
                "stop_command": "pkill -f sinatra",
                "user_msg": "", "logfile_path": "", "timeout_seconds": 60, "icon_url": "",
                "webapp_options": {"autolaunch": True, "port": "4567", "proxy": {"trim_prefix": False}, "url": "http://localhost:4567"},
            }
        return None

    @staticmethod
    def _node_app_entry(ep: dict, analysis: AnalysisResult) -> dict:
        name = ep["name"]
        t = ep["type"]
        port = analysis.node_start_port if analysis else 3000
        pkg_mgr = analysis.node_package_manager if analysis else "npm"

        # Determine the start command based on type
        if t == "nextjs":
            start_cmd = f"cd /project && {pkg_mgr} run build && {pkg_mgr} run start -- -p {port}"
            health = f"curl -f http://localhost:{port}/"
            stop = "pkill -f 'next start'"
        elif t == "nuxt":
            start_cmd = f"cd /project && {pkg_mgr} run build && {pkg_mgr} run start"
            health = f"curl -f http://localhost:{port}/"
            stop = "pkill -f nuxt"
        elif t == "vite":
            start_cmd = f"cd /project && {pkg_mgr} run build && {pkg_mgr} run preview -- --host 0.0.0.0 --port {port}"
            health = f"curl -f http://localhost:{port}/"
            stop = "pkill -f vite"
        else:
            # Generic node-server or node-app
            start_cmd = f"cd /project && {pkg_mgr} start"
            health = f"curl -f http://localhost:{port}/"
            stop = "pkill -f node"

        return {
            "name": name,
            "type": "custom",
            "class": "webapp",
            "start_command": start_cmd,
            "health_check_command": health,
            "stop_command": stop,
            "user_msg": "",
            "logfile_path": "",
            "timeout_seconds": 120,
            "icon_url": "",
            "webapp_options": {
                "autolaunch": True,
                "port": str(port),
                "proxy": {"trim_prefix": False},
                "url": f"http://localhost:{port}",
            },
        }

    @staticmethod
    def _programming_languages(analysis: AnalysisResult) -> list[str]:
        langs = []
        lang_map = {
            "python": "python3", "javascript": "javascript", "typescript": "typescript",
            "go": "go", "rust": "rust", "java": "java", "ruby": "ruby", "cpp": "cpp",
        }
        for detected, label in lang_map.items():
            if detected in analysis.languages:
                langs.append(label)
        return langs

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
        has_node = "javascript" in analysis.languages or "typescript" in analysis.languages
        pkg_mgr = analysis.node_package_manager if hasattr(analysis, "node_package_manager") else "npm"

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
        ]

        if has_node:
            lines.extend([
                "",
                "# Install Node.js LTS via NodeSource",
                "if ! command -v node &> /dev/null; then",
                '    echo "Installing Node.js LTS..."',
                "    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
                "    apt-get install -y -qq nodejs",
                "fi",
            ])
            if pkg_mgr == "pnpm":
                lines.extend([
                    "",
                    "# Install pnpm",
                    "if ! command -v pnpm &> /dev/null; then",
                    '    echo "Installing pnpm..."',
                    "    npm install -g pnpm",
                    "fi",
                    "",
                    "# Install Node.js dependencies",
                    'echo "Installing Node.js dependencies with pnpm..."',
                    "cd /project && pnpm install",
                ])
            elif pkg_mgr == "yarn":
                lines.extend([
                    "",
                    "# Install yarn",
                    "if ! command -v yarn &> /dev/null; then",
                    '    echo "Installing yarn..."',
                    "    npm install -g yarn",
                    "fi",
                    "",
                    "# Install Node.js dependencies",
                    'echo "Installing Node.js dependencies with yarn..."',
                    "cd /project && yarn install",
                ])
            else:
                lines.extend([
                    "",
                    "# Install Node.js dependencies",
                    "if [ -f /project/package.json ]; then",
                    '    echo "Installing Node.js dependencies with npm..."',
                    "    cd /project && npm install",
                    "fi",
                ])

        if "python" in analysis.languages:
            lines.extend([
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
            ])

        if "go" in analysis.languages:
            lines.extend([
                "",
                "# Install Go dependencies",
                "if [ -f /project/go.mod ]; then",
                '    echo "Downloading Go modules..."',
                "    cd /project && go mod download",
                "fi",
            ])

        if "rust" in analysis.languages:
            lines.extend([
                "",
                "# Install Rust toolchain",
                "if ! command -v rustc &> /dev/null; then",
                '    echo "Installing Rust..."',
                "    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
                '    source "$HOME/.cargo/env"',
                "fi",
                "# Build Rust project",
                "if [ -f /project/Cargo.toml ]; then",
                '    echo "Building Rust project..."',
                "    cd /project && cargo build --release",
                "fi",
            ])

        if "java" in analysis.languages:
            lines.extend([
                "",
                "# Install Java (OpenJDK)",
                "if ! command -v java &> /dev/null; then",
                '    echo "Installing OpenJDK..."',
                "    apt-get install -y -qq openjdk-17-jdk maven",
                "fi",
            ])

        if "ruby" in analysis.languages:
            lines.extend([
                "",
                "# Install Ruby and Bundler",
                "if ! command -v ruby &> /dev/null; then",
                '    echo "Installing Ruby..."',
                "    apt-get install -y -qq ruby-full",
                "fi",
                "if [ -f /project/Gemfile ]; then",
                '    echo "Installing Ruby gems..."',
                "    cd /project && gem install bundler && bundle install",
                "fi",
            ])

        lines.extend([
            "",
            "# Initialize Git LFS",
            "git lfs install",
            "",
            "# Create Workbench directories",
            "mkdir -p /project/data /project/models /project/data/scratch",
            "",
            'echo "=== Setup Complete ==="',
        ])
        return "\n".join(lines) + "\n"
