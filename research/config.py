"""Load and validate research-agent.yaml configuration."""

import os
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "configs" / "research-agent.yaml"


def load_config(config_path: str | None = None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path) as f:
        config = yaml.safe_load(f)
    _validate(config)
    return config


def _validate(config: dict):
    required_keys = ["model", "ollama_url", "search", "languages", "categories", "paths"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")
    if not config["categories"]:
        raise ValueError("At least one category required")
    if not config["languages"]:
        raise ValueError("At least one language required")


def resolve_path(config: dict, key: str) -> Path:
    """Resolve a path from config relative to project root."""
    project_root = Path(__file__).resolve().parent.parent
    return project_root / config["paths"][key]
