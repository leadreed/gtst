from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

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
    add_tag_payload,
    browser_results_payload,
    facet_suggestions_payload,
    _os_action_path,
    path_action_payload,
    resolve_path_action_payload,
    schema_metadata_payload,
    selected_browser_asset,
    set_ready_payload,
)
from gtst import GtstRoot


def path_endswith(path: str, suffix: str) -> bool:
    return path.replace("\\", "/").endswith(suffix)


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
        project="project1",
        tree=tree,
        asset=asset,
        variant="base",
        subVariant="default",
        version="",
        tag="",
    )["result"][0]
    return asset_ref


class FakeVideo:
    def __init__(self, payload: bytes = b"fake video") -> None:
        self.payload = payload
        self.saved_path: str | None = None
        self.saved_format: Any = None
        self.saved_codec: str | None = None
        self.saved_metadata: dict[str, Any] | None = None

    def save_to(
        self,
        path: str,
        format: Any,
        codec: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        self.saved_path = path
        self.saved_format = format
        self.saved_codec = codec
        self.saved_metadata = metadata
        Path(path).write_bytes(self.payload)


def test_asset_ref_resolve_has_no_preview_ui(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("GTST_ROOT", str(tmp_path / "root"))

    result = GtstAssetRef().resolve(
        project="project1",
        tree="images",
        asset="heroImage",
        variant="base",
        subVariant="default",
        version="",
        tag="",
    )

    assert "ui" not in result
    assert result["result"][1] == ""


def test_asset_ref_missing_explicit_version_errors(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch)
    SaveGtstText().save("first prompt", asset_ref, "", False, "")

    with pytest.raises(Exception, match="Version folder does not exist"):
        GtstAssetRef().resolve(
            project="project1",
            tree="prompts",
            asset="heroPrompt",
            variant="base",
            subVariant="default",
            version="v999",
            tag="",
        )


def test_pathless_asset_ref_honors_requested_version(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch)
    SaveGtstText().save("first prompt", asset_ref, "", False, "")
    SaveGtstText().save("second prompt", asset_ref, "", False, "")

    pathless_ref = {
        **asset_ref,
        "requested_version": "v999",
        "file_path": "",
    }

    with pytest.raises(Exception, match="Version folder does not exist"):
        LoadGtstText().load(pathless_ref)


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
        project="project1",
        tree="prompts",
        asset="heroPrompt",
        variant="base",
        subVariant="default",
        version="",
        tag="",
    )["result"]
    assert ref_path == second
    assert current_ref["file_path"] == second
    assert json.loads(ref_metadata)["version"] == "v002"

    _, tagged_path, _ = GtstAssetRef().resolve(
        project="project1",
        tree="prompts",
        asset="heroPrompt",
        variant="base",
        subVariant="default",
        version="",
        tag="draft",
    )["result"]
    assert tagged_path == first

    version_ref, _, _ = GtstAssetRef().resolve(
        project="project1",
        tree="prompts",
        asset="heroPrompt",
        variant="base",
        subVariant="default",
        version="v001",
        tag="",
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


def test_dynamic_asset_ref_re_resolves_when_ready_moves(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch)
    first = SaveGtstText().save("first prompt", asset_ref, "", False, "")["result"][1]
    second_ref = SaveGtstText().save("second prompt", asset_ref, "", True, "")[
        "result"
    ][0]

    current_ref = GtstAssetRef().resolve(
        project="project1",
        tree="prompts",
        asset="heroPrompt",
        variant="base",
        subVariant="default",
        version="",
        tag="",
    )["result"][0]
    before = GtstAssetRef.IS_CHANGED(
        project="project1",
        tree="prompts",
        asset="heroPrompt",
        variant="base",
        subVariant="default",
        version="",
        tag="",
    )

    MarkGtstReady().mark_ready(second_ref, "v001")
    after = GtstAssetRef.IS_CHANGED(
        project="project1",
        tree="prompts",
        asset="heroPrompt",
        variant="base",
        subVariant="default",
        version="",
        tag="",
    )

    text, loaded_path, _ = LoadGtstText().load(current_ref)
    assert before != after
    assert loaded_path == first
    assert text == "first prompt"


def test_video_nodes_publish_and_load_video(tmp_path: Path, monkeypatch: Any) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="videos", asset="shot01")
    video = FakeVideo()
    prompt = {"1": {"class_type": "CreateVideo"}}
    extra_pnginfo = {"workflow": {"nodes": []}}

    result = SaveGtstVideo().save(
        video,
        asset_ref,
        "",
        "mp4",
        "h264",
        True,
        "review",
        prompt=prompt,
        extra_pnginfo=extra_pnginfo,
    )
    published_ref, published, metadata = result["result"]

    assert published_ref["file_path"] == published
    assert result["ui"]["animated"] == (True,)
    assert result["ui"]["images"][0]["type"] == "temp"
    assert video.saved_path is not None
    assert video.saved_path.endswith("shot01.mp4")
    assert video.saved_format == "mp4"
    assert video.saved_codec == "h264"
    assert video.saved_metadata == {"workflow": {"nodes": []}, "prompt": prompt}
    assert Path(published).read_bytes() == b"fake video"
    assert json.loads(metadata)["tags"] == ["ready", "review"]
    assert LoadGtstVideo().load(published_ref)["result"][0] == published


def test_browser_current_prefers_ready_then_latest(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    first_ref, first_path, _, _ = SaveGtstText().save(
        "first caption",
        asset_ref,
        "",
        False,
        "",
    )["result"]
    second_ref, second_path, _, _ = SaveGtstText().save(
        "second caption",
        asset_ref,
        "",
        False,
        "",
    )["result"]

    current = browser_results_payload("current", {"project": "project1"})
    assert [item["file_path"] for item in current["items"]] == [second_path]

    MarkGtstReady().mark_ready(second_ref, "v001")
    ready = browser_results_payload("current", {"project": "project1"})
    assert [item["file_path"] for item in ready["items"]] == [first_path]
    assert ready["items"][0]["asset_ref"]["version"] == first_ref["version"]


def test_browser_latest_only_ignores_ready(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    SaveGtstText().save("first caption", asset_ref, "", False, "")
    second_path = SaveGtstText().save(
        "second caption",
        asset_ref,
        "",
        False,
        "",
    )["result"][1]
    MarkGtstReady().mark_ready(asset_ref, "v001")

    payload = browser_results_payload("latest only", {"project": "project1"})

    assert [item["file_path"] for item in payload["items"]] == [second_path]


def test_browser_all_versions_and_tag_filter(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    first_path = SaveGtstText().save("first", asset_ref, "", False, "")["result"][1]
    second_path = SaveGtstText().save("second", asset_ref, "", False, "")["result"][1]
    TagGtstVersion().tag_version(asset_ref, "v001", "selected")

    values = {
        "project": "project1",
        "tree": "texts",
        "asset": "caption01",
    }
    all_versions = browser_results_payload("all versions", values)
    assert [item["file_path"] for item in all_versions["items"]] == [
        first_path,
        second_path,
    ]

    tagged = browser_results_payload("all versions", {**values, "tag": "selected"})
    assert [item["file_path"] for item in tagged["items"]] == [first_path]


def test_browser_filters_by_multiple_tags_using_default_or(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    first_path = SaveGtstText().save("first", asset_ref, "", False, "favorite")[
        "result"
    ][1]
    second_path = SaveGtstText().save(
        "second",
        asset_ref,
        "",
        False,
        "favorite, selected",
    )["result"][1]
    third_path = SaveGtstText().save("third", asset_ref, "", False, "selected")[
        "result"
    ][1]

    values = {
        "project": "project1",
        "tree": "texts",
        "asset": "caption01",
        "tag": "favorite, selected",
    }
    all_versions = browser_results_payload("all versions", values)
    latest = browser_results_payload("latest only", values)

    assert first_path != second_path
    assert [item["file_path"] for item in all_versions["items"]] == [
        first_path,
        second_path,
        third_path,
    ]
    assert [item["file_path"] for item in latest["items"]] == [third_path]
    assert all_versions["tag_filter_mode"] == "OR"


def test_browser_filters_by_multiple_tags_using_and(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    first_path = SaveGtstText().save("first", asset_ref, "", False, "favorite")[
        "result"
    ][1]
    second_path = SaveGtstText().save(
        "second",
        asset_ref,
        "",
        False,
        "favorite, selected",
    )["result"][1]
    SaveGtstText().save("third", asset_ref, "", False, "selected")

    values = {
        "project": "project1",
        "tree": "texts",
        "asset": "caption01",
        "tag": "favorite, selected",
        "tag_filter_mode": "AND",
    }
    all_versions = browser_results_payload("all versions", values)
    latest = browser_results_payload("latest only", values)

    assert first_path != second_path
    assert [item["file_path"] for item in all_versions["items"]] == [second_path]
    assert [item["file_path"] for item in latest["items"]] == []
    assert all_versions["tag_filter_mode"] == "AND"


def test_browser_tag_filter_narrows_latest_only_mode(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    first_ref, first_path, _, _ = SaveGtstText().save(
        "first",
        asset_ref,
        "",
        False,
        "",
    )["result"]
    SaveGtstText().save("second", asset_ref, "", False, "")
    MarkGtstReady().mark_ready(first_ref, "v001")

    values = {
        "project": "project1",
        "tree": "texts",
        "asset": "caption01",
        "tag": "ready",
    }
    all_versions = browser_results_payload("all versions", values)
    latest = browser_results_payload("latest only", values)

    assert [item["file_path"] for item in all_versions["items"]] == [first_path]
    assert [item["file_path"] for item in latest["items"]] == []


def test_browser_ready_tag_filter_only_returns_ready_version(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    first_path = SaveGtstText().save("first", asset_ref, "", False, "")["result"][1]
    second_path = SaveGtstText().save("second", asset_ref, "", True, "")["result"][1]

    values = {
        "project": "project1",
        "tree": "texts",
        "asset": "caption01",
        "tag": "ready",
    }
    ready = browser_results_payload("all versions", values)
    all_versions = browser_results_payload(
        "all versions",
        {
            "project": "project1",
            "tree": "texts",
            "asset": "caption01",
        },
    )

    assert [item["file_path"] for item in ready["items"]] == [second_path]
    assert all_versions["items"][0]["file_path"] == first_path
    assert "ready" not in all_versions["items"][0]["tags"]
    assert all_versions["items"][1]["file_path"] == second_path
    assert "ready" in all_versions["items"][1]["tags"]


def test_browser_multi_tag_filter_supports_ready(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    SaveGtstText().save("first", asset_ref, "", False, "favorite")
    second_path = SaveGtstText().save("second", asset_ref, "", True, "favorite")[
        "result"
    ][1]

    values = {
        "project": "project1",
        "tree": "texts",
        "asset": "caption01",
        "tag": "ready, favorite",
        "tag_filter_mode": "AND",
    }
    payload = browser_results_payload("all versions", values)

    assert [item["file_path"] for item in payload["items"]] == [second_path]


def test_browser_wildcards_text_preview_and_cap(
    tmp_path: Path, monkeypatch: Any
) -> None:
    first_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    second_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption02")
    long_text = "word " * 200
    SaveGtstText().save(long_text, first_ref, "", False, "")
    SaveGtstText().save("short", second_ref, "", False, "")

    payload = browser_results_payload(
        "latest only", {"project": "project1", "tree": "texts"}, limit=1
    )

    assert payload["capped"] is True
    assert len(payload["items"]) == 1
    assert payload["items"][0]["media_type"] == "text"
    assert len(payload["items"][0]["preview_text"]) <= 503
    assert payload["items"][0]["preview_text"].endswith("...")


def test_browser_selection_reconstructs_asset_ref(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    saved = SaveGtstText().save("caption", asset_ref, "", False, "")["result"][1]

    result = BrowseGtst().browse(
        mode="latest only",
        project="project1",
        tree="texts",
        asset="caption01",
        variant="",
        subVariant="",
        version="",
        tag="",
        tag_filter_mode="OR",
        selected_file_path=saved,
        preview_item_size=140,
    )

    selected_ref, selected_path, selected_metadata = result["result"]
    assert selected_path == saved
    assert selected_ref["file_path"] == saved
    assert selected_ref["version"] == "v001"
    assert json.loads(selected_metadata)["facets"]["asset"] == "caption01"


def test_browser_selection_requires_file(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("GTST_ROOT", str(tmp_path / "root"))

    try:
        selected_browser_asset("")
    except ValueError as exc:
        assert "No GTST browser preview selected" in str(exc)
    else:
        raise AssertionError("expected missing browser selection to fail")


def test_resolve_path_action_reveals_deepest_existing_facet_path(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    saved = SaveGtstText().save("caption", asset_ref, "", False, "")["result"][1]
    opened: list[tuple[str, Path]] = []

    monkeypatch.setattr(
        "comfy_nodes._os_action_path",
        lambda action, path: opened.append((action, Path(path))),
    )

    partial = resolve_path_action_payload(
        "reveal",
        {"project": "project1", "tree": "texts", "asset": "missing"},
    )
    assert path_endswith(partial["path"], "/project1/texts")
    assert opened[-1] == ("reveal", Path(partial["path"]))

    exact = resolve_path_action_payload(
        "reveal",
        {
            "project": "project1",
            "tree": "texts",
            "asset": "caption01",
            "variant": "base",
            "subVariant": "default",
        },
    )
    assert exact["path"] == saved
    assert opened[-1] == ("reveal", Path(saved))


def test_windows_reveal_selects_file_with_quoted_explorer_path(
    tmp_path: Path, monkeypatch: Any
) -> None:
    target = tmp_path / "folder with spaces, comma" / "asset file, final.txt"
    target.parent.mkdir()
    target.write_text("asset", encoding="utf-8")
    calls: list[tuple[list[str], bool]] = []

    monkeypatch.setattr("comfy_nodes.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "comfy_nodes.subprocess.run",
        lambda command, check: calls.append((command, check)),
    )

    _os_action_path("reveal", target)

    assert calls == [(["explorer.exe", f'/select,"{target.resolve()}"'], False)]


def test_windows_reveal_opens_folder_with_explorer_exe(
    tmp_path: Path, monkeypatch: Any
) -> None:
    target = tmp_path / "folder with spaces, comma"
    target.mkdir()
    calls: list[tuple[list[str], bool]] = []

    monkeypatch.setattr("comfy_nodes.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "comfy_nodes.subprocess.run",
        lambda command, check: calls.append((command, check)),
    )

    _os_action_path("reveal", target)

    assert calls == [(["explorer.exe", str(target.resolve())], False)]


def test_path_action_is_scoped_to_gtst_root(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("GTST_ROOT", str(tmp_path / "root"))
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="inside GTST_ROOT"):
        path_action_payload("open", str(outside))


def test_set_ready_payload_marks_browser_item_ready(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    first = SaveGtstText().save("first", asset_ref, "", False, "")["result"][1]
    second = SaveGtstText().save("second", asset_ref, "", True, "")["result"][1]

    payload = set_ready_payload(first)

    assert payload["ok"] is True
    assert payload["path"] == first
    assert payload["metadata"]["is_ready"] is True
    current = browser_results_payload("current", {"project": "project1"})
    assert [item["file_path"] for item in current["items"]] == [first]
    assert current["items"][0]["file_path"] != second


def test_add_tag_payload_tags_browser_item(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    saved = SaveGtstText().save("first", asset_ref, "", False, "")["result"][1]

    payload = add_tag_payload(saved, "favorite")

    assert payload["ok"] is True
    assert payload["path"] == saved
    assert payload["tag"] == "favorite"
    assert "favorite" in payload["metadata"]["tags"]
    tagged = browser_results_payload(
        "all versions",
        {"project": "project1", "tag": "favorite"},
    )
    assert [item["file_path"] for item in tagged["items"]] == [saved]


def test_add_tag_payload_rejects_empty_tag(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="texts", asset="caption01")
    saved = SaveGtstText().save("first", asset_ref, "", False, "")["result"][1]

    with pytest.raises(ValueError, match="tag cannot be empty"):
        add_tag_payload(saved, " ")


def test_facet_suggestions_are_hierarchy_aware(
    tmp_path: Path, monkeypatch: Any
) -> None:
    first_ref = make_ref(tmp_path, monkeypatch, tree="images", asset="hero")
    SaveGtstText().save("placeholder", first_ref, "", False, "")
    second_ref = make_ref(tmp_path, monkeypatch, tree="prompts", asset="caption")
    SaveGtstText().save("placeholder", second_ref, "", False, "")

    project_payload = facet_suggestions_payload("project", {})
    tree_payload = facet_suggestions_payload("tree", {"project": "project1"})
    asset_payload = facet_suggestions_payload(
        "asset", {"project": "project1", "tree": "images"}
    )

    assert project_payload["values"] == ["project1"]
    assert tree_payload["values"] == ["images", "prompts"]
    assert asset_payload["values"] == ["hero"]


def test_facet_suggestions_return_empty_for_missing_prior_facets(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="images", asset="hero")
    SaveGtstText().save("placeholder", asset_ref, "", False, "")

    assert facet_suggestions_payload("tree", {})["values"] == []
    assert facet_suggestions_payload("asset", {"project": "project1"})["values"] == []


def test_facet_suggestions_use_exact_schema_field_names(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="images", asset="hero")
    SaveGtstText().save("placeholder", asset_ref, "", False, "")

    payload = facet_suggestions_payload(
        "subVariant",
        {
            "project": "project1",
            "tree": "images",
            "asset": "hero",
            "variant": "base",
        },
    )

    assert payload["schema_field"] == "subVariant"
    assert payload["facets"] == {
        "project": "project1",
        "tree": "images",
        "asset": "hero",
        "variant": "base",
    }
    assert payload["values"] == ["default"]


def test_asset_ref_suggestions_include_versions_and_tags(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="images", asset="hero")
    SaveGtstText().save("first", asset_ref, "", False, "")
    SaveGtstText().save("second", asset_ref, "", False, "")
    TagGtstVersion().tag_version(asset_ref, "v001", "selected")

    values = {
        "project": "project1",
        "tree": "images",
        "asset": "hero",
        "variant": "base",
        "subVariant": "default",
    }

    assert facet_suggestions_payload("version", values)["values"] == ["v001", "v002"]
    assert facet_suggestions_payload("tag", values)["values"] == ["selected"]
    assert (
        facet_suggestions_payload("tag", {**values, "version": "v001"})["values"]
        == ["selected"]
    )


def test_version_suggestions_return_empty_for_incomplete_facets(
    tmp_path: Path, monkeypatch: Any
) -> None:
    asset_ref = make_ref(tmp_path, monkeypatch, tree="images", asset="hero")
    SaveGtstText().save("placeholder", asset_ref, "", False, "")

    assert facet_suggestions_payload("version", {"project": "project1"})["values"] == []


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
    assert inputs["subVariant"][0] == "STRING"
    assert inputs["variant"][1]["default"] == ""
    assert inputs["subVariant"][1]["default"] == ""
    assert inputs["tree"][1]["gtstFacetValues"] == ["newTree"]
    assert inputs["asset"][1]["gtstFacetValues"] == ["newAsset"]
    assert "assets" not in inputs["tree"][1]["gtstFacetValues"]
    assert "images" not in inputs["tree"][1]["gtstFacetValues"]


def test_nodes_use_custom_schema_exact_field_names(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = GtstRoot.create(
        tmp_path / "root",
        schema=["show", "shot", "name"],
        default_filename_facet="name",
    )
    monkeypatch.setenv("GTST_ROOT", str(root.path))

    inputs = GtstAssetRef.INPUT_TYPES()["required"]
    assert {"show", "shot", "name", "version", "tag"} <= set(inputs)
    assert "project" not in inputs
    assert "subvariant" not in inputs
    assert "subVariant" not in inputs

    asset_ref = GtstAssetRef().resolve(
        show="demo",
        shot="shot010",
        name="plateMain",
        version="",
        tag="",
    )["result"][0]
    result = SaveGtstText().save("plate notes", asset_ref, "", False, "")
    published = result["result"][1]

    assert path_endswith(published, "/demo/shot010/plateMain/v001/plateMain.txt")
    assert json.loads(result["result"][2])["facets"] == {
        "show": "demo",
        "shot": "shot010",
        "name": "plateMain",
    }


def test_schema_metadata_payload_uses_active_root_schema(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = GtstRoot.create(
        tmp_path / "root",
        schema=["show", "shot", "name"],
        default_filename_facet="name",
    )
    monkeypatch.setenv("GTST_ROOT", str(root.path))

    payload = schema_metadata_payload()

    assert payload["schema"] == ["show", "shot", "name"]
    assert payload["facet_fields"] == ["show", "shot", "name"]
    assert payload["suggestion_fields"] == ["show", "shot", "name", "version", "tag"]
    assert payload["default_filename_facet"] == "name"
    assert payload["ready_tag_name"] == "ready"
    assert payload["browser_tag_filter_modes"] == ["OR", "AND"]


def test_default_filename_facet_errors_when_unresolved(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = GtstRoot.create(
        tmp_path / "root",
        schema=["show", "shot", "name"],
        default_filename_facet="name",
    )
    monkeypatch.setenv("GTST_ROOT", str(root.path))
    asset_ref = {
        "root_path": str(root.path),
        "facets": {"show": "demo", "shot": "shot010", "name": ""},
        "version": "",
        "requested_version": "",
        "requested_tag": "",
        "file_path": "",
        "metadata": {},
    }

    with pytest.raises(ValueError, match="Default filename facet"):
        SaveGtstText().save("plate notes", asset_ref, "", False, "")
