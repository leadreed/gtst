"""ComfyUI nodes for GTST."""

from __future__ import annotations

import json
import mimetypes
import os
import platform
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import uuid

from gtst import GtstConfig, GtstError, GtstRoot, GtstTagError


CATEGORY = "GTST"
DEFAULT_TEXT_EXTENSION = ".txt"
DEFAULT_IMAGE_EXTENSION = ".png"
ASSET_REF_TYPE = "GTST_ASSET_REF"
STATIC_SUGGESTION_WIDGETS = ("version", "tag")
BROWSER_MODES = ("current", "latest only", "all versions")
BROWSER_TAG_FILTER_MODES = ("OR", "AND")
BROWSER_RESULT_LIMIT = 1000
TEXT_PREVIEW_LIMIT = 500
IMAGE_EXTENSIONS = {".apng", ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".m4v", ".mov", ".mp4", ".ogg", ".ogv", ".webm"}
DEFAULT_VIDEO_FORMATS = ("auto", "mp4")
DEFAULT_VIDEO_CODECS = ("auto", "h264")
TEXT_EXTENSIONS = {
    ".cfg",
    ".csv",
    ".json",
    ".log",
    ".md",
    ".py",
    ".text",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


def _root() -> GtstRoot:
    return GtstRoot.from_env()


def _input_schema() -> list[str]:
    root_path = os.environ.get("GTST_ROOT", "").strip()
    if not root_path:
        return list(GtstConfig.default().schema)
    try:
        return list(GtstRoot.create(root_path).config.schema)
    except Exception:
        return list(GtstConfig.default().schema)


def _suggestion_widgets(schema: list[str] | None = None) -> tuple[str, ...]:
    return (*(schema or _input_schema()), *STATIC_SUGGESTION_WIDGETS)


ASSET_REF_SUGGESTION_WIDGETS = _suggestion_widgets()


def schema_metadata_payload() -> dict[str, Any]:
    root = _root()
    schema = list(root.config.schema)
    return {
        "root_path": str(root.path),
        "schema": schema,
        "facet_fields": schema,
        "suggestion_fields": list(_suggestion_widgets(schema)),
        "ready_tag_name": root.config.ready_tag_name,
        "default_filename_facet": root.config.default_filename_facet,
        "browser_modes": list(BROWSER_MODES),
        "browser_tag_filter_modes": list(BROWSER_TAG_FILTER_MODES),
    }


def _asset_inputs() -> dict[str, tuple[str, dict[str, object]]]:
    options = _facet_options()
    return {
        field: _facet_input(f"{field} facet value.", options.get(field, []))
        for field in options
    }


def _browser_asset_inputs() -> dict[str, tuple[str, dict[str, object]]]:
    return _asset_inputs()


def _facet_input(
    tooltip: str, values: list[str], default: str = ""
) -> tuple[str, dict[str, object]]:
    return (
        "STRING",
        {
            "default": default,
            "tooltip": tooltip,
            "gtstFacetValues": values,
        },
    )


def _version_input(default: str = "") -> tuple[str, dict[str, object]]:
    return (
        "STRING",
        {
            "default": default,
            "tooltip": "Version such as v001 or 1. Leave empty to resolve by tag/current.",
        },
    )


def _tag_input(default: str = "") -> tuple[str, dict[str, object]]:
    return (
        "STRING",
        {
            "default": default,
            "tooltip": "Tag name. Leave empty to use ready/current resolution.",
        },
    )


def _tag_filter_mode_input(default: str = "OR") -> tuple[list[str], dict[str, object]]:
    return (
        list(BROWSER_TAG_FILTER_MODES),
        {
            "default": default,
            "tooltip": "How multiple comma-separated tags are matched.",
        },
    )


def _resolve_file(
    root: GtstRoot,
    facets: dict[str, str],
    version: str = "",
    tag: str = "",
) -> str:
    version = version.strip()
    tag = tag.strip()
    if version:
        return root.get_version(version=version, facets=facets)
    if tag:
        return root.get_latest_by_tag(tag, facets=facets)
    return root.get_current(facets=facets)


def _file_signature(file_path: str | Path) -> dict[str, Any]:
    path = Path(file_path)
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def _missing_asset_signature(root: GtstRoot, facets: dict[str, str]) -> dict[str, Any]:
    asset_dir = root.asset_dir(facets=facets)
    if asset_dir.exists():
        return _file_signature(asset_dir)
    parent = asset_dir.parent
    return _file_signature(parent if parent.exists() else root.path)


def _resolution_kind(version: str, tag: str, file_path: str | None) -> str:
    if file_path is not None:
        return "file"
    if version.strip():
        return "version"
    if tag.strip():
        return "tag"
    return "current"


def _change_signature_for_ref(asset_ref: dict[str, Any]) -> str:
    root = _ref_root(asset_ref)
    facets = _ref_facets(asset_ref)
    file_path = _ref_file_path(asset_ref)
    return json.dumps(
        {
            "root_path": str(root.path),
            "facets": facets,
            "resolution": asset_ref.get("resolution", "file"),
            "requested_version": str(asset_ref.get("requested_version", "")).strip(),
            "requested_tag": str(asset_ref.get("requested_tag", "")).strip(),
            "file": _file_signature(file_path),
        },
        sort_keys=True,
    )


def _change_signature_for_optional_ref(asset_ref: dict[str, Any] | None) -> str:
    if not isinstance(asset_ref, dict):
        return json.dumps({"asset_ref": "unavailable"}, sort_keys=True)
    return _change_signature_for_ref(asset_ref)


def _facet_options() -> dict[str, list[str]]:
    fields = _input_schema()
    options = {field: [] for field in fields}
    root_path = os.environ.get("GTST_ROOT", "").strip()
    if not root_path:
        return options

    try:
        root = GtstRoot.create(root_path)
        for field in fields:
            if field in root.config.schema:
                options[field] = sorted(_collect_facet_values(root, field))
        return options
    except Exception:
        return options


def _collect_facet_values(root: GtstRoot, field: str) -> set[str]:
    field_index = root.config.schema.index(field)
    results: set[str] = set()

    def walk(prefix: dict[str, str], depth: int) -> None:
        current_field = root.config.schema[depth]
        for value in root.list_values(current_field, facets=prefix):
            if depth == field_index:
                results.add(value)
            elif depth < field_index:
                walk({**prefix, current_field: value}, depth + 1)

    walk({}, 0)
    return results


def _prior_facets_for_field(
    root: GtstRoot, field: str, values: dict[str, str]
) -> dict[str, str] | None:
    if field not in root.config.schema:
        raise ValueError(f"Unknown GTST facet field: {field}")

    field_index = root.config.schema.index(field)
    prior: dict[str, str] = {}
    for prior_field in root.config.schema[:field_index]:
        value = str(values.get(prior_field, "")).strip()
        if not value:
            return None
        prior[prior_field] = value
    return prior


def _complete_facets_from_widget_values(
    root: GtstRoot, values: dict[str, str]
) -> dict[str, str] | None:
    facets: dict[str, str] = {}
    for schema_field in root.config.schema:
        value = str(values.get(schema_field, "")).strip()
        if not value:
            return None
        facets[schema_field] = value
    return facets


def _facets_from_kwargs(root: GtstRoot, values: dict[str, Any]) -> dict[str, str]:
    facets: dict[str, str] = {}
    for schema_field in root.config.schema:
        value = str(values.get(schema_field, "")).strip()
        if not value:
            raise ValueError(f"Missing GTST facet value: {schema_field}")
        facets[schema_field] = value
    return facets


def _tag_suggestions(root: GtstRoot, facets: dict[str, str], version: str = "") -> list[str]:
    if version:
        return root.list_tags(version=version, facets=facets)

    tags = set(root.list_tags(facets=facets))
    for asset_version in root.list_versions(facets=facets):
        tags.update(root.list_tags(version=asset_version, facets=facets))
    return sorted(tags)


def facet_suggestions_payload(
    field: str, values: dict[str, str] | None = None
) -> dict[str, Any]:
    root = _root()
    if field == "version":
        facets = _complete_facets_from_widget_values(root, values or {})
        suggestions = [] if facets is None else root.list_versions(facets=facets)
        return {
            "root_path": str(root.path),
            "field": field,
            "schema_field": field,
            "facets": facets or {},
            "values": suggestions,
        }
    if field == "tag":
        facets = _complete_facets_from_widget_values(root, values or {})
        version = str((values or {}).get("version", "")).strip()
        suggestions = [] if facets is None else _tag_suggestions(root, facets, version)
        return {
            "root_path": str(root.path),
            "field": field,
            "schema_field": field,
            "facets": facets or {},
            "values": suggestions,
        }

    prior = _prior_facets_for_field(root, field, values or {})
    suggestions = [] if prior is None else root.list_values(field, facets=prior)
    return {
        "root_path": str(root.path),
        "field": field,
        "schema_field": field,
        "facets": prior or {},
        "values": suggestions,
    }


def _asset_ref(
    root: GtstRoot,
    facets: dict[str, str],
    version: str = "",
    tag: str = "",
    file_path: str | None = None,
) -> dict[str, Any]:
    resolved = file_path
    metadata: dict[str, Any]
    if resolved is None:
        try:
            resolved = _resolve_file(root, facets, version=version, tag=tag)
            metadata = _metadata(root, resolved)
        except GtstError:
            if version.strip() or tag.strip():
                raise
            resolved = ""
            metadata = {
                "root_path": str(root.path),
                "asset_dir": root.asset_dir(facets=facets).as_posix(),
                "file_path": "",
                "facets": facets,
                "version": "",
                "tags": [],
                "ready_tag_name": root.config.ready_tag_name,
                "is_ready": False,
            }
    else:
        metadata = _metadata(root, resolved)
    return {
        "root_path": str(root.path),
        "facets": facets,
        "version": metadata["version"],
        "requested_version": version.strip(),
        "requested_tag": tag.strip(),
        "resolution": _resolution_kind(version, tag, file_path),
        "file_path": resolved,
        "metadata": metadata,
    }


def _ref_root(asset_ref: dict[str, Any]) -> GtstRoot:
    return GtstRoot.create(str(asset_ref["root_path"]))


def _ref_facets(asset_ref: dict[str, Any]) -> dict[str, str]:
    facets = asset_ref["facets"]
    if not isinstance(facets, dict):
        raise ValueError("Invalid GTST asset reference: facets must be a dictionary.")
    return {str(key): str(value) for key, value in facets.items()}


def _ref_file_path(asset_ref: dict[str, Any]) -> str:
    file_path = str(asset_ref.get("file_path", ""))
    root = _ref_root(asset_ref)
    version = str(
        asset_ref.get("requested_version") or asset_ref.get("version", "")
    ).strip()
    tag = str(asset_ref.get("requested_tag", "")).strip()

    if asset_ref.get("resolution") in {"current", "tag", "version"}:
        version = str(asset_ref.get("requested_version", "")).strip()
        return _resolve_file(root, _ref_facets(asset_ref), version=version, tag=tag)

    if file_path:
        return file_path
    return _resolve_file(root, _ref_facets(asset_ref), version=version, tag=tag)


def _metadata(root: GtstRoot, file_path: str) -> dict[str, Any]:
    facets = root.facets_from_path(file_path)
    version = root.version_from_path(file_path)
    tags = set(root.list_tags(version=version, facets=facets))
    try:
        ready_path = root.get_tagged_version(root.config.ready_tag_name, facets=facets)
    except GtstTagError:
        ready_path = None
    is_ready = ready_path == file_path
    if is_ready:
        tags.add(root.config.ready_tag_name)
    else:
        tags.discard(root.config.ready_tag_name)
    return {
        "root_path": str(root.path),
        "asset_dir": root.asset_dir(facets=facets).as_posix(),
        "file_path": file_path,
        "facets": facets,
        "version": version,
        "tags": sorted(tags),
        "ready_tag_name": root.config.ready_tag_name,
        "is_ready": is_ready,
    }


def _metadata_json(root: GtstRoot, file_path: str) -> str:
    return json.dumps(_metadata(root, file_path), indent=2, sort_keys=True)


def _browser_filter_facets(
    root: GtstRoot, values: dict[str, str] | None = None
) -> dict[str, str]:
    filters: dict[str, str] = {}
    for schema_field in root.config.schema:
        value = str((values or {}).get(schema_field, "")).strip()
        if value:
            filters[schema_field] = value
    return filters


def _iter_browser_facets(
    root: GtstRoot, filters: dict[str, str]
) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []

    def walk(depth: int, base: Path, facets: dict[str, str]) -> None:
        if depth >= len(root.config.schema):
            if any(
                child.is_dir()
                and root._version_number_from_name(child.name) is not None
                for child in base.iterdir()
            ):
                matches.append(dict(facets))
            return

        field = root.config.schema[depth]
        expected = filters.get(field)
        if expected:
            candidate = base / expected
            if candidate.is_dir():
                walk(depth + 1, candidate, {**facets, field: expected})
            return

        if not base.is_dir():
            return
        for child in sorted(base.iterdir(), key=lambda path: path.name):
            if child.is_dir():
                walk(depth + 1, child, {**facets, field: child.name})

    walk(0, root.path, {})
    return matches


def _path_inside_root(root: GtstRoot, file_path: str | Path) -> Path:
    resolved = Path(file_path).expanduser().resolve()
    if root.path not in [resolved, *resolved.parents]:
        raise ValueError(f"Path is not inside GTST_ROOT: {resolved}")
    return resolved


def _deepest_existing_facet_path(
    root: GtstRoot, values: dict[str, str] | None = None
) -> Path:
    path = root.path
    for schema_field in root.config.schema:
        value = str((values or {}).get(schema_field, "")).strip()
        if not value:
            break
        candidate = path / value
        if not candidate.exists():
            break
        path = candidate
    return path


def _resolved_browser_target(values: dict[str, str] | None = None) -> Path:
    root = _root()
    facets = _browser_filter_facets(root, values)
    path = _deepest_existing_facet_path(root, values)
    version = str((values or {}).get("version", "")).strip()
    tag = str((values or {}).get("tag", "")).strip()

    if len(facets) != len(root.config.schema):
        return path

    if version or tag:
        return Path(_resolve_file(root, facets, version=version, tag=tag)).resolve()

    try:
        return Path(root.get_current(facets=facets)).resolve()
    except GtstError:
        return root.asset_dir(facets=facets).resolve()


def _debug_path_action(message: str, **fields: Any) -> None:
    details = " ".join(
        f"{key}={value!r}" for key, value in fields.items() if value is not None
    )
    suffix = f" {details}" if details else ""
    print(f"[GTST path action] {message}{suffix}", flush=True)


def _run_os_path_command(command: list[str]) -> None:
    _debug_path_action(
        "launch",
        command=command,
        command_line=subprocess.list2cmdline(command),
    )
    completed = subprocess.run(command, check=False)
    _debug_path_action(
        "completed",
        command=command,
        returncode=getattr(completed, "returncode", None),
    )


def _os_action_path(action: str, path: str | Path) -> None:
    resolved = Path(path).expanduser().resolve()
    system = platform.system()
    _debug_path_action(
        "resolved action target",
        action=action,
        system=system,
        path=str(resolved),
        exists=resolved.exists(),
        is_file=resolved.is_file(),
        is_dir=resolved.is_dir(),
    )

    if action == "reveal":
        if system == "Darwin":
            _run_os_path_command(["open", "-R", str(resolved)])
            return
        if system == "Windows":
            if resolved.is_file():
                _run_os_path_command(["explorer.exe", "/select,", str(resolved)])
            else:
                _run_os_path_command(["explorer.exe", str(resolved)])
            return
        if resolved.is_file():
            _run_os_path_command(["xdg-open", str(resolved.parent)])
        else:
            _run_os_path_command(["xdg-open", str(resolved)])
        return

    if action == "open":
        if system == "Darwin":
            _run_os_path_command(["open", str(resolved)])
            return
        if system == "Windows":
            _debug_path_action("startfile", path=str(resolved))
            os.startfile(str(resolved))  # type: ignore[attr-defined]
            return
        _run_os_path_command(["xdg-open", str(resolved)])
        return

    raise ValueError(f"Unsupported GTST path action: {action}")


def path_action_payload(action: str, file_path: str) -> dict[str, Any]:
    if action not in {"reveal", "open"}:
        raise ValueError(f"Unsupported GTST path action: {action}")
    root = _root()
    path = _path_inside_root(root, file_path)
    _debug_path_action(
        "path action request",
        action=action,
        raw_path=file_path,
        root=str(root.path),
        scoped_path=str(path),
    )
    if not path.exists():
        raise ValueError(f"GTST path does not exist: {path}")
    _os_action_path(action, path)
    return {"ok": True, "action": action, "path": str(path)}


def resolve_path_action_payload(
    action: str, values: dict[str, str] | None = None
) -> dict[str, Any]:
    if action not in {"reveal", "open"}:
        raise ValueError(f"Unsupported GTST path action: {action}")
    root = _root()
    target = _resolved_browser_target(values)
    path = _path_inside_root(root, target)
    _debug_path_action(
        "resolved path action request",
        action=action,
        values=values,
        root=str(root.path),
        target=str(target),
        scoped_path=str(path),
    )
    if not path.exists():
        raise ValueError(f"GTST path does not exist: {path}")
    _os_action_path(action, path)
    return {"ok": True, "action": action, "path": str(path)}


def set_ready_payload(file_path: str) -> dict[str, Any]:
    root = _root()
    path = _path_inside_root(root, file_path)
    if not path.is_file():
        raise ValueError(f"GTST ready target is not a file: {path}")
    facets = root.facets_from_path(path)
    version = root.version_from_path(path)
    root.tag_version(root.config.ready_tag_name, version=version, facets=facets)
    refreshed = root.get_version(version=version, facets=facets)
    return {
        "ok": True,
        "path": refreshed,
        "metadata": _metadata(root, refreshed),
    }


def add_tag_payload(file_path: str, tag: str) -> dict[str, Any]:
    tag = tag.strip()
    if not tag:
        raise ValueError("GTST tag cannot be empty.")
    root = _root()
    path = _path_inside_root(root, file_path)
    if not path.is_file():
        raise ValueError(f"GTST tag target is not a file: {path}")
    facets = root.facets_from_path(path)
    version = root.version_from_path(path)
    root.tag_version(tag, version=version, facets=facets)
    refreshed = root.get_version(version=version, facets=facets)
    return {
        "ok": True,
        "path": refreshed,
        "tag": tag,
        "metadata": _metadata(root, refreshed),
    }


def _media_type(file_path: str | Path) -> str:
    extension = Path(file_path).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in TEXT_EXTENSIONS:
        return "text"
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type and mime_type.startswith("text/"):
        return "text"
    return "file"


def _require_media_type(file_path: str | Path, expected: str, node_name: str) -> None:
    actual = _media_type(file_path)
    if actual != expected:
        raise ValueError(
            f"{node_name} expected a GTST {expected} asset, got {actual}: {file_path}"
        )


def _text_preview(file_path: str | Path) -> str:
    path = Path(file_path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= TEXT_PREVIEW_LIMIT:
        return text
    return text[:TEXT_PREVIEW_LIMIT].rstrip() + "..."


def _browser_item(root: GtstRoot, file_path: str) -> dict[str, Any]:
    metadata = _metadata(root, file_path)
    facets = metadata["facets"]
    media_type = _media_type(file_path)
    label_parts = [str(facets.get(field, "")) for field in root.config.schema]
    label_parts.append(str(metadata["version"]))
    label = " / ".join(part for part in label_parts if part)
    item: dict[str, Any] = {
        "asset_ref": _asset_ref(
            root,
            facets,
            version=str(metadata["version"]),
            file_path=file_path,
        ),
        "root_path": str(root.path),
        "facets": facets,
        "version": metadata["version"],
        "file_path": file_path,
        "metadata": metadata,
        "tags": metadata["tags"],
        "is_ready": metadata["is_ready"],
        "media_type": media_type,
        "label": label,
        "subtitle": str(Path(file_path).name),
    }
    if media_type == "text":
        item["preview_text"] = _text_preview(file_path)
    return item


def _browser_paths_for_facets(
    root: GtstRoot,
    facets: dict[str, str],
    mode: str,
    version: str,
    tag: str,
    tag_filter_mode: str = "OR",
) -> list[str]:
    tag_filters = _split_tags(tag)
    tag_filter_mode = (
        tag_filter_mode
        if tag_filter_mode in BROWSER_TAG_FILTER_MODES
        else "OR"
    )
    if version:
        try:
            file_path = root.get_version(version=version, facets=facets)
        except GtstError:
            return []
        if tag_filters and not _file_matches_tags(
            root, file_path, tag_filters, tag_filter_mode
        ):
            return []
        return [file_path]

    if mode == "all versions":
        paths: list[str] = []
        for asset_version in root.list_versions(facets=facets):
            paths.append(root.get_version(version=asset_version, facets=facets))
    else:
        try:
            if mode == "current":
                paths = [root.get_current(facets=facets)]
            else:
                paths = [root.get_latest(facets=facets)]
        except GtstError:
            return []

    if tag_filters:
        return [
            file_path
            for file_path in paths
            if _file_matches_tags(root, file_path, tag_filters, tag_filter_mode)
        ]
    return paths


def _file_matches_tags(
    root: GtstRoot, file_path: str, tags: list[str], tag_filter_mode: str = "OR"
) -> bool:
    metadata = _metadata(root, file_path)
    file_tags = set(metadata["tags"])
    if tag_filter_mode == "AND":
        return all(tag in file_tags for tag in tags)
    return any(tag in file_tags for tag in tags)


def browser_results_payload(
    mode: str,
    values: dict[str, str] | None = None,
    *,
    limit: int = BROWSER_RESULT_LIMIT,
) -> dict[str, Any]:
    root = _root()
    mode = mode if mode in BROWSER_MODES else "current"
    filters = _browser_filter_facets(root, values)
    version = str((values or {}).get("version", "")).strip()
    tag = str((values or {}).get("tag", "")).strip()
    tag_filter_mode = str((values or {}).get("tag_filter_mode", "OR")).strip().upper()
    if tag_filter_mode not in BROWSER_TAG_FILTER_MODES:
        tag_filter_mode = "OR"
    items: list[dict[str, Any]] = []
    capped = False

    for facets in _iter_browser_facets(root, filters):
        for file_path in _browser_paths_for_facets(
            root,
            facets,
            mode,
            version,
            tag,
            tag_filter_mode,
        ):
            try:
                items.append(_browser_item(root, file_path))
            except GtstError:
                continue
            if len(items) >= limit:
                capped = True
                break
        if capped:
            break

    return {
        "mode": mode,
        "tag_filter_mode": tag_filter_mode,
        "root_path": str(root.path),
        "filters": filters,
        "limit": limit,
        "capped": capped,
        "items": items,
    }


def preview_asset_payload(values: dict[str, str] | None = None) -> dict[str, Any]:
    root = _root()
    facets = _browser_filter_facets(root, values)
    if len(facets) != len(root.config.schema):
        return {
            "ok": False,
            "root_path": str(root.path),
            "item": None,
            "error": "Incomplete GTST asset reference.",
        }

    version = str((values or {}).get("version", "")).strip()
    tag = str((values or {}).get("tag", "")).strip()
    try:
        file_path = _resolve_file(root, facets, version=version, tag=tag)
        item = _browser_item(root, file_path)
    except GtstError as exc:
        return {
            "ok": False,
            "root_path": str(root.path),
            "item": None,
            "error": str(exc),
        }

    return {
        "ok": True,
        "root_path": str(root.path),
        "item": item,
    }


def selected_browser_asset(selected_file_path: str) -> tuple[dict[str, Any], str, str]:
    selected = selected_file_path.strip()
    if not selected:
        raise ValueError("No GTST browser preview selected.")
    root = _root()
    file_path = str(_path_inside_root(root, selected))
    if not Path(file_path).is_file():
        raise ValueError(f"Selected GTST browser file does not exist: {file_path}")
    facets = root.facets_from_path(file_path)
    version = root.version_from_path(file_path)
    asset_ref = _asset_ref(root, facets, version=version, file_path=file_path)
    return asset_ref, file_path, json.dumps(asset_ref["metadata"], indent=2, sort_keys=True)


def _split_tags(tags: str) -> list[str]:
    return [
        part.strip()
        for chunk in tags.splitlines()
        for part in chunk.split(",")
        if part.strip()
    ]


def _publish_existing_file(
    root: GtstRoot,
    source_path: str,
    facets: dict[str, str],
    mark_ready: bool,
    tags: str = "",
    filename_override: str | None = None,
) -> str:
    published = root.publish(
        source_path,
        facets=facets,
        filename_override=filename_override,
    )
    version = root.version_from_path(published)
    if mark_ready:
        root.tag_version(root.config.ready_tag_name, version=version, facets=facets)
    for tag in _split_tags(tags):
        root.tag_version(tag, version=version, facets=facets)
    return published


def _video_container_type() -> Any | None:
    try:
        from comfy_api.latest import Types
    except ImportError:
        return None
    return Types.VideoContainer


def _video_codec_type() -> Any | None:
    try:
        from comfy_api.latest import Types
    except ImportError:
        return None
    return Types.VideoCodec


def _video_format_options() -> list[str]:
    video_container = _video_container_type()
    if video_container is None:
        return list(DEFAULT_VIDEO_FORMATS)
    return list(video_container.as_input())


def _video_codec_options() -> list[str]:
    video_codec = _video_codec_type()
    if video_codec is None:
        return list(DEFAULT_VIDEO_CODECS)
    return list(video_codec.as_input())


def _video_format_value(format_name: str) -> Any:
    video_container = _video_container_type()
    if video_container is None:
        return format_name
    return video_container(format_name)


def _video_extension(format_name: str) -> str:
    video_container = _video_container_type()
    if video_container is None:
        return ".mp4" if format_name == "auto" else f".{format_name}"
    extension = video_container.get_extension(format_name)
    if not extension:
        extension = DEFAULT_VIDEO_FORMATS[-1]
    return f".{extension.lstrip('.')}"


def _video_from_file(file_path: str) -> Any:
    try:
        from comfy_api.latest import InputImpl
    except ImportError as exc:
        raise RuntimeError(
            "Load GTST Video requires ComfyUI's video API to create a VIDEO output."
        ) from exc
    return InputImpl.VideoFromFile(file_path)


def _comfy_metadata(prompt: Any, extra_pnginfo: Any) -> dict[str, Any] | None:
    try:
        from comfy.cli_args import args
    except ImportError:
        disable_metadata = False
    else:
        disable_metadata = bool(args.disable_metadata)

    if disable_metadata:
        return None

    metadata: dict[str, Any] = {}
    if extra_pnginfo is not None:
        metadata.update(extra_pnginfo)
    if prompt is not None:
        metadata["prompt"] = prompt
    return metadata or None


def _temp_source_name(file_name: str, extension: str) -> str:
    override_suffix = Path(file_name.strip()).suffix
    return f"source{override_suffix or extension}"


def _output(result: tuple[Any, ...], ui: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"result": result}
    if ui:
        payload["ui"] = ui
    return payload


def _temp_preview_path(extension: str) -> tuple[Path, str]:
    try:
        import folder_paths
    except ImportError:
        temp_dir = Path(tempfile.gettempdir())
    else:
        temp_dir = Path(folder_paths.get_temp_directory())

    filename = f"gtst_{uuid.uuid4().hex}{extension}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir / filename, filename


def _preview_image_file_ui(image_path: str) -> dict[str, Any]:
    source = Path(image_path)
    extension = source.suffix or DEFAULT_IMAGE_EXTENSION
    path, filename = _temp_preview_path(extension)
    shutil.copy2(source, path)
    return {"images": [{"filename": filename, "subfolder": "", "type": "temp"}]}


def _preview_video_ui(video_path: str) -> dict[str, Any]:
    source = Path(video_path)
    extension = source.suffix or ".mp4"
    path, filename = _temp_preview_path(extension)
    shutil.copy2(source, path)
    return {
        "images": [{"filename": filename, "subfolder": "", "type": "temp"}],
        "animated": (True,),
    }


def _load_image_tensor(file_path: str) -> tuple[Any, Any]:
    try:
        import numpy as np
        from PIL import Image, ImageOps
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "Load GTST Image requires Pillow, NumPy, and Torch in the ComfyUI Python environment."
        ) from exc

    image = Image.open(file_path)
    image = ImageOps.exif_transpose(image)
    if image.mode == "RGBA":
        alpha = np.array(image.getchannel("A")).astype(np.float32) / 255.0
        mask = torch.from_numpy(1.0 - alpha).unsqueeze(0)
        image = image.convert("RGB")
    else:
        mask = torch.zeros((1, image.height, image.width), dtype=torch.float32)
        image = image.convert("RGB")

    image_array = np.array(image).astype(np.float32) / 255.0
    return (torch.from_numpy(image_array).unsqueeze(0), mask)


def _save_image_tensor(image: Any, destination: Path) -> None:
    try:
        import numpy as np
        from PIL import Image
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "Save GTST Image requires Pillow, NumPy, and Torch in the ComfyUI Python environment."
        ) from exc

    tensor = image
    if isinstance(tensor, torch.Tensor):
        tensor = tensor.detach().cpu()
    array = np.asarray(tensor)
    if array.ndim == 4:
        array = array[0]
    if array.ndim != 3 or array.shape[-1] not in (1, 3, 4):
        raise ValueError("Expected IMAGE tensor shape [B,H,W,C] or [H,W,C].")
    array = np.clip(array, 0.0, 1.0)
    array = (array * 255.0).round().astype(np.uint8)
    if array.shape[-1] == 1:
        array = array[:, :, 0]
    Image.fromarray(array).save(destination)


