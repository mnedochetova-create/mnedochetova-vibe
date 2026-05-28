import os


def env_flag(name: str, default: str = "false") -> bool:
    """Truthy: true, yes, 1 (any case). Matches LOG_GROUP_ENABLED convention."""
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}
