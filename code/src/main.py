"""WB-Ready: Convert any GitHub repository into an NVIDIA AI Workbench project."""

import sys
import os
import tempfile
import shutil
from pathlib import Path

# Add src/ to path for imports (works from /project/code or locally)
src_path = Path(__file__).resolve().parent
sys.path.insert(0, str(src_path))

import streamlit as st

from github_client import GitHubClient, RepositoryInfo
from repository_analyzer import RepositoryAnalyzer, AnalysisResult
from config_generator import ConfigGenerator

st.set_page_config(page_title="WB-Ready", page_icon="wrench", layout="wide")

st.title("WB-Ready: Repository Converter for NVIDIA AI Workbench")
st.markdown("Analyze any GitHub repo and generate all `.project/` configuration files automatically.")

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Configuration")
    github_token = st.text_input(
        "GitHub Token",
        type="password",
        value=os.getenv("GITHUB_TOKEN", ""),
        help="Personal access token with `repo` scope",
    )
    if github_token:
        st.success("Token set")
    else:
        st.warning("Required for forking and private repos")

    st.divider()
    st.markdown("[NVIDIA Workbench docs](https://docs.nvidia.com/ai-workbench/)")
    st.markdown("[Convert a repo (official guide)](https://docs.nvidia.com/ai-workbench/user-guide/latest/how-to/convert-repo.html)")

# ── Session state ───────────────────────────────────────────────────────────

if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "repo_info" not in st.session_state:
    st.session_state.repo_info = None

# ── Step 1: Repository URL ──────────────────────────────────────────────────

st.header("1. Select Repository")
repo_url = st.text_input("GitHub Repository URL", placeholder="https://github.com/owner/repo")

if st.button("Analyze", type="primary", disabled=not repo_url):
    if not github_token:
        st.error("Add a GitHub token in the sidebar first.")
        st.stop()
    with st.spinner("Cloning and analyzing..."):
        try:
            client = GitHubClient(github_token)
            repo_info = client.get_repository_info(repo_url)
            st.session_state.repo_info = repo_info

            tmp = tempfile.mkdtemp()
            try:
                clone_path = client.clone_repository(repo_url, tmp)
                analyzer = RepositoryAnalyzer(clone_path)
                st.session_state.analysis = analyzer.analyze()
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

            st.success(f"Analyzed **{repo_info.full_name}**")
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            st.stop()

# ── Step 2: Results ─────────────────────────────────────────────────────────

if st.session_state.analysis and st.session_state.repo_info:
    analysis: AnalysisResult = st.session_state.analysis
    repo_info: RepositoryInfo = st.session_state.repo_info

    st.divider()
    st.header("2. Analysis Results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Language", repo_info.language)
    c2.metric("GPU needed", "Yes" if analysis.has_gpu_requirements else "No")
    c3.metric("Frameworks", ", ".join(sorted(analysis.detected_frameworks)) or "None")
    c4.metric("Entry points", str(len(analysis.entry_points)))

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Detected languages")
        st.write(", ".join(sorted(analysis.languages)) if analysis.languages else "None")
        st.subheader("Base image")
        st.code(analysis.base_image)

    with col2:
        st.subheader("Entry points")
        if analysis.entry_points:
            for ep in analysis.entry_points:
                st.markdown(f"- `{ep['file']}` ({ep['type']})")
        else:
            st.write("None detected")

    with st.expander("Python dependencies"):
        st.code("\n".join(analysis.python_packages) if analysis.python_packages else "(none)")
    with st.expander("System packages"):
        st.code("\n".join(analysis.system_packages))

    # ── Step 3: Configure ────────────────────────────────────────────────────

    st.divider()
    st.header("3. Configuration")

    col1, col2 = st.columns(2)
    with col1:
        project_name = st.text_input("Project name", value=repo_info.name, help="Lowercase, hyphens OK")
    with col2:
        target_branch = st.text_input("Target branch", value=repo_info.default_branch)

    project_desc = st.text_area("Description", value=repo_info.description)

    # Preview
    if st.button("Preview generated files"):
        spec = ConfigGenerator.generate_spec_yaml(project_name, project_desc, analysis, target_branch)
        st.markdown("**spec.yaml**")
        st.code(spec, language="yaml")

        st.markdown("**apt.txt**")
        st.code(ConfigGenerator.generate_apt_txt(analysis.system_packages))

        if analysis.python_packages:
            st.markdown("**requirements.txt**")
            st.code(ConfigGenerator.generate_requirements_txt(analysis.python_packages))

        st.markdown("**postBuild.bash**")
        st.code(ConfigGenerator.generate_postbuild_bash(analysis), language="bash")

    # ── Step 4: Convert ──────────────────────────────────────────────────────

    st.divider()
    st.header("4. Convert & Push")
    st.markdown(
        "This will **fork** the repo to your GitHub account, add `.project/` config files, "
        "and push. The original repo is never modified."
    )

    if st.button("Convert & Push", type="primary"):
        if not github_token:
            st.error("Add a GitHub token in the sidebar first.")
            st.stop()

        progress = st.progress(0)
        status = st.empty()

        try:
            client = GitHubClient(github_token)

            status.text("Forking repository...")
            progress.progress(15)
            forked_url = client.fork_repository(repo_info.owner, repo_info.name)

            status.text("Cloning fork...")
            progress.progress(35)
            tmp = tempfile.mkdtemp()

            try:
                clone_path = client.clone_repository(forked_url, tmp)

                status.text("Generating Workbench configuration...")
                progress.progress(55)

                project_dir = Path(clone_path) / ".project"
                project_dir.mkdir(exist_ok=True)

                # Generate files
                spec = ConfigGenerator.generate_spec_yaml(project_name, project_desc, analysis, target_branch)
                (project_dir / "spec.yaml").write_text(spec)

                apt = ConfigGenerator.generate_apt_txt(analysis.system_packages)
                (project_dir / "apt.txt").write_text(apt)

                if analysis.python_packages:
                    reqs = ConfigGenerator.generate_requirements_txt(analysis.python_packages)
                    (project_dir / "requirements.txt").write_text(reqs)

                postbuild = ConfigGenerator.generate_postbuild_bash(analysis)
                pb_path = project_dir / "postBuild.bash"
                pb_path.write_text(postbuild)
                pb_path.chmod(0o755)

                # Create standard directories
                (Path(clone_path) / "models").mkdir(exist_ok=True)
                (Path(clone_path) / "data" / "scratch").mkdir(parents=True, exist_ok=True)

                status.text("Committing and pushing...")
                progress.progress(75)

                msg = (
                    "Add NVIDIA AI Workbench configuration\n\n"
                    "Generated by WB-Ready:\n"
                    "- .project/spec.yaml\n"
                    "- .project/apt.txt\n"
                    "- .project/requirements.txt\n"
                    "- .project/postBuild.bash\n\n"
                    "Ready to clone into NVIDIA AI Workbench."
                )
                client.push_changes(clone_path, msg, target_branch)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

            progress.progress(100)
            status.empty()

            fork_web = forked_url.replace(".git", "")
            st.success(f"Done! Fork with Workbench config: {fork_web}")
            st.balloons()

        except Exception as e:
            st.error(f"Conversion failed: {e}")
