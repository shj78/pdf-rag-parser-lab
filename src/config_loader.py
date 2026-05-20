"""Shared helpers for experiment configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_config(path: str | Path) -> tuple[dict[str, Any], Path]:
    """Load a YAML file and return both the parsed data and its directory."""

    config_path = Path(path).expanduser().resolve()
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config file must contain a mapping: {config_path}")
    return payload, config_path.parent


def resolve_path(path_value: str | Path, base_dir: Path) -> Path:
    """Resolve a config path relative to the config file directory."""

    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()
