"""GitHub API client for cloning, forking, and pushing repositories."""

import os
import time
from dataclasses import dataclass
from github import Github, GithubException
import git


@dataclass
class RepositoryInfo:
    owner: str
    name: str
    full_name: str
    clone_url: str
    default_branch: str
    description: str
    language: str


class GitHubClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN or pass token.")
        self.github = Github(self.token)

    def get_repository_info(self, repo_url: str) -> RepositoryInfo:
        """Fetch repo metadata from a GitHub URL."""
        parts = repo_url.rstrip("/").split("/")
        owner, repo = parts[-2], parts[-1].replace(".git", "")
        try:
            r = self.github.get_repo(f"{owner}/{repo}")
            return RepositoryInfo(
                owner=owner,
                name=repo,
                full_name=r.full_name,
                clone_url=r.clone_url,
                default_branch=r.default_branch,
                description=r.description or "",
                language=r.language or "Unknown",
            )
        except GithubException as e:
            raise ValueError(f"Cannot fetch repo: {e}") from e

    def clone_repository(self, repo_url: str, local_path: str) -> str:
        """Clone a repo to local_path. Returns path."""
        # Inject token for private repos
        if self.token and "github.com" in repo_url:
            repo_url = repo_url.replace("https://", f"https://x-access-token:{self.token}@")
        try:
            git.Repo.clone_from(repo_url, local_path, depth=1)
            return local_path
        except git.GitCommandError as e:
            raise ValueError(f"Clone failed: {e}") from e

    def fork_repository(self, owner: str, repo: str) -> str:
        """Fork a repo. Returns the fork's clone URL."""
        try:
            source = self.github.get_repo(f"{owner}/{repo}")
            fork = self.github.get_user().create_fork(source)
            # Wait for fork to be ready
            time.sleep(3)
            return fork.clone_url
        except GithubException as e:
            if "already exists" in str(e).lower():
                user = self.github.get_user()
                existing = self.github.get_repo(f"{user.login}/{repo}")
                return existing.clone_url
            raise ValueError(f"Fork failed: {e}") from e

    def create_fresh_repo(self, source_owner: str, source_repo: str, local_clone_path: str) -> str:
        """Create a new repo with only the latest files (no history). Fast for Workbench cloning."""
        import shutil

        user = self.github.get_user()
        repo_name = f"{source_owner}-{source_repo}"

        # Delete existing repo if it exists
        try:
            existing = self.github.get_repo(f"{user.login}/{repo_name}")
            existing.delete()
            time.sleep(2)
        except GithubException:
            pass

        # Create new empty repo
        try:
            new_repo = user.create_repo(
                repo_name,
                description=f"Workbench-ready version of {source_owner}/{source_repo}",
                auto_init=False,
                private=False,
            )
        except GithubException as e:
            raise ValueError(f"Failed to create repo: {e}") from e

        # Remove old .git and re-init as a fresh repo
        git_dir = os.path.join(local_clone_path, ".git")
        if os.path.exists(git_dir):
            shutil.rmtree(git_dir)

        repo = git.Repo.init(local_clone_path, initial_branch="main")
        remote_url = new_repo.clone_url
        if self.token and "github.com" in remote_url:
            remote_url = remote_url.replace("https://", f"https://x-access-token:{self.token}@")
        repo.create_remote("origin", remote_url)

        # Configure git user for commit
        repo.config_writer().set_value("user", "name", "WB-Ready").release()
        repo.config_writer().set_value("user", "email", "wb-ready@nvidia.com").release()

        return new_repo.clone_url

    def push_changes(self, local_repo_path: str, commit_message: str, branch: str = "main") -> None:
        """Stage all changes, commit, and push."""
        try:
            repo = git.Repo(local_repo_path)

            # Configure git user if not set
            try:
                repo.config_reader().get_value("user", "name")
            except Exception:
                repo.config_writer().set_value("user", "name", "WB-Ready").release()
                repo.config_writer().set_value("user", "email", "wb-ready@nvidia.com").release()

            repo.git.add(A=True)

            # For fresh repos with no HEAD, always commit
            has_head = True
            try:
                repo.head.commit
            except ValueError:
                has_head = False

            if not has_head or repo.is_dirty(untracked_files=True):
                repo.index.commit(commit_message)
            else:
                return

            origin = repo.remote("origin")
            origin.push(refspec=f"HEAD:refs/heads/{branch}")
        except git.GitCommandError as e:
            raise ValueError(f"Push failed: {e}") from e
