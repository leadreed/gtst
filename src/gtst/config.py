"""GTST root configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .errors import GtstConfigError
from .validation import validate_name

CONFIG_FILENAME = "gtst.json"
DEFAULT_SCHEMA = ["project", "tree", "asset", "variant", "subVariant"]
DEFAULT_VERSION_WIDTH = 3
DEFAULT_READY_TAG_NAME = "ready"
DEFAULT_FILENAME_FACET = "asset"
DEFAULT_SINGLE_VERSION_TAGS: list[str] = []
REQUIRED_FIELDS = {
    "schema",
    "version_width",
    "ready_tag_name",
    "default_filename_facet",
    "single_version_tags",
}


@dataclass(frozen=True)
class GtstConfig:
    """Configuration stored in a GTST root."""

    schema: list[str] = field(default_factory=lambda: list(DEFAULT_SCHEMA))
    version_width: int = DEFAULT_VERSION_WIDTH
    ready_tag_name: str = DEFAULT_READY_TAG_NAME
    default_filename_facet: str = DEFAULT_FILENAME_FACET
    single_version_tags: list[str] = field(
        default_factory=lambda: list(DEFAULT_SINGLE_VERSION_TAGS)
    )

    @classmethod
    def default(cls) -> "GtstConfig":
        return cls()

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "GtstConfig":
        missing = sorted(REQUIRED_FIELDS - set(data))
        if missing:
            raise GtstConfigError(
                f"GTST config missing required fields: {', '.join(missing)}"
            )

        schema = data["schema"]
        version_width = data["version_width"]
        ready_tag_name = data["ready_tag_name"]
        default_filename_facet = data["default_filename_facet"]
        single_version_tags = data["single_version_tags"]

        if not isinstance(schema, list) or not all(
            isinstance(item, str) for item in schema
        ):
            raise GtstConfigError("Config field 'schema' must be a list of strings.")
        if not schema:
            raise GtstConfigError("Config field 'schema' cannot be empty.")
        if len(set(schema)) != len(schema):
            raise GtstConfigError("Config field 'schema' cannot contain duplicates.")
        for name in schema:
            validate_name(name, label="schema field")

        if not isinstance(version_width, int) or isinstance(version_width, bool):
            raise GtstConfigError("Config field 'version_width' must be an integer.")
        if version_width < 1:
            raise GtstConfigError("Config field 'version_width' must be at least 1.")

        if not isinstance(ready_tag_name, str):
            raise GtstConfigError("Config field 'ready_tag_name' must be a string.")
        validate_name(ready_tag_name, label="ready tag")

        if not isinstance(default_filename_facet, str):
            raise GtstConfigError(
                "Config field 'default_filename_facet' must be a string."
            )
        validate_name(default_filename_facet, label="default filename facet")
        if default_filename_facet not in schema:
            raise GtstConfigError(
                "Config field 'default_filename_facet' must name a schema field."
            )

        if not isinstance(single_version_tags, list) or not all(
            isinstance(item, str) for item in single_version_tags
        ):
            raise GtstConfigError(
                "Config field 'single_version_tags' must be a list of strings."
            )
        for tag in single_version_tags:
            validate_name(tag, label="tag")

        return cls(
            schema=list(schema),
            version_width=version_width,
            ready_tag_name=ready_tag_name,
            default_filename_facet=default_filename_facet,
            single_version_tags=list(dict.fromkeys(single_version_tags)),
        )

    @classmethod
    def load(cls, root_path: Path) -> "GtstConfig":
        config_path = root_path / CONFIG_FILENAME
        if not config_path.exists():
            raise GtstConfigError(f"GTST config does not exist: {config_path}")
        if not config_path.is_file():
            raise GtstConfigError(f"GTST config is not a file: {config_path}")

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GtstConfigError(f"GTST config is invalid JSON: {config_path}") from exc

        if not isinstance(data, dict):
            raise GtstConfigError("GTST config must contain a JSON object.")
        return cls.from_mapping(data)

    def write(self, root_path: Path) -> Path:
        config_path = root_path / CONFIG_FILENAME
        config_path.write_text(
            json.dumps(self.to_mapping(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        return config_path

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": list(self.schema),
            "version_width": self.version_width,
            "ready_tag_name": self.ready_tag_name,
            "default_filename_facet": self.default_filename_facet,
            "single_version_tags": list(self.single_version_tags),
        }

    def is_ready_tag(self, tag: str) -> bool:
        return tag == self.ready_tag_name

    def is_single_version_tag(self, tag: str) -> bool:
        return self.is_ready_tag(tag) or tag in set(self.single_version_tags)