class GtstAssetRef:
    """Resolve a reusable GTST asset reference."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "file_path", "metadata_json")
    FUNCTION = "resolve"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                **_asset_inputs(),
                "version": _version_input(),
                "tag": _tag_input(),
            }
        }

    @classmethod
    def IS_CHANGED(cls, version: str = "", tag: str = "", **kwargs: Any) -> str:
        root = _root()
        facets = _facets_from_kwargs(root, kwargs)
        payload: dict[str, Any] = {
            "root_path": str(root.path),
            "facets": facets,
            "resolution": _resolution_kind(version, tag, None),
            "requested_version": version.strip(),
            "requested_tag": tag.strip(),
        }
        try:
            payload["file"] = _file_signature(
                _resolve_file(root, facets, version=version, tag=tag)
            )
        except GtstError as exc:
            payload["missing"] = _missing_asset_signature(root, facets)
            payload["error"] = type(exc).__name__
        return json.dumps(payload, sort_keys=True)

    def resolve(self, version: str = "", tag: str = "", **kwargs: Any) -> dict[str, Any]:
        root = _root()
        facets = _facets_from_kwargs(root, kwargs)
        asset_ref = _asset_ref(root, facets, version=version, tag=tag)
        result = (
            asset_ref,
            str(asset_ref["file_path"]),
            json.dumps(asset_ref["metadata"], indent=2, sort_keys=True),
        )
        return _output(result)


class LoadGtstImage:
    """Load a GTST image asset into ComfyUI."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "file_path", "metadata_json")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, asset_ref: dict[str, Any]) -> str:
        return _change_signature_for_optional_ref(asset_ref)

    def load(self, asset_ref: dict[str, Any]) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        file_path = _ref_file_path(asset_ref)
        _require_media_type(file_path, "image", "Load GTST Image")
        image, mask = _load_image_tensor(file_path)
        result = (image, mask, file_path, _metadata_json(root, file_path))
        return _output(result)


