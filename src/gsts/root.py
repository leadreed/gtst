"""Public GSTS root API."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
from typing import Any

from .config import CONFIG_FILENAME, GstsConfig
from .errors import GstsConfigError, GstsPathError, GstsPublishError, GstsTagError, GstsVersionError
from .locking import FileLock
from .validation import validate_name

GTST_TAGS_DIR = "gtst_tags"


class GstsRoot:
    """A filesystem root containing GSTS projects and assets."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.config = GstsConfig.load(self.path)

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        schema: list[str] | None = None,
        version_width: int = 3,
        single_version_tags: list[str] | None = None,
        exist_ok: bool = True,
    ) -> "GstsRoot":
        root_path = Path(path).expanduser().resolve()
        if root_path.exists() and not root_path.is_dir():
            raise GstsConfigError(f"GSTS root is not a directory: {root_path}")
        root_path.mkdir(parents=True, exist_ok=exist_ok)

        config_path = root_path / CONFIG_FILENAME
        if config_path.exists() and not exist_ok:
            raise GstsConfigError(f"GSTS config already exists: {config_path}")

        if not config_path.exists():
            config = GstsConfig.from_mapping(
                {
                    "schema": schema if schema is not None else GstsConfig.default().schema,
                    "version_width": version_width,
                    "single_version_tags": single_version_tags
                    if single_version_tags is not None
                    else GstsConfig.default().single_version_tags,
                }
            )
            config.write(root_path)
        return cls(root_path)

    def publish(
        self,
        source: str | Path,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> str:
        source_path = Path(source).expanduser().resolve()
        if not source_path.exists():
            raise GstsPublishError(f"Source file does not exist: {source_path}")
        if not source_path.is_file():
            raise GstsPublishError(f"Source path is not a file: {source_path}")

        with self._lock():
            asset_dir = self.asset_dir(facets=facets, **facet_values)
            asset_dir.mkdir(parents=True, exist_ok=True)
            next_number = self._latest_version_number(asset_dir) + 1
            version_dir = asset_dir / self._format_version(next_number)
            if version_dir.exists():
                raise GstsPublishError(f"Version folder already exists: {version_dir}")
            version_dir.mkdir()
            destination = version_dir / source_path.name
            if destination.exists():
                raise GstsPublishError(f"Destination file already exists: {destination}")
            shutil.copy2(source_path, destination)
            return str(destination.resolve())

    def get_latest(
        self, *, facets: dict[str, str] | None = None, **facet_values: str
    ) -> str:
        return self.get_version(version="latest", facets=facets, **facet_values)

    def get_current(
        self, *, facets: dict[str, str] | None = None, **facet_values: str
    ) -> str:
        try:
            return self.get_tagged_version(
                self.config.ready_tag_name, facets=facets, **facet_values
            )
        except GstsTagError:
            return self.get_latest(facets=facets, **facet_values)

    def get_version(
        self,
        version: str | int,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> str:
        asset_dir = self.asset_dir(facets=facets, **facet_values)
        version_dir = self.version_dir(asset_dir, version)
        return str(self._asset_file_in_version(version_dir).resolve())

    def list_versions(
        self, *, facets: dict[str, str] | None = None, **facet_values: str
    ) -> list[str]:
        asset_dir = self.asset_dir(facets=facets, **facet_values)
        return [self._format_version(number) for number in self._version_numbers(asset_dir)]

    def tag_version(
        self,
        tag: str,
        version: str | int,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> str:
        validate_name(tag, label="tag")
        with self._lock():
            asset_dir = self.asset_dir(facets=facets, **facet_values)
            version_dir = self.version_dir(asset_dir, version)
            number = self._version_number_from_dir(version_dir)
            if self.config.is_single_version_tag(tag):
                tag_path = self._write_single_version_tag(asset_dir, tag, number)
            else:
                tag_path = self._write_multi_version_tag(version_dir, tag)
            return str(tag_path.resolve())

    def get_tagged_version(
        self,
        tag: str,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> str:
        validate_name(tag, label="tag")
        asset_dir = self.asset_dir(facets=facets, **facet_values)
        if self.config.is_single_version_tag(tag):
            version_number = self._current_single_version_tag(asset_dir, tag)
            if version_number is None:
                raise GstsTagError(f"Tag '{tag}' is not set for asset: {asset_dir}")
            return self.get_version(
                version=version_number, facets=facets, **facet_values
            )

        tagged = self.find_by_tag(tag, facets=facets, **facet_values)
        if not tagged:
            raise GstsTagError(f"Tag '{tag}' is not set for asset: {asset_dir}")
        if len(tagged) > 1:
            raise GstsTagError(f"Tag '{tag}' is set on multiple versions.")
        return tagged[0]

    def get_latest_by_tag(
        self,
        tag: str,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> str:
        validate_name(tag, label="tag")
        asset_dir = self.asset_dir(facets=facets, **facet_values)
        if self.config.is_single_version_tag(tag):
            version_number = self._current_single_version_tag(asset_dir, tag)
            if version_number is None:
                raise GstsTagError(f"Tag '{tag}' is not set for asset: {asset_dir}")
            return self.get_version(version=version_number, facets=facets, **facet_values)

        latest_version: str | None = None
        for version_name in self.list_versions(facets=facets, **facet_values):
            version_dir = asset_dir / version_name
            if (version_dir / GTST_TAGS_DIR / f"{tag}.gtst").is_file():
                latest_version = version_name
        if latest_version is None:
            raise GstsTagError(f"Tag '{tag}' is not set for asset: {asset_dir}")
        return self.get_version(version=latest_version, facets=facets, **facet_values)

    def find_by_tag(
        self,
        tag: str,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> list[str]:
        validate_name(tag, label="tag")
        asset_dir = self.asset_dir(facets=facets, **facet_values)
        if self.config.is_single_version_tag(tag):
            version_number = self._current_single_version_tag(asset_dir, tag)
            if version_number is None:
                return []
            return [self.get_version(version=version_number, facets=facets, **facet_values)]

        results: list[str] = []
        for version_name in self.list_versions(facets=facets, **facet_values):
            version_dir = asset_dir / version_name
            if (version_dir / GTST_TAGS_DIR / f"{tag}.gtst").is_file():
                results.append(str(self._asset_file_in_version(version_dir).resolve()))
        return results

    def list_tags(
        self,
        version: str | int | None = None,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> list[str]:
        asset_dir = self.asset_dir(facets=facets, **facet_values)
        tags: set[str] = set()

        for tag in self.config.single_version_tags:
            if self._current_single_version_tag(asset_dir, tag) is not None:
                tags.add(tag)

        if version is not None:
            version_dir = self.version_dir(asset_dir, version)
            tag_dir = version_dir / GTST_TAGS_DIR
            if tag_dir.is_dir():
                for path in tag_dir.iterdir():
                    if path.is_file() and path.name.endswith(".gtst"):
                        tag_name = path.name[:-5]
                        if tag_name not in self.config.single_version_tags:
                            tags.add(tag_name)
        return sorted(tags)

    def list_values(
        self,
        field: str,
        *,
        facets: dict[str, str] | None = None,
        **facet_values: str,
    ) -> list[str]:
        if field not in self.config.schema:
            raise GstsPathError(f"Unknown schema field: {field}")
        merged = self._merge_facets(facets, facet_values, require_complete=False)
        field_index = self.config.schema.index(field)
        for prior_field in self.config.schema[:field_index]:
            if prior_field not in merged:
                raise GstsPathError(
                    f"Cannot list '{field}' without prior facet '{prior_field}'."
                )
        base = self.path.joinpath(
            *(merged[name] for name in self.config.schema[:field_index])
        )
        if not base.is_dir():
            return []
        return sorted(path.name for path in base.iterdir() if path.is_dir())

    def asset_dir(
        self, *, facets: dict[str, str] | None = None, **facet_values: str
    ) -> Path:
        merged = self._merge_facets(facets, facet_values, require_complete=True)
        relative_parts = [merged[field] for field in self.config.schema]
        return self.path.joinpath(*relative_parts)

    def version_dir(self, asset_dir: str | Path, version: str | int) -> Path:
        asset_path = Path(asset_dir).resolve()
        if version == "latest":
            latest_number = self._latest_version_number(asset_path)
            if latest_number < 1:
                raise GstsVersionError(f"No versions exist for asset: {asset_path}")
            version_name = self._format_version(latest_number)
        else:
            version_name = self._normalize_version(version)
        version_path = asset_path / version_name
        if not version_path.is_dir():
            raise GstsVersionError(f"Version folder does not exist: {version_path}")
        return version_path

    def asset_dir_from_path(self, path: str | Path) -> str:
        resolved = Path(path).expanduser().resolve()
        version_dir = Path(self.version_dir_from_path(resolved))
        return str(version_dir.parent.resolve())

    def version_dir_from_path(self, path: str | Path) -> str:
        resolved = Path(path).expanduser().resolve()
        current = resolved if resolved.is_dir() else resolved.parent
        while self.path in [current, *current.parents]:
            if current.is_dir() and self._version_number_from_name(current.name) is not None:
                return str(current.resolve())
            if current == self.path:
                break
            current = current.parent
        raise GstsPathError(f"Path is not inside a GSTS version folder: {resolved}")

    def version_from_path(self, path: str | Path) -> str:
        return Path(self.version_dir_from_path(path)).name

    def facets_from_path(self, path: str | Path) -> dict[str, str]:
        asset_dir = Path(self.asset_dir_from_path(path))
        try:
            relative = asset_dir.relative_to(self.path)
        except ValueError as exc:
            raise GstsPathError(f"Path is not inside GSTS root: {path}") from exc
        parts = relative.parts
        if len(parts) != len(self.config.schema):
            raise GstsPathError(f"Path does not match GSTS schema: {asset_dir}")
        return dict(zip(self.config.schema, parts))

    def _merge_facets(
        self,
        facets: dict[str, str] | None,
        facet_values: dict[str, str],
        *,
        require_complete: bool,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        if facets is not None:
            if not isinstance(facets, dict):
                raise GstsPathError("facets must be a dictionary.")
            merged.update(facets)
        for key, value in facet_values.items():
            if key in merged and merged[key] != value:
                raise GstsPathError(f"Facet '{key}' was provided more than once.")
            merged[key] = value

        unknown = sorted(set(merged) - set(self.config.schema))
        if unknown:
            raise GstsPathError(f"Unknown schema fields: {', '.join(unknown)}")

        if require_complete:
            missing = [field for field in self.config.schema if field not in merged]
            if missing:
                raise GstsPathError(f"Missing schema fields: {', '.join(missing)}")

        for field, value in merged.items():
            validate_name(value, label=f"facet '{field}'")
        return merged

    def _lock(self) -> FileLock:
        return FileLock(self.path / "gtst.lock")

    def _version_numbers(self, asset_dir: Path) -> list[int]:
        if not asset_dir.is_dir():
            return []
        numbers = [
            number
            for path in asset_dir.iterdir()
            if path.is_dir()
            for number in [self._version_number_from_name(path.name)]
            if number is not None
        ]
        return sorted(numbers)

    def _latest_version_number(self, asset_dir: Path) -> int:
        numbers = self._version_numbers(asset_dir)
        return numbers[-1] if numbers else 0

    def _format_version(self, number: int) -> str:
        return f"v{number:0{self.config.version_width}d}"

    def _normalize_version(self, version: str | int) -> str:
        if isinstance(version, bool):
            raise GstsVersionError("Version cannot be a boolean.")
        if isinstance(version, int):
            if version < 1:
                raise GstsVersionError("Version number must be at least 1.")
            return self._format_version(version)
        if not isinstance(version, str):
            raise GstsVersionError("Version must be an integer, 'latest', or v-prefixed string.")
        if version.isdigit():
            return self._format_version(int(version))
        number = self._version_number_from_name(version)
        if number is None:
            raise GstsVersionError(f"Invalid version: {version}")
        return self._format_version(number)

    def _version_number_from_name(self, name: str) -> int | None:
        match = re.fullmatch(rf"v(\d{{{self.config.version_width},}})", name)
        if not match:
            return None
        number = int(match.group(1))
        return number if number >= 1 else None

    def _version_number_from_dir(self, version_dir: Path) -> int:
        number = self._version_number_from_name(version_dir.name)
        if number is None:
            raise GstsVersionError(f"Invalid version folder: {version_dir}")
        return number

    def _asset_file_in_version(self, version_dir: Path) -> Path:
        files = [
            path
            for path in version_dir.iterdir()
            if path.is_file() and path.name != "gtst.lock" and not path.name.endswith(".gtst")
        ]
        if not files:
            raise GstsVersionError(f"Version folder contains no asset file: {version_dir}")
        if len(files) > 1:
            raise GstsVersionError(
                f"Version folder contains more than one asset file: {version_dir}"
            )
        return files[0]

    def _write_multi_version_tag(self, version_dir: Path, tag: str) -> Path:
        tag_dir = version_dir / GTST_TAGS_DIR
        tag_dir.mkdir(parents=True, exist_ok=True)
        tag_path = tag_dir / f"{tag}.gtst"
        tag_path.touch(exist_ok=True)
        return tag_path

    def _write_single_version_tag(self, asset_dir: Path, tag: str, version_number: int) -> Path:
        tag_dir = asset_dir / GTST_TAGS_DIR / tag
        tag_dir.mkdir(parents=True, exist_ok=True)
        next_operation = self._latest_tag_operation(tag_dir, tag) + 1
        tag_path = tag_dir / (
            f"gtstTag{next_operation:0{self.config.version_width}d}_"
            f"{tag}_{version_number:0{self.config.version_width}d}.gtst"
        )
        if tag_path.exists():
            raise GstsTagError(f"Tag operation file already exists: {tag_path}")
        tag_path.touch()
        return tag_path

    def _current_single_version_tag(self, asset_dir: Path, tag: str) -> int | None:
        tag_dir = asset_dir / GTST_TAGS_DIR / tag
        if not tag_dir.is_dir():
            return None
        candidates: list[tuple[int, int]] = []
        for path in tag_dir.iterdir():
            parsed = self._parse_single_version_tag_file(path.name, tag)
            if parsed is not None:
                candidates.append(parsed)
        if not candidates:
            return None
        return sorted(candidates)[-1][1]

    def _latest_tag_operation(self, tag_dir: Path, tag: str) -> int:
        operations = [
            parsed[0]
            for path in tag_dir.iterdir()
            for parsed in [self._parse_single_version_tag_file(path.name, tag)]
            if parsed is not None
        ]
        return max(operations, default=0)

    def _parse_single_version_tag_file(self, name: str, tag: str) -> tuple[int, int] | None:
        escaped_tag = re.escape(tag)
        match = re.fullmatch(rf"gtstTag(\d+)_{escaped_tag}_(\d+)\.gtst", name)
        if not match:
            return None
        operation = int(match.group(1))
        version = int(match.group(2))
        if operation < 1 or version < 1:
            return None
        return operation, version
