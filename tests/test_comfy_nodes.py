from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

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


def make_ref(
    tmp_path: Path,
    monkeypatch: Any,
    tree: str = "prompts",
    asset: str = "heroPrompt",
) -> dict[str, Any]:
    monkeypatch.setenv("GTST_ROOT", str(tmp_path / "root"))
    asset_ref, _, _ = GtstAssetRef().resolve(
        "project1",
        tree,
        asset,
        "base",
        "default",
        "",
        "",
    )
    return asset_ref


def test_text_nodes_asset_ref_tag_and_ready(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch)

    first_ref, first, first_metadata = SaveGtstText().save(
        "first prompt",
        asset_ref,
        "prompt.txt",
        False,
        "draft",
    )
    second_ref, second, second_metadata = SaveGtstText().save(
        "second prompt",
        asset_ref,
        "prompt.txt",
        True,
        "approved, favorite",
    )

    assert first_ref["version"] == "v001"
    assert second_ref["version"] == "v002"
    assert Path(first).read_text(encoding="utf-8") == "first prompt"
    assert Path(second).read_text(encoding="utf-8") == "second prompt"
    assert json.loads(first_metadata)["version"] == "v001"
    assert json.loads(second_metadata)["tags"] == ["approved", "favorite", "ready"]

    current_ref, ref_path, ref_metadata = GtstAssetRef().resolve(
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "",
        "",
    )
    assert ref_path == second
    assert current_ref["file_path"] == second
    assert json.loads(ref_metadata)["version"] == "v002"

    _, tagged_path, _ = GtstAssetRef().resolve(
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "",
        "draft",
    )
    assert tagged_path == first

    version_ref, _, _ = GtstAssetRef().resolve(
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "v001",
        "",
    )
    text, loaded_path, _ = LoadGtstText().load(version_ref)
    assert text == "first prompt"
    assert loaded_path == first

    ready_ref, ready_path, ready_metadata = MarkGtstReady().mark_ready(
        second_ref,
        "v001",
    )
    assert ready_ref["version"] == "v001"
    assert ready_path == first
    assert "ready" in json.loads(ready_metadata)["tags"]

    _, tagged_ready_path, tagged_ready_metadata = TagGtstVersion().tag_version(
        ready_ref,
        "v001",
        "selected",
    )
    assert tagged_ready_path == first
    assert "selected" in json.loads(tagged_ready_metadata)["tags"]


def test_video_nodes_publish_and_load_path(tmp_path: Path, monkeypatch: Any) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="videos", asset="shot01")
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake video")

    published_ref, published, metadata = SaveGtstVideo().save(
        str(source),
        asset_ref,
        True,
        "review",
    )

    assert published_ref["file_path"] == published
    assert Path(published).read_bytes() == b"fake video"
    assert json.loads(metadata)["tags"] == ["ready", "review"]
    assert LoadGtstVideo().load(published_ref)[0] == published


def test_browse_lists_values_and_versions(tmp_path: Path, monkeypatch: Any) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    SaveGtstText().save(
        "caption",
        asset_ref,
        "",
        False,
        "",
    )

    values = json.loads(
        BrowseGtst().browse(
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


def test_asset_ref_inputs_use_searchable_dropdown_values(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="images", asset="heroImage")
    SaveGtstText().save("placeholder", asset_ref, "", False, "")

    inputs = GtstAssetRef.INPUT_TYPES()["required"]

    assert "root_path" not in inputs
    assert "project1" in inputs["project"][0]
    assert "images" in inputs["tree"][0]
    assert "heroImage" in inputs["asset"][0]
    assert "base" in inputs["variant"][0]
    assert "default" in inputs["subvariant"][0]