class SaveGtstImage:
    """Save a ComfyUI image into GTST."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "published_path", "metadata_json")
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "image": ("IMAGE",),
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
                "file_name": ("STRING", {"default": ""}),
                "mark_ready": ("BOOLEAN", {"default": False}),
                "tags": (
                    "STRING",
                    {"default": "", "tooltip": "Comma or newline separated tags."},
                ),
            }
        }

    def save(
        self,
        image: Any,
        asset_ref: dict[str, Any],
        file_name: str,
        mark_ready: bool,
        tags: str,
    ) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        facets = _ref_facets(asset_ref)
        filename_override = file_name.strip() or None
        name = _temp_source_name(file_name, DEFAULT_IMAGE_EXTENSION)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / name
            _save_image_tensor(image, source)
            published = _publish_existing_file(
                root,
                str(source),
                facets,
                mark_ready,
                tags,
                filename_override=filename_override,
            )
        result = (
            _asset_ref(root, facets, file_path=published),
            published,
            _metadata_json(root, published),
        )
        return _output(result, _preview_image_file_ui(published))


class LoadGtstText:
    """Load a GTST text asset."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "file_path", "metadata_json")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, asset_ref: dict[str, Any]) -> str:
        return _change_signature_for_optional_ref(asset_ref)

    def load(self, asset_ref: dict[str, Any]) -> tuple[str, str, str]:
        root = _ref_root(asset_ref)
        file_path = _ref_file_path(asset_ref)
        return (
            Path(file_path).read_text(encoding="utf-8"),
            file_path,
            _metadata_json(root, file_path),
        )


