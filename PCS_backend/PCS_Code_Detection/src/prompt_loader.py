from pathlib import Path

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


def fetch_prompt(prompt_name: str) -> str:
    # TODO (production): replace with Azure Key Vault / GCP Secret Manager call
    path = PROMPT_DIR / prompt_name
    return path.read_text(encoding="utf-8")
