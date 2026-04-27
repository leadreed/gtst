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
    asset_ref = GtstAssetRef().resolve(
        "project1",
        tree,
        asset,
        "base",
        "default",
        "",
        "",
    )["result"][0]
    return asset_ref


def test_asset_ref_resolve_has_no_preview_ui(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("GTST_ROOT", str(tmp_path / "root"))

    result = GtstAssetRef().resolve(
        "project1",
        "images",
        "heroImage",
        "base",
        "default",
        "",
        "",
    )

    assert "ui" not in result
    assert result["result"][1] == ""


def test_text_nodes_asset_ref_tag_and_ready(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch)

    first_result = SaveGtstText().save(
        "first prompt",
        asset_ref,
        "prompt.txt",
        False,
        "draft",
    )
    first_ref, first, first_metadata, _ = first_result["result"]
    second_result = SaveGtstText().save(
        "second prompt",
        asset_ref,
        "prompt.txt",
        True,
        "approved, favorite",
    )
    second_ref, second, second_metadata, _ = second_result["result"]

    assert first_ref["version"] == "v001"
    assert second_ref["version"] == "v002"
    assert "ui" not in first_result
    assert "ui" not in second_result
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
    )["result"]
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
    )["result"]
    assert tagged_path == first

    version_ref, _, _ = GtstAssetRef().resolve(
        "project1",
        "prompts",
        "heroPrompt",
        "base",
        "default",
        "v001",
        "",
    )["result"]
    text, loaded_path, _ = LoadGtstText().load(version_ref)
    assert text == "first prompt"
    assert loaded_path == first

    ready_ref, ready_path, ready_metadata = MarkGtstReady().mark_ready(
        second_ref,
        "v001",
    )["result"]
    assert ready_ref["version"] == "v001"
    assert ready_path == first
    assert "ready" in json.loads(ready_metadata)["tags"]

    _, tagged_ready_path, tagged_ready_metadata = TagGtstVersion().tag_version(
        ready_ref,
        "v001",
        "selected",
    )["result"]
    assert tagged_ready_path == first
    assert "selected" in json.loads(tagged_ready_metadata)["tags"]


def test_video_nodes_publish_and_load_path(tmp_path: Path, monkeypatch: Any) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="videos", asset="shot01")
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake video")

    result = SaveGtstVideo().save(
        str(source),
        asset_ref,
        True,
        "review",
    )
    published_ref, published, metadata = result["result"]

    assert published_ref["file_path"] == published
    assert result["ui"]["animated"] == (True,)
    assert result["ui"]["images"][0]["type"] == "temp"
    assert Path(published).read_bytes() == b"fake video"
    assert json.loads(metadata)["tags"] == ["ready", "review"]
    assert LoadGtstVideo().load(published_ref)["result"][0] == published


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


def test_asset_ref_inputs_are_strings_with_existing_facet_values_only(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="newTree", asset="newAsset")
    SaveGtstText().save("placeholder", asset_ref, "", False, "")

    inputs = GtstAssetRef.INPUT_TYPES()["required"]

    assert "root_path" not in inputs
    assert inputs["project"][0] == "STRING"
    assert inputs["tree"][0] == "STRING"
    assert inputs["asset"][0] == "STRING"
    assert inputs["variant"][0] == "STRING"
    assert inputs["subvariant"][0] == "STRING"
    assert inputs["variant"][1]["default"] == "base"
    assert inputs["subvariant"][1]["default"] == "default"
    assert inputs["tree"][1]["gtstFacetValues"] == ["newTree"]
    assert inputs["asset"][1]["gtstFacetValues"] == ["newAsset"]
    assert "assets" not in inputs["tree"][1]["gtstFacetValues"]
    assert "images" not in inputs["tree"][1]["gtstFacetValues"]