class SaveGtstText:
    """Save text into GTST."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "published_path", "metadata_json", "text")
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
                "file_name": ("STRING", {"default": ""}),
                "mark_ready": ("BOOLEAN", {"default": False}),
                "tags": (
                    "STRING",
                    {"default": "", "tooltip": "Comma or newline separated tags."},
                ),
            }
        }

    def save(
        self,
        text: str,
        asset_ref: dict[str, Any],
        file_name: str,
        mark_ready: bool,
        tags: str,
    ) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        facets = _ref_facets(asset_ref)
        filename_override = file_name.strip() or None
        name = _temp_source_name(file_name, DEFAULT_TEXT_EXTENSION)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / name
            source.write_text(text, encoding="utf-8")
            published = _publish_existing_file(
                root,
                str(source),
                facets,
                mark_ready,
                tags,
                filename_override=filename_override,
            )
        result = (
            _asset_ref(root, facets, file_path=published),
            published,
            _metadata_json(root, published),
            text,
        )
        return _output(result)


class LoadGtstVideo:
    """Load a GTST video asset into ComfyUI."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "video_path", "metadata_json")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
            }
        }

    @classmethod
    def IS_CHANGED(cls, asset_ref: dict[str, Any]) -> str:
        return _change_signature_for_optional_ref(asset_ref)

    def load(self, asset_ref: dict[str, Any]) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        file_path = _ref_file_path(asset_ref)
        _require_media_type(file_path, "video", "Load GTST Video")
        result = (_video_from_file(file_path), file_path, _metadata_json(root, file_path))
        return _output(result)


