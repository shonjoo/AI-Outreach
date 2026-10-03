"""Generation package with lazy module exports."""

__all__ = [
    "LLMClient",
    "build_system_prompt",
    "build_user_prompt",
    "check_batch_uniqueness",
    "DraftGenerator",
    "validate_draft",
]


def __getattr__(name: str):
    if name == "LLMClient":
        from src.generation.llm_client import LLMClient
        return LLMClient
    if name == "DraftGenerator":
        from src.generation.generator import DraftGenerator
        return DraftGenerator
    if name == "build_system_prompt":
        from src.generation.prompts import build_system_prompt
        return build_system_prompt
    if name == "build_user_prompt":
        from src.generation.prompts import build_user_prompt
        return build_user_prompt
    if name == "check_batch_uniqueness":
        from src.generation.uniqueness import check_batch_uniqueness
        return check_batch_uniqueness
    if name == "validate_draft":
        from src.generation.validator import validate_draft
        return validate_draft
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
