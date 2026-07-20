"""Configuration loading and path management for Bluefish.

Configuration comes from three layers, later ones overriding earlier ones:

  1. Built-in defaults (``DEFAULTS`` below).
  2. A YAML file, if present (``~/.bluefish/config.yaml`` by default, or an
     explicit path passed on the command line).
  3. (Nothing else today — environment only supplies the API key, read where
     it is used.)

The result is exposed as a :class:`Config` object with convenience accessors
and resolved filesystem paths under ``data_dir``.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "data_dir": "~/.bluefish",
    "sensors": {
        "process": {"enabled": True, "poll_interval": 3.0},
        "log": {
            "enabled": True,
            "poll_interval": 2.0,
            "paths": [
                "/var/log/auth.log",
                "/var/log/syslog",
                "/var/log/secure",
                "/var/log/messages",
            ],
        },
    },
    "self_profile": {
        "default_learn_minutes": 5,
        "numeric_k": 3.0,
    },
    "detectors": {
        "adaptive": {"novelty_threshold": 0.5},
        "danger": {"window_seconds": 60, "escalation_threshold": 3.0},
    },
    "response": {"allow_active_measures": False},
    "llm": {
        "enabled": True,
        "model": "claude-sonnet-5",
        "max_tokens": 1024,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


@dataclass
class Config:
    """Resolved Bluefish configuration."""

    data: dict[str, Any]

    # --- generic access -------------------------------------------------
    def get(self, *path: str, default: Any = None) -> Any:
        """Fetch a nested value by key path, e.g. ``get("llm", "model")``."""
        node: Any = self.data
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    # --- resolved paths -------------------------------------------------
    @property
    def data_dir(self) -> Path:
        return Path(os.path.expanduser(self.data["data_dir"]))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bluefish.db"

    @property
    def pid_path(self) -> Path:
        return self.data_dir / "bluefish.pid"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "bluefish.log"

    def ensure_data_dir(self) -> Path:
        """Create the data directory (private perms) and return it."""
        path = self.data_dir
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass
        return path


def default_config_path() -> Path:
    """Where Bluefish looks for a config file when none is given."""
    return Path(os.path.expanduser("~/.bluefish/config.yaml"))


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Load configuration, merging a YAML file over the built-in defaults.

    If ``path`` is None, the default location is used when it exists; a
    missing default file is not an error (defaults apply).
    """
    file_path = Path(path) if path is not None else default_config_path()
    overrides: dict[str, Any] = {}
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config file {file_path} must be a YAML mapping")
        overrides = loaded
    elif path is not None:
        # An explicitly requested file that does not exist is an error.
        raise FileNotFoundError(f"Config file not found: {file_path}")

    return Config(_deep_merge(DEFAULTS, overrides))