class SaveGtstVideo:
    """Save a ComfyUI video into GTST."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "published_path", "metadata_json")
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "video": ("VIDEO",),
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
                "file_name": ("STRING", {"default": ""}),
                "format": (
                    _video_format_options(),
                    {"default": "auto"},
                ),
                "codec": (
                    _video_codec_options(),
                    {"default": "auto"},
                ),
                "mark_ready": ("BOOLEAN", {"default": False}),
                "tags": (
                    "STRING",
                    {"default": "", "tooltip": "Comma or newline separated tags."},
                ),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    def save(
        self,
        video: Any,
        asset_ref: dict[str, Any],
        file_name: str,
        format: str,
        codec: str,
        mark_ready: bool,
        tags: str,
        prompt: Any = None,
        extra_pnginfo: Any = None,
    ) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        facets = _ref_facets(asset_ref)
        extension = _video_extension(format)
        filename_override = file_name.strip() or None
        name = _temp_source_name(file_name, extension)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / name
            video.save_to(
                str(source),
                format=_video_format_value(format),
                codec=codec,
                metadata=_comfy_metadata(prompt, extra_pnginfo),
            )
            published = _publish_existing_file(
                root,
                str(source),
                facets,
                mark_ready,
                tags,
                filename_override=filename_override,
            )
        result = (
            _asset_ref(root, facets, file_path=published),
            published,
            _metadata_json(root, published),
        )
        return _output(result, _preview_video_ui(published))


class MarkGtstReady:
    """Mark a specific GTST version ready."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "file_path", "metadata_json")
    FUNCTION = "mark_ready"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
                "version": _version_input(""),
            }
        }

    def mark_ready(
        self, asset_ref: dict[str, Any], version: str
    ) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        facets = _ref_facets(asset_ref)
        version = version.strip() or str(asset_ref["version"])
        root.tag_version(root.config.ready_tag_name, version=version, facets=facets)
        file_path = root.get_version(version=version, facets=facets)
        result = (
            _asset_ref(root, facets, file_path=file_path),
            file_path,
            _metadata_json(root, file_path),
        )
        return _output(result)


