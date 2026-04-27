from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from comfy_nodes import (
    NODE_CLASS_MAPPINGS,
    NODE_DISPLAY_NAME_MAPPINGS,
    BrowseGtst,
    GtstAssetRef,
    LoadGtstText,
    LoadGtstVideo,
    MarkGtstReady,
    SaveGtstText,
    SaveGtstVideo,
    TagGtstVersion,
)


def test_comfy_entrypoint_exports_node_mappings() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "gtst_comfyui_nodes",
        repo_root / "__init__.py",
        submodule_search_locations=[str(repo_root)],
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.NODE_CLASS_MAPPINGS == NODE_CLASS_MAPPINGS
    assert module.NODE_DISPLAY_NAME_MAPPINGS == NODE_DISPLAY_NAME_MAPPINGS


def test_node_mappings_include_requested_nodes() -> None:
    assert NODE_CLASS_MAPPINGS == {
        "GTSTAssetRef": GtstAssetRef,
        "LoadGTSTImage": NODE_CLASS_MAPPINGS["LoadGTSTImage"],
        "SaveGTSTImage": NODE_CLASS_MAPPINGS["SaveGTSTImage"],
        "LoadGTSTText": LoadGtstText,
        "SaveGTSTText": SaveGtstText,
        "LoadGTSTVideo": LoadGtstVideo,
        "SaveGTSTVideo": SaveGtstVideo,
        "MarkGTSTReady": MarkGtstReady,
        "TagGTSTVersion": TagGtstVersion,
        "BrowseGTST": BrowseGtst,
    }
    assert set(NODE_DISPLAY_NAME_MAPPINGS) == set(NODE_CLASS_MAPPINGS)


def test_text_nodes_asset_ref_tag_and_ready(tmp_path: Path) -> None:
    root_path = str(tmp_path / "root")

    first, first_metadata = SaveGtstText().save(
        "first prompt",
        root_path,
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "prompt.txt",
        False,
        "draft",
    )
    second, second_metadata = SaveGtstText().save(
        "second prompt",
        root_path,
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "prompt.txt",
        True,
        "approved, favorite",
    )

    assert Path(first).read_text(encoding="utf-8") == "first prompt"
    assert Path(second).read_text(encoding="utf-8") == "second prompt"
    assert json.loads(first_metadata)["version"] == "v001"
    assert json.loads(second_metadata)["tags"] == ["approved", "favorite", "ready"]

    ref_path, ref_metadata = GtstAssetRef().resolve(
        root_path,
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "",
        "",
    )
    assert ref_path == second
    assert json.loads(ref_metadata)["version"] == "v002"

    tagged_path, _ = GtstAssetRef().resolve(
        root_path,
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "",
        "draft",
    )
    assert tagged_path == first

    text, loaded_path, _ = LoadGtstText().load(
        root_path,
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "v001",
        "",
    )
    assert text == "first prompt"
    assert loaded_path == first

    ready_path, ready_metadata = MarkGtstReady().mark_ready(
        root_path,
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "v001",
    )
    assert ready_path == first
    assert "ready" in json.loads(ready_metadata)["tags"]

    tagged_ready_path, tagged_ready_metadata = TagGtstVersion().tag_version(
        root_path,
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "v001",
        "selected",
    )
    assert tagged_ready_path == first
    assert "selected" in json.loads(tagged_ready_metadata)["tags"]


def test_video_nodes_publish_and_load_path(tmp_path: Path) -> None:
    root_path = str(tmp_path / "root")
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake video")

    published, metadata = SaveGtstVideo().save(
        str(source),
        root_path,
        "project1",
        "videos",
        "shot01",
        "base",
        "default",
        True,
        "review",
    )

    assert Path(published).read_bytes() == b"fake video"
    assert json.loads(metadata)["tags"] == ["ready", "review"]
    assert LoadGtstVideo().load(
        root_path,
        "project1",
        "videos",
        "shot01",
        "base",
        "default",
        "",
        "",
    )[0] == published


def test_browse_lists_values_and_versions(tmp_path: Path) -> None:
    root_path = str(tmp_path / "root")
    SaveGtstText().save(
        "caption",
        root_path,
        "project1",
        "texts",
        "caption01",
        "base",
        "default",
        "",
        False,
        "",
    )

    values = json.loads(
        BrowseGtst().browse(
            root_path,
            "values",
            "project1/texts",
            "unused",
            "unused",
            "unused",
            "unused",
            "unused",
        )[0]
    )
    assert values["field"] == "asset"
    assert values["values"] == ["caption01"]

    versions = json.loads(
        BrowseGtst().browse(
            root_path,
            "versions",
            "",
            "project1",
            "texts",
            "caption01",
            "base",
            "default",
        )[0]
    )
    assert versions["versions"] == ["v001"]
