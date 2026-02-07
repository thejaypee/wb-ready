"""Optional LLM-powered analysis to enhance heuristic results."""

from dataclasses import dataclass, field
from pathlib import Path
from repository_analyzer import AnalysisResult


@dataclass
class LLMSuggestions:
    corrections: list[str] = field(default_factory=list)
    additional_setup: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_base_image: str = ""


# Key files to send for context (limit total size)
CONTEXT_FILES = [
    "README.md", "readme.md", "README.rst",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "package.json", "pyproject.toml", "requirements.txt",
    "Makefile", "go.mod", "Cargo.toml",
    ".nvimrc", ".python-version", ".node-version", ".tool-versions",
]

MAX_FILE_SIZE = 8000  # chars per file
MAX_TOTAL_CONTEXT = 30000


class LLMAnalyzer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """Detect API key type and create the appropriate client."""
        if self._client:
            return self._client

        key = self.api_key.strip()
        if key.startswith("sk-ant-"):
            # Anthropic / Claude API key
            try:
                import anthropic
                self._client = ("anthropic", anthropic.Anthropic(api_key=key))
            except ImportError:
                raise ImportError("Install anthropic: pip install anthropic")
        else:
            # Assume OpenAI-compatible key
            try:
                import openai
                self._client = ("openai", openai.OpenAI(api_key=key))
            except ImportError:
                raise ImportError("Install openai: pip install openai")
        return self._client

    def analyze(self, analysis: AnalysisResult, repo_path: str) -> LLMSuggestions:
        """Send heuristic results + key files to an LLM for verification."""
        context = self._gather_context(repo_path)
        prompt = self._build_prompt(analysis, context)

        try:
            provider, client = self._get_client()
            if provider == "anthropic":
                return self._call_anthropic(client, prompt)
            else:
                return self._call_openai(client, prompt)
        except Exception:
            # Graceful fallback: if API fails, return empty suggestions
            return LLMSuggestions()

    def _gather_context(self, repo_path: str) -> str:
        """Read key files from the repo for LLM context."""
        root = Path(repo_path)
        parts = []
        total = 0
        for fname in CONTEXT_FILES:
            fpath = root / fname
            if fpath.exists() and fpath.is_file():
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")[:MAX_FILE_SIZE]
                    if total + len(content) > MAX_TOTAL_CONTEXT:
                        break
                    parts.append(f"=== {fname} ===\n{content}")
                    total += len(content)
                except Exception:
                    continue
        return "\n\n".join(parts)

    def _build_prompt(self, analysis: AnalysisResult, context: str) -> str:
        return f"""You are an expert at configuring NVIDIA AI Workbench projects. Analyze the following heuristic analysis results and repository files, then provide corrections and suggestions.

## Heuristic Analysis Results
- Languages: {', '.join(sorted(analysis.languages)) or 'None'}
- Frameworks: {', '.join(sorted(analysis.detected_frameworks)) or 'None'}
- Node frameworks: {', '.join(sorted(analysis.node_frameworks)) if analysis.node_frameworks else 'None'}
- Entry points: {analysis.entry_points}
- Base image: {analysis.base_image}
- GPU required: {analysis.has_gpu_requirements}
- Node version: {analysis.node_version}
- Package manager: {analysis.node_package_manager}

## Repository Files
{context}

## Instructions
Respond in JSON with these fields:
- "corrections": list of strings describing any errors in the heuristic analysis
- "additional_setup": list of strings describing extra setup steps needed
- "warnings": list of strings about potential issues
- "suggested_base_image": string with a better base image if the current one is wrong, or empty string

Only include items where you have specific, actionable feedback. Be concise."""

    def _call_anthropic(self, client, prompt: str) -> LLMSuggestions:
        import json
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_response(response.content[0].text)

    def _call_openai(self, client, prompt: str) -> LLMSuggestions:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_response(response.choices[0].message.content)

    def _parse_response(self, text: str) -> LLMSuggestions:
        import json
        # Extract JSON from response (handle markdown code blocks)
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            data = json.loads(text)
            return LLMSuggestions(
                corrections=data.get("corrections", []),
                additional_setup=data.get("additional_setup", []),
                warnings=data.get("warnings", []),
                suggested_base_image=data.get("suggested_base_image", ""),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return LLMSuggestions()