class TagGtstVersion:
    """Add a custom tag to a GTST version."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "file_path", "metadata_json")
    FUNCTION = "tag_version"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
                "version": _version_input(""),
                "tag": _tag_input("favorite"),
            }
        }

    def tag_version(
        self, asset_ref: dict[str, Any], version: str, tag: str
    ) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        facets = _ref_facets(asset_ref)
        version = version.strip() or str(asset_ref["version"])
        root.tag_version(tag, version=version, facets=facets)
        file_path = root.get_version(version=version, facets=facets)
        result = (
            _asset_ref(root, facets, file_path=file_path),
            file_path,
            _metadata_json(root, file_path),
        )
        return _output(result)


class BrowseGtst:
    """Browse GTST assets and output the selected concrete version."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "file_path", "metadata_json")
    FUNCTION = "browse"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "mode": (list(BROWSER_MODES), {"default": "current"}),
                **_browser_asset_inputs(),
                "version": _version_input(),
                "tag": _tag_input(),
                "tag_filter_mode": _tag_filter_mode_input(),
                "selected_file_path": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Selected browser preview file path.",
                    },
                ),
                "preview_item_size": (
                    "INT",
                    {
                        "default": 140,
                        "min": 80,
                        "max": 600,
                        "step": 1,
                        "display": "slider",
                        "tooltip": "Preview tile size in the browser grid.",
                    },
                ),
            }
        }

    def browse(
        self,
        mode: str,
        version: str,
        tag: str,
        tag_filter_mode: str,
        selected_file_path: str,
        preview_item_size: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del mode, version, tag, tag_filter_mode, preview_item_size, kwargs
        return _output(selected_browser_asset(selected_file_path))


NODE_CLASS_MAPPINGS = {
    "GTSTAssetRef": GtstAssetRef,
    "LoadGTSTImage": LoadGtstImage,
    "SaveGTSTImage": SaveGtstImage,
    "LoadGTSTText": LoadGtstText,
    "SaveGTSTText": SaveGtstText,
    "LoadGTSTVideo": LoadGtstVideo,
    "SaveGTSTVideo": SaveGtstVideo,
    "MarkGTSTReady": MarkGtstReady,
    "TagGTSTVersion": TagGtstVersion,
    "BrowseGTST": BrowseGtst,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GTSTAssetRef": "GTST Asset Ref",
    "LoadGTSTImage": "Load GTST Image",
    "SaveGTSTImage": "Save GTST Image",
    "LoadGTSTText": "Load GTST Text",
    "SaveGTSTText": "Save GTST Text",
    "LoadGTSTVideo": "Load GTST Video",
    "SaveGTSTVideo": "Save GTST Video",
    "MarkGTSTReady": "Mark GTST Ready",
    "TagGTSTVersion": "Tag GTST Version",
    "BrowseGTST": "Browse GTST",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
