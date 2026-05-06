"""Private utility functions shared across serve route modules."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException
from pydantic import BaseModel

from ..pipeline.runner import ALL_STAGES
from ..profile.loader import resolve_profile
from ..profile.schema import Profile
from ..research.refs_store import Reference, update_markdown_references_block


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def _resolve_profile_or_default(name: str | None) -> Profile:
    return resolve_profile(name or "default_ghanaian")


def _list_profiles_payload() -> dict[str, Any]:
    """Discover all available profiles (XDG dir + bundled default)."""
    from ..config import profiles_dir
    from ..profile.loader import resolve_profile as _resolve

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Bundled default first.
    try:
        bundled = _resolve("default_ghanaian")
        out.append(
            {
                "name": bundled.profile_name,
                "dialect": bundled.dialect,
                "is_bundled": True,
            }
        )
        seen.add(bundled.profile_name)
    except Exception:  # pragma: no cover
        pass

    pdir = profiles_dir()
    for path in sorted(pdir.glob("*.yaml")):
        try:
            from ..profile.schema import load_profile

            prof = load_profile(path)
        except Exception:
            continue
        if prof.profile_name in seen:
            # User-saved override of the bundled name; mark as not-bundled.
            for entry in out:
                if entry["name"] == prof.profile_name:
                    entry["is_bundled"] = False
                    entry["dialect"] = prof.dialect
            continue
        out.append(
            {
                "name": prof.profile_name,
                "dialect": prof.dialect,
                "is_bundled": False,
            }
        )
        seen.add(prof.profile_name)
    return {"profiles": out}


def _normalize_stages(raw: Iterable[str] | None) -> tuple[str, ...]:
    if not raw:
        return ALL_STAGES
    seq = list(raw)
    if seq == ["all"]:
        return ALL_STAGES
    return tuple(seq)


def _apply_backend_override(profile: Profile, backend: str | None, model: str | None) -> Profile:
    """Return a profile with ``backend``/``model`` overridden if requested."""
    if backend is None and model is None:
        return profile
    updates: dict[str, Any] = {}
    if backend is not None:
        updates["backend"] = backend
    if model is not None:
        new_cfg = dict(profile.backend_config)
        new_cfg["model"] = model
        updates["backend_config"] = new_cfg
    return profile.model_copy(update=updates)


def _safe_resolve_profile(name: str | None) -> Profile | None:
    """Resolve a profile name; on failure return ``None`` so research aids
    still work without a profile (targets just become null).

    The pre-v1.3 routes (``/v1/score``, ``/v1/transform``) raise 400 on
    unknown profile because they need profile-driven behaviour. The research
    aids prefer to degrade gracefully — a typo in the profile name should
    not block reading metrics.
    """
    if name is None:
        try:
            return resolve_profile("default_ghanaian")
        except FileNotFoundError:
            return None
    try:
        return resolve_profile(name)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "not_found", "detail": str(exc)},
        ) from exc


def _synth_raw_apa(body: Any) -> str:
    authors = ", ".join(body.authors)
    line = f"{authors} ({body.year}). {body.title}."
    if body.venue:
        line += f" {body.venue}."
    return line


def _try_update_markdown_refs(document_path: str, refs: list[Reference]) -> None:
    """Best-effort regeneration of the markdown ``## References`` block.

    Failures (path missing, not writable, encoding issues) are swallowed
    silently — the route still succeeds because ``references.json`` is
    canonical.
    """
    try:
        path = Path(document_path)
        if not path.exists() or not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        new_text = update_markdown_references_block(text, refs)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
    except (OSError, UnicodeDecodeError, UnicodeEncodeError):
        return


def _code_for_status(code: int) -> str:
    if code == 401:
        return "unauthorised"
    if code == 400:
        return "invalid_input"
    if code == 403:
        return "external_disabled"
    if code == 404:
        return "not_found"
    if code == 502:
        return "backend_unavailable"
    return "internal"


def _serialise_pipeline_result(result: Any) -> dict[str, Any]:
    """Convert a :class:`PipelineResult` to the BRIDGE_CONTRACT §3.4 shape."""
    return {
        "input": result.input,
        "output": result.output,
        "pre_score": _to_jsonable(result.pre_score),
        "post_score": _to_jsonable(result.post_score),
        "llm_used": result.llm_used,
        "deterministic_log": [_to_jsonable(item) for item in result.deterministic_log],
        "grammar": _to_jsonable(result.grammar) if result.grammar is not None else None,
        "elapsed_seconds": result.elapsed_seconds,
        "notes": list(result.notes),
    }
