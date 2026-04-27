"""ComfyUI nodes for GTST."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid

from gtst import GtstConfig, GtstError, GtstRoot, GtstTagError


CATEGORY = "GTST"
DEFAULT_TEXT_EXTENSION = ".txt"
DEFAULT_IMAGE_EXTENSION = ".png"
ASSET_REF_TYPE = "GTST_ASSET_REF"
FACET_WIDGETS = ("project", "tree", "asset", "variant", "subvariant")
ASSET_REF_SUGGESTION_WIDGETS = (*FACET_WIDGETS, "version", "tag")
WIDGET_TO_SCHEMA_FIELD = {"subvariant": "subVariant"}
SCHEMA_TO_WIDGET_FIELD = {"subVariant": "subvariant"}
BROWSER_MODES = ("current", "latest only", "all versions", "tagged")
BROWSER_RESULT_LIMIT = 200
TEXT_PREVIEW_LIMIT = 500
IMAGE_EXTENSIONS = {".apng", ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".m4v", ".mov", ".mp4", ".ogg", ".ogv", ".webm"}
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


def _facets(
    project: str,
    tree: str,
    asset: str,
    variant: str,
    subvariant: str,
) -> dict[str, str]:
    return {
        "project": project,
        "tree": tree,
        "asset": asset,
        "variant": variant,
        "subVariant": subvariant,
    }


def _schema_field(widget_name: str) -> str:
    return WIDGET_TO_SCHEMA_FIELD.get(widget_name, widget_name)


def _widget_field(schema_name: str) -> str:
    return SCHEMA_TO_WIDGET_FIELD.get(schema_name, schema_name)


def _asset_inputs() -> dict[str, tuple[str, dict[str, object]]]:
    options = _facet_options()
    return {
        "project": _facet_input("Project facet value.", options["project"]),
        "tree": _facet_input("Tree facet value.", options["tree"]),
        "asset": _facet_input("Asset facet value.", options["asset"]),
        "variant": _facet_input("Variant facet value.", options["variant"], "base"),
        "subvariant": _facet_input(
            "SubVariant facet value.", options["subVariant"], "default"
        ),
    }


def _browser_asset_inputs() -> dict[str, tuple[str, dict[str, object]]]:
    options = _facet_options()
    return {
        "project": _facet_input("Project facet value.", options["project"]),
        "tree": _facet_input("Tree facet value.", options["tree"]),
        "asset": _facet_input("Asset facet value.", options["asset"]),
        "variant": _facet_input("Variant facet value.", options["variant"]),
        "subvariant": _facet_input("SubVariant facet value.", options["subVariant"]),
    }


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


def _facet_options() -> dict[str, list[str]]:
    fields = GtstConfig.default().schema
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
        widget_name = _widget_field(prior_field)
        value = str(values.get(widget_name, values.get(prior_field, ""))).strip()
        if not value:
            return None
        prior[prior_field] = value
    return prior


def _complete_facets_from_widget_values(
    root: GtstRoot, values: dict[str, str]
) -> dict[str, str] | None:
    facets: dict[str, str] = {}
    for schema_field in root.config.schema:
        widget_name = _widget_field(schema_field)
        value = str(values.get(widget_name, values.get(schema_field, ""))).strip()
        if not value:
            return None
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

    schema_field = _schema_field(field)
    prior = _prior_facets_for_field(root, schema_field, values or {})
    suggestions = [] if prior is None else root.list_values(schema_field, facets=prior)
    return {
        "root_path": str(root.path),
        "field": field,
        "schema_field": schema_field,
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
            resolved = ""
            metadata = {
                "root_path": str(root.path),
                "asset_dir": root.asset_dir(facets=facets).as_posix(),
                "file_path": "",
                "facets": facets,
                "version": "",
                "tags": [],
            }
    else:
        metadata = _metadata(root, resolved)
    return {
        "root_path": str(root.path),
        "facets": facets,
        "version": metadata["version"],
        "requested_version": version.strip(),
        "requested_tag": tag.strip(),
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
    if file_path:
        return file_path
    root = _ref_root(asset_ref)
    return _resolve_file(root, _ref_facets(asset_ref))


def _metadata(root: GtstRoot, file_path: str) -> dict[str, Any]:
    facets = root.facets_from_path(file_path)
    version = root.version_from_path(file_path)
    tags = set(root.list_tags(version=version, facets=facets))
    try:
        ready_path = root.get_tagged_version(root.config.ready_tag_name, facets=facets)
    except GtstTagError:
        ready_path = None
    if ready_path == file_path:
        tags.add(root.config.ready_tag_name)
    return {
        "root_path": str(root.path),
        "asset_dir": root.asset_dir(facets=facets).as_posix(),
        "file_path": file_path,
        "facets": facets,
        "version": version,
        "tags": sorted(tags),
    }


def _metadata_json(root: GtstRoot, file_path: str) -> str:
    return json.dumps(_metadata(root, file_path), indent=2, sort_keys=True)


def _browser_filter_facets(
    root: GtstRoot, values: dict[str, str] | None = None
) -> dict[str, str]:
    filters: dict[str, str] = {}
    for schema_field in root.config.schema:
        widget_name = _widget_field(schema_field)
        value = str(
            (values or {}).get(widget_name, (values or {}).get(schema_field, ""))
        ).strip()
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
    label = " / ".join(
        [
            str(facets.get("asset", Path(file_path).stem)),
            str(facets.get("variant", "")),
            str(facets.get("subVariant", "")),
            str(metadata["version"]),
        ]
    )
    label = " / ".join(part for part in label.split(" / ") if part)
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
        "media_type": media_type,
        "label": label,
        "subtitle": str(Path(file_path).name),
    }
    if media_type == "text":
        item["preview_text"] = _text_preview(file_path)
    return item


def _browser_paths_for_facets(
    root: GtstRoot, facets: dict[str, str], mode: str, version: str, tag: str
) -> list[str]:
    if version:
        try:
            file_path = root.get_version(version=version, facets=facets)
        except GtstError:
            return []
        if tag and tag not in root.list_tags(version=version, facets=facets):
            return []
        return [file_path]

    if mode == "tagged":
        if not tag:
            return []
        return root.find_by_tag(tag, facets=facets)

    if mode == "all versions":
        paths: list[str] = []
        for asset_version in root.list_versions(facets=facets):
            if tag and tag not in root.list_tags(version=asset_version, facets=facets):
                continue
            paths.append(root.get_version(version=asset_version, facets=facets))
        return paths

    try:
        if mode == "current":
            return [root.get_current(facets=facets)]
        return [root.get_latest(facets=facets)]
    except GtstError:
        return []


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
    items: list[dict[str, Any]] = []
    capped = False

    for facets in _iter_browser_facets(root, filters):
        for file_path in _browser_paths_for_facets(root, facets, mode, version, tag):
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
        "root_path": str(root.path),
        "filters": filters,
        "limit": limit,
        "capped": capped,
        "items": items,
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
) -> str:
    published = root.publish(source_path, facets=facets)
    version = root.version_from_path(published)
    if mark_ready:
        root.tag_version(root.config.ready_tag_name, version=version, facets=facets)
    for tag in _split_tags(tags):
        root.tag_version(tag, version=version, facets=facets)
    return published


def _default_filename(asset: str, file_name: str, extension: str) -> str:
    stripped = file_name.strip()
    if stripped:
        return stripped
    return f"{asset}{extension}"


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

    def resolve(
        self,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
        tag: str,
    ) -> dict[str, Any]:
        root = _root()
        facets = _facets(project, tree, asset, variant, subvariant)
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

    def load(self, asset_ref: dict[str, Any]) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        file_path = _ref_file_path(asset_ref)
        image, mask = _load_image_tensor(file_path)
        result = (image, mask, file_path, _metadata_json(root, file_path))
        return _output(result, _preview_image_file_ui(file_path))


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
        name = _default_filename(facets["asset"], file_name, DEFAULT_IMAGE_EXTENSION)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / name
            _save_image_tensor(image, source)
            published = _publish_existing_file(root, str(source), facets, mark_ready, tags)
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
        name = _default_filename(facets["asset"], file_name, DEFAULT_TEXT_EXTENSION)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / name
            source.write_text(text, encoding="utf-8")
            published = _publish_existing_file(root, str(source), facets, mark_ready, tags)
        result = (
            _asset_ref(root, facets, file_path=published),
            published,
            _metadata_json(root, published),
            text,
        )
        return _output(result)


class LoadGtstVideo:
    """Resolve a GTST video asset path."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("video_path", "metadata_json")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
            }
        }

    def load(self, asset_ref: dict[str, Any]) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        file_path = _ref_file_path(asset_ref)
        result = (file_path, _metadata_json(root, file_path))
        return _output(result, _preview_video_ui(file_path))


class SaveGtstVideo:
    """Save an existing video path into GTST."""

    CATEGORY = CATEGORY
    RETURN_TYPES = (ASSET_REF_TYPE, "STRING", "STRING")
    RETURN_NAMES = ("asset_ref", "published_path", "metadata_json")
    FUNCTION = "save"
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "video_path": ("STRING", {"default": ""}),
                "asset_ref": (ASSET_REF_TYPE, {"forceInput": True}),
                "mark_ready": ("BOOLEAN", {"default": False}),
                "tags": (
                    "STRING",
                    {"default": "", "tooltip": "Comma or newline separated tags."},
                ),
            }
        }

    def save(
        self,
        video_path: str,
        asset_ref: dict[str, Any],
        mark_ready: bool,
        tags: str,
    ) -> dict[str, Any]:
        root = _ref_root(asset_ref)
        facets = _ref_facets(asset_ref)
        published = _publish_existing_file(root, video_path, facets, mark_ready, tags)
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
                        "max": 240,
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
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
        tag: str,
        selected_file_path: str,
        preview_item_size: int,
    ) -> dict[str, Any]:
        del mode, project, tree, asset, variant, subvariant, version, tag, preview_item_size
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
