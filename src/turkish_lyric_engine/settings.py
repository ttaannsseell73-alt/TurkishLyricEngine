"""TOML settings contain no credentials; environment keys stay at transport."""
from pathlib import Path
import tomllib

from .contracts import Brief
from .providers import HttpJsonProvider, configured_provider


def load_settings(path=None):
    if path is None:
        return {"generation": {}, "provider": {}, "judge": {}}
    with Path(path).open("rb") as handle:
        value = tomllib.load(handle)
    if set(value) - {"generation", "provider", "judge"}:
        raise ValueError("unknown settings section")
    for section in ("generation", "provider", "judge"):
        value.setdefault(section, {})
        if not isinstance(value[section], dict):
            raise ValueError("settings sections must be tables")
    if set(value["generation"]) - (set(Brief.__dataclass_fields__) - {"theme"}):
        raise ValueError("unknown generation setting")
    for section in ("provider", "judge"):
        if set(value[section]) - {"kind", "model", "base_url", "timeout", "max_output_tokens"}:
            raise ValueError("unknown provider setting; secrets belong in environment")
    return value


def make_provider(settings, *, overrides=None):
    values = {**settings, **{k: v for k, v in (overrides or {}).items() if v is not None}}
    provider = configured_provider(kind=values.get("kind"), model=values.get("model"), base_url=values.get("base_url"))
    if "timeout" in values or "max_output_tokens" in values:
        provider = HttpJsonProvider(provider.model, kind=provider.name, base_url=provider.base_url,
                                    timeout=values.get("timeout", 60), max_output_tokens=values.get("max_output_tokens", 8000))
    return provider
