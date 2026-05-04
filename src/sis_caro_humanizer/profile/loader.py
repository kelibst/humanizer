from __future__ import annotations

from pathlib import Path

from ..config import profile_path
from .schema import Profile, load_profile


BUNDLED_DEFAULT = Path(__file__).parent / "default_ghanaian.yaml"


def resolve_profile(name_or_path: str) -> Profile:
    """Resolve a profile by name (XDG config dir), explicit path, or bundled default."""
    candidate = Path(name_or_path)
    if candidate.exists():
        return load_profile(candidate)
    user_path = profile_path(name_or_path)
    if user_path.exists():
        return load_profile(user_path)
    if name_or_path in ("default", "default_ghanaian"):
        return load_profile(BUNDLED_DEFAULT)
    raise FileNotFoundError(
        f"profile {name_or_path!r} not found in {user_path.parent}, "
        f"and no file exists at {candidate}"
    )
