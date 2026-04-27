"""ComfyUI nodes for GTST."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from typing import Any

from gtst import GtstRoot, GtstTagError


CATEGORY = "GTST"
DEFAULT_TEXT_EXTENSION = ".txt"
DEFAULT_IMAGE_EXTENSION = ".png"


def _root(root_path: str) -> GtstRoot:
    stripped = root_path.strip()
    if stripped:
        return GtstRoot.create(stripped)
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


def _asset_inputs() -> dict[str, tuple[str, dict[str, object]]]:
    return {
        "root_path": (
            "STRING",
            {
                "default": "",
                "tooltip": "GTST root path. Leave empty to use GTST_ROOT.",
            },
        ),
        "project": ("STRING", {"default": "project1"}),
        "tree": ("STRING", {"default": "assets"}),
        "asset": ("STRING", {"default": "asset"}),
        "variant": ("STRING", {"default": "base"}),
        "subvariant": ("STRING", {"default": "default"}),
    }


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
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("file_path", "metadata_json")
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
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
        tag: str,
    ) -> tuple[str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        file_path = _resolve_file(root, facets, version=version, tag=tag)
        return (file_path, _metadata_json(root, file_path))


class LoadGtstImage:
    """Load a GTST image asset into ComfyUI."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("IMAGE", "MASK", "STRING", "STRING")
    RETURN_NAMES = ("image", "mask", "file_path", "metadata_json")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return GtstAssetRef.INPUT_TYPES()

    def load(
        self,
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
        tag: str,
    ) -> tuple[Any, Any, str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        file_path = _resolve_file(root, facets, version=version, tag=tag)
        image, mask = _load_image_tensor(file_path)
        return (image, mask, file_path, _metadata_json(root, file_path))


class SaveGtstImage:
    """Save a ComfyUI image into GTST."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("published_path", "metadata_json")
    FUNCTION = "save"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "image": ("IMAGE",),
                **_asset_inputs(),
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
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        file_name: str,
        mark_ready: bool,
        tags: str,
    ) -> tuple[str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        name = _default_filename(asset, file_name, DEFAULT_IMAGE_EXTENSION)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / name
            _save_image_tensor(image, source)
            published = _publish_existing_file(root, str(source), facets, mark_ready, tags)
        return (published, _metadata_json(root, published))


class LoadGtstText:
    """Load a GTST text asset."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("text", "file_path", "metadata_json")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return GtstAssetRef.INPUT_TYPES()

    def load(
        self,
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
        tag: str,
    ) -> tuple[str, str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        file_path = _resolve_file(root, facets, version=version, tag=tag)
        return (
            Path(file_path).read_text(encoding="utf-8"),
            file_path,
            _metadata_json(root, file_path),
        )


class SaveGtstText:
    """Save text into GTST."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("published_path", "metadata_json")
    FUNCTION = "save"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "text": ("STRING", {"default": "", "multiline": True}),
                **_asset_inputs(),
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
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        file_name: str,
        mark_ready: bool,
        tags: str,
    ) -> tuple[str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        name = _default_filename(asset, file_name, DEFAULT_TEXT_EXTENSION)
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / name
            source.write_text(text, encoding="utf-8")
            published = _publish_existing_file(root, str(source), facets, mark_ready, tags)
        return (published, _metadata_json(root, published))


class LoadGtstVideo:
    """Resolve a GTST video asset path."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("video_path", "metadata_json")
    FUNCTION = "load"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return GtstAssetRef.INPUT_TYPES()

    def load(
        self,
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
        tag: str,
    ) -> tuple[str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        file_path = _resolve_file(root, facets, version=version, tag=tag)
        return (file_path, _metadata_json(root, file_path))


class SaveGtstVideo:
    """Save an existing video path into GTST."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("published_path", "metadata_json")
    FUNCTION = "save"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "video_path": ("STRING", {"default": ""}),
                **_asset_inputs(),
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
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        mark_ready: bool,
        tags: str,
    ) -> tuple[str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        published = _publish_existing_file(root, video_path, facets, mark_ready, tags)
        return (published, _metadata_json(root, published))


class MarkGtstReady:
    """Mark a specific GTST version ready."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("file_path", "metadata_json")
    FUNCTION = "mark_ready"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {"required": {**_asset_inputs(), "version": _version_input("v001")}}

    def mark_ready(
        self,
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
    ) -> tuple[str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        root.tag_version(root.config.ready_tag_name, version=version, facets=facets)
        file_path = root.get_version(version=version, facets=facets)
        return (file_path, _metadata_json(root, file_path))


class TagGtstVersion:
    """Add a custom tag to a GTST version."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("file_path", "metadata_json")
    FUNCTION = "tag_version"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                **_asset_inputs(),
                "version": _version_input("v001"),
                "tag": _tag_input("favorite"),
            }
        }

    def tag_version(
        self,
        root_path: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
        version: str,
        tag: str,
    ) -> tuple[str, str]:
        root = _root(root_path)
        facets = _facets(project, tree, asset, variant, subvariant)
        root.tag_version(tag, version=version, facets=facets)
        file_path = root.get_version(version=version, facets=facets)
        return (file_path, _metadata_json(root, file_path))


class BrowseGtst:
    """List GTST facet values or asset versions as JSON."""

    CATEGORY = CATEGORY
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("json",)
    FUNCTION = "browse"

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, dict[str, object]]:
        return {
            "required": {
                "root_path": _asset_inputs()["root_path"],
                "mode": (["values", "versions"], {"default": "values"}),
                "partial_query": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "For values: slash path before the facet to list.",
                    },
                ),
                "project": ("STRING", {"default": "project1"}),
                "tree": ("STRING", {"default": "assets"}),
                "asset": ("STRING", {"default": "asset"}),
                "variant": ("STRING", {"default": "base"}),
                "subvariant": ("STRING", {"default": "default"}),
            }
        }

    def browse(
        self,
        root_path: str,
        mode: str,
        partial_query: str,
        project: str,
        tree: str,
        asset: str,
        variant: str,
        subvariant: str,
    ) -> tuple[str]:
        root = _root(root_path)
        if mode == "versions":
            facets = _facets(project, tree, asset, variant, subvariant)
            payload: dict[str, Any] = {
                "mode": mode,
                "root_path": str(root.path),
                "facets": facets,
                "versions": root.list_versions(facets=facets),
            }
        else:
            parts = [part for part in partial_query.strip("/").split("/") if part]
            if len(parts) >= len(root.config.schema):
                raise ValueError("partial_query must be shorter than the GTST schema.")
            facets = dict(zip(root.config.schema, parts))
            field = root.config.schema[len(parts)]
            payload = {
                "mode": "values",
                "root_path": str(root.path),
                "partial_query": "/".join(parts),
                "field": field,
                "facets": facets,
                "values": root.list_values(field, facets=facets),
            }
        return (json.dumps(payload, indent=2, sort_keys=True),)


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
