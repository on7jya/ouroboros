"""Configuration loader — supports both YAML and environment variables."""

import os
from typing import Optional, Dict

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def load_yaml_config(path: str = "config.yaml") -> Optional[Dict]:
    """Load config from YAML file if present."""
    if yaml is None:
        raise ImportError(
            "PyYAML is required for YAML config. Install with: pip install pyyaml"
        )
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Config:
    """Unified config object — YAML loads first, then falls back to env vars."""

    def __init__(self):
        # Try YAML first
        yaml_config = load_yaml_config("services/kafka_translator/config.yaml")
        if yaml_config:
            self._load_from_yaml(yaml_config)
        else:
            # Fallback to Pydantic Settings (env vars)
            from .main import settings
            self._copy_from_settings(settings)

    def _load_from_yaml(self, cfg: Dict):
        """Populate fields from YAML config."""
        br = cfg.get("brokers", {})
        self.source_bootstrap_servers = br.get("source", {}).get(
            "host", "localhost"
        ) + ":" + str(br.get("source", {}).get("port", 9092))
        self.dest_bootstrap_servers = br.get("destination", {}).get(
            "host", "localhost"
        ) + ":" + str(br.get("destination", {}).get("port", 9092))

        topics = cfg.get("topics", {})
        self.source_topic = topics.get("source", "source-events")
        self.dest_topic = topics.get("destination", "dest-events")

        # Security — keep simple for now
        self.security_protocol = "PLAINTEXT"
        sasl = br.get("source", {}).get("security_protocol", None)
        if sasl:
            self.security_protocol = sasl

    def _copy_from_settings(self, settings):
        """Fallback: copy from Pydantic Settings."""
        self.source_bootstrap_servers = settings.source_bootstrap_servers
        self.dest_bootstrap_servers = settings.dest_bootstrap_servers
        self.source_topic = settings.source_topic
        self.dest_topic = settings.dest_topic


config = Config()
