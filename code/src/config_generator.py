"""Generates NVIDIA AI Workbench configuration files from analysis results."""

from datetime import datetime, timezone
import yaml
from repository_analyzer import AnalysisResult


class _WorkbenchDumper(yaml.SafeDumper):
    """Custom YAML dumper matching Workbench's 4-space indent with proper list formatting."""
    pass


def _str_representer(dumper, data):
    """Quote strings that contain special chars, leave others unquoted."""
    if any(c in data for c in ":{}\n\\$%") or data == "":
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"')
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_WorkbenchDumper.add_representer(str, _str_representer)


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
                "createdOn": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        return ConfigGenerator._render_spec(spec)

    @staticmethod
    def _render_spec(spec: dict) -> str:
        """Render spec dict as YAML matching Workbench's exact formatting (4-space indent)."""

        def _render_value(val, indent, inline_key=False):
            """Render a YAML value. Returns list of lines."""
            if isinstance(val, dict):
                return _render_dict(val, indent)
            elif isinstance(val, list):
                return _render_list(val, indent)
            else:
                return []  # scalar handled inline

        def _render_dict(d, indent):
            pad = "    " * indent
            lines = []
            for key, val in d.items():
                if isinstance(val, dict):
                    lines.append(f"{pad}{key}:")
                    lines.extend(_render_dict(val, indent + 1))
                elif isinstance(val, list):
                    if not val:
                        lines.append(f"{pad}{key}: []")
                    else:
                        lines.append(f"{pad}{key}:")
                        lines.extend(_render_list(val, indent + 1))
                else:
                    lines.append(f"{pad}{key}: {_quote(val)}")
            return lines

        def _render_list(lst, indent):
            pad = "    " * indent
            lines = []
            for item in lst:
                if isinstance(item, dict):
                    first = True
                    for k, v in item.items():
                        if first:
                            prefix = f"{pad}- "
                            first = False
                        else:
                            prefix = f"{pad}  "
                        if isinstance(v, dict):
                            lines.append(f"{prefix}{k}:")
                            lines.extend(_render_dict(v, indent + 1))
                        elif isinstance(v, list):
                            if not v:
                                lines.append(f"{prefix}{k}: []")
                            else:
                                lines.append(f"{prefix}{k}:")
                                lines.extend(_render_list(v, indent + 1))
                        else:
                            lines.append(f"{prefix}{k}: {_quote(v)}")
                else:
                    lines.append(f"{pad}- {_quote(item)}")
            return lines

        def _quote(val):
            if isinstance(val, bool):
                return "true" if val else "false"
            if isinstance(val, int):
                return str(val)
            if val is None or val == "":
                return '""'
            s = str(val)
            # Quote strings that look like numbers
            try:
                float(s)
                return f'"{s}"'
            except ValueError:
                pass
            # Quote booleans
            if s.lower() in ("true", "false", "null", "yes", "no"):
                return f'"{s}"'
            # Shell commands with \$ need single quotes (double quotes treat \$ as escape).
            # In YAML single-quoted strings, literal ' is escaped as ''.
            if "\\$" in s:
                escaped = s.replace("'", "''")
                return f"'{escaped}'"
            # Quote strings with special YAML chars that need it
            if "\n" in s or s.startswith("{") or s.startswith("["):
                escaped = s.replace('"', '\\"')
                return f'"{escaped}"'
            # Quote strings containing : that aren't already handled by single-quote path
            if ":" in s or s.startswith("&") or s.startswith("*"):
                return f'"{s}"'
            return s

        lines = _render_dict(spec, 0)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _build_environment(analysis: AnalysisResult) -> dict:
        """Build environment section matching Workbench reference format."""
        # Base image packages + project's detected system packages
        base_apt = ["curl", "git", "git-lfs", "python3", "gcc", "python3-dev", "python3-pip", "vim"]
        all_apt = sorted(set(base_apt + analysis.system_packages))

        # Base pip packages + project's detected Python packages
        base_pip = ["jupyterlab==4.0.7"]
        all_pip = base_pip + analysis.python_packages

        package_managers = [
            {
                "name": "apt",
                "binary_path": "/usr/bin/apt",
                "installed_packages": all_apt,
            },
            {
                "name": "pip",
                "binary_path": "/usr/local/bin/pip",
                "installed_packages": all_pip,
            },
        ]

        # JupyterLab app from the base image
        jupyterlab_app = {
            "name": "jupyterlab",
            "type": "jupyterlab",
            "class": "webapp",
            "start_command": "jupyter lab --allow-root --port 8888 --ip 0.0.0.0 --no-browser --NotebookApp.base_url=\\$PROXY_PREFIX --NotebookApp.default_url=/lab --NotebookApp.allow_origin='*'",
            "health_check_command": "[ \\$(echo url=\\$(jupyter lab list | head -n 2 | tail -n 1 | cut -f1 -d' ' | grep -v 'Currently' | sed \"s@/?@/lab?@g\") | curl -o /dev/null -s -w '%{http_code}' --config -) == '200' ]",
            "stop_command": "jupyter lab stop 8888",
            "user_msg": "",
            "logfile_path": "",
            "timeout_seconds": 60,
            "icon_url": "",
            "webapp_options": {
                "autolaunch": True,
                "port": "8888",
                "proxy": {"trim_prefix": False},
                "url_command": "jupyter lab list | head -n 2 | tail -n 1 | cut -f1 -d' ' | grep -v 'Currently'",
            },
        }

        langs = ConfigGenerator._programming_languages(analysis)

        return {
            "base": {
                "registry": "nvcr.io",
                "image": "nvidia/ai-workbench/python-basic:1.0.2",
                "build_timestamp": "",
                "name": "Python Basic",
                "supported_architectures": [],
                "cuda_version": analysis.cuda_version or "",
                "description": "A Python Base with Jupyterlab",
                "entrypoint_script": "",
                "labels": ["ubuntu", "python3", "jupyterlab"],
                "apps": [jupyterlab_app],
                "programming_languages": langs,
                "icon_url": "",
                "image_version": "1.0.2",
                "os": "linux",
                "os_distro": "ubuntu",
                "os_distro_release": "22.04",
                "schema_version": "v2",
                "user_info": {"uid": "", "gid": "", "username": ""},
                "package_managers": package_managers,
                "package_manager_environment": {"name": "", "target": ""},
            },
            "compose_file_path": "",
        }

    @staticmethod
    def _build_execution(analysis: AnalysisResult) -> dict:
        """Build execution section with apps, resources, secrets, and mounts."""
        # Build apps from detected entry points
        apps = []
        for ep in analysis.entry_points:
            app = ConfigGenerator._app_for_entry_point(ep, analysis)
            if app:
                apps.append(app)

        # Always include VS Code app
        vs_code_app = {
            "name": "VS Code",
            "type": "vs-code",
            "class": "native",
            "start_command": "",
            "health_check_command": '[ \\$(ps aux | grep ".vscode-server" | grep -v grep | wc -l ) -gt 4 ] && [ \\$(ps aux | grep "/.vscode-server/bin/.*/node .* net.createConnection" | grep -v grep | wc -l) -gt 0 ]',
            "stop_command": "",
            "user_msg": "",
            "logfile_path": "",
            "timeout_seconds": 120,
            "icon_url": "",
        }
        apps.append(vs_code_app)

        gpu_requested = 1 if analysis.has_gpu_requirements else 0

        return {
            "apps": apps,
            "resources": {
                "gpu": {"requested": gpu_requested},
                "sharedMemoryMB": 0,
            },
            "secrets": [],
            "mounts": [
                {"type": "project", "target": "/project/", "description": "Project directory", "options": "rw"},
                {"type": "volume", "target": "/nvwb-shared-volume/", "description": "", "options": "volumeName=nvwb-shared-volume"},
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
            "# This file contains bash commands that will be executed at the end of the container build process,",
            "# after all system packages and programming language specific package have been installed.",
            "#",
            "# System packages (apt) and Python packages (pip) are managed by Workbench via spec.yaml",
            "# and configpacks. This script handles additional custom setup only.",
            "set -e",
        ]

        if has_node:
            lines.extend([
                "",
                f"# Install Node.js {analysis.node_version}.x via NodeSource",
                "if ! command -v node &> /dev/null; then",
                f'    echo "Installing Node.js {analysis.node_version}.x..."',
                f"    curl -fsSL https://deb.nodesource.com/setup_{analysis.node_version}.x | bash -",
                "    apt-get install -y -qq nodejs",
                "fi",
            ])
            if pkg_mgr == "pnpm":
                lines.extend([
                    "",
                    "# Install pnpm",
                    "if ! command -v pnpm &> /dev/null; then",
                    '    echo "Installing pnpm..."',
                    "    npm install -g pnpm@latest",
                    "    # Ensure pnpm is in PATH",
                    "    export PNPM_HOME=$(npm config get prefix)/bin",
                    "    export PATH=$PNPM_HOME:$PATH",
                    "    # Verify installation",
                    "    if ! command -v pnpm &> /dev/null; then",
                    "        echo 'Failed to install pnpm, falling back to npm'",
                    "        pkg_mgr='npm'",
                    "    else",
                    "        echo 'pnpm installed successfully'",
                    "    fi",
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
                "# Install project Python dependencies from repo (if any)",
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

    @staticmethod
    def generate_prebuild_bash() -> str:
        return (
            "#!/bin/bash\n"
            "# This file contains bash commands that will be executed at the beginning of the container build process,\n"
            "# before any system packages or programming language specific package have been installed.\n"
            "#\n"
            "# Note: This file may be removed if you don't need to use it\n"
        )

    @staticmethod
    def generate_configpacks(analysis: AnalysisResult) -> str:
        """Generate configpacks file listing build phases for Workbench."""
        lines = [
            "*defaults.ContainerUser",
            "*bash.PreBuild",
            "*defaults.CA",
            "*defaults.EnvVars",
            "*defaults.Readme",
            "*defaults.Entrypoint",
            "*apt.PackageManager",
            "*bash.PreLanguage",
        ]
        if "python" in analysis.languages:
            lines.append("*python.PipPackageManager")
        lines.extend([
            "*bash.PostBuild",
            "*jupyterlab.JupyterLab",
            "*vs_code.VSCode",
        ])
        return "\n".join(lines) + "\n"

    @staticmethod
    def generate_gitattributes() -> str:
        return "* text=auto eol=lf\nmodels/** filter=lfs diff=lfs merge=lfs -text\n"

    @staticmethod
    def generate_gitignore(existing_content: str = "") -> str:
        """Generate .gitignore merging existing entries with required Workbench entries."""
        workbench_entries = [
            "",
            "# Ignore generated or temporary files managed by the Workbench",
            ".project/*",
            "!.project/spec.yaml",
            "!.project/configpacks",
            "!.project/apt.txt",
            "!.project/requirements.txt",
            "!.project/postBuild.bash",
            "!.project/preBuild.bash",
            "",
            "# General ignores",
            "",
            "# Byte-compiled / optimized / DLL files",
            "__pycache__/",
            "*.py[cod]",
            "*$py.class",
            "",
            "# Temp directories, notebooks created by jupyterlab",
            ".ipynb_checkpoints",
            ".Trash-*/",
            ".jupyter/",
            "",
            "# Python distribution / packaging",
            ".Python",
            "build/",
            "develop-eggs/",
            "dist/",
            "downloads/",
            "eggs/",
            ".eggs/",
            "lib/",
            "lib64/",
            "parts/",
            "sdist/",
            "var/",
            "wheels/",
            "share/python-wheels/",
            "*.egg-info/",
            ".installed.cfg",
            "*.egg",
            "MANIFEST",
            "",
            "# Unit test / coverage reports",
            "htmlcov/",
            ".tox/",
            ".nox/",
            ".coverage",
            ".coverage.*",
            ".cache",
            "nosetests.xml",
            "coverage.xml",
            "*.cover",
            "*.py,cover",
            ".hypothesis/",
            ".pytest_cache/",
            "cover/",
            "",
            "# Workbench Project Layout",
            "data/*",
            "!data/.gitkeep",
            "data/scratch/*",
            "!data/scratch/.gitkeep",
        ]

        if existing_content.strip():
            # Merge: keep existing entries, append Workbench entries that aren't already present
            existing_lines = set(line.strip() for line in existing_content.splitlines() if line.strip() and not line.strip().startswith("#"))
            merged = existing_content.rstrip("\n")
            new_entries = []
            for entry in workbench_entries:
                stripped = entry.strip()
                if not stripped or stripped.startswith("#"):
                    new_entries.append(entry)
                elif stripped not in existing_lines:
                    new_entries.append(entry)
            merged += "\n" + "\n".join(new_entries) + "\n"
            return merged
        else:
            return "\n".join(workbench_entries).lstrip("\n") + "\n"

    @staticmethod
    def generate_variables_env() -> str:
        return (
            "# Set environment variables in the format KEY=VALUE, 1 per line\n"
            "# This file will be sourced inside the project container when started.\n"
            "# NOTE: If you change this file while the project is running, you must restart the project container for changes to take effect.\n"
            "\n"
        )
