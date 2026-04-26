from __future__ import annotations

import json
from pathlib import Path

import pytest

from gsts import (
    GstsConfigError,
    GstsPathError,
    GstsPublishError,
    GstsRoot,
    GstsTagError,
    GstsVersionError,
)


def write_source(tmp_path: Path, name: str = "simpleBox.txt", text: str = "box") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def facets() -> dict[str, str]:
    return {
        "project": "project1",
        "tree": "assets",
        "asset": "simpleBox",
        "variant": "base",
        "subVariant": "default",
    }


def test_create_writes_default_config(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")

    config_path = root.path / "gtst.json"
    assert config_path.is_file()
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "schema": ["project", "tree", "asset", "variant", "subVariant"],
        "version_width": 3,
        "single_version_tags": ["ready"],
    }


def test_open_requires_config(tmp_path: Path) -> None:
    empty_root = tmp_path / "root"
    empty_root.mkdir()

    with pytest.raises(GstsConfigError, match="config does not exist"):
        GstsRoot(empty_root)


def test_publish_allocates_versions_and_preserves_filename(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path, "simpleBox.txt", "v1")

    first = root.publish(source, facets=facets())
    source.write_text("v2", encoding="utf-8")
    second = root.publish(source, **facets())

    assert first.endswith("/project1/assets/simpleBox/base/default/v001/simpleBox.txt")
    assert second.endswith("/project1/assets/simpleBox/base/default/v002/simpleBox.txt")
    assert Path(first).read_text(encoding="utf-8") == "v1"
    assert Path(second).read_text(encoding="utf-8") == "v2"
    assert root.list_versions(**facets()) == ["v001", "v002"]


def test_publish_rejects_non_file_source(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")

    with pytest.raises(GstsPublishError, match="not a file"):
        root.publish(tmp_path, **facets())


def test_invalid_facet_names_are_rejected(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path)
    bad_facets = facets()
    bad_facets["asset"] = "bad asset"

    with pytest.raises(GstsPathError, match="letters, numbers"):
        root.publish(source, facets=bad_facets)


def test_get_latest_and_explicit_versions_return_asset_file(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path, text="v1")
    first = root.publish(source, **facets())
    source.write_text("v2", encoding="utf-8")
    second = root.publish(source, **facets())

    assert root.get_version(version=1, **facets()) == first
    assert root.get_version(version="v001", **facets()) == first
    assert root.get_latest(**facets()) == second


def test_malformed_version_folders_are_ignored(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path)
    first = root.publish(source, **facets())
    asset_dir = Path(root.asset_dir(**facets()))
    (asset_dir / "version-two").mkdir()
    (asset_dir / "vabc").mkdir()

    assert root.list_versions(**facets()) == ["v001"]
    assert root.get_latest(**facets()) == first


def test_retrieval_errors_for_empty_or_ambiguous_version_folder(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    asset_dir = root.asset_dir(**facets())
    (asset_dir / "v001").mkdir(parents=True)

    with pytest.raises(GstsVersionError, match="no asset file"):
        root.get_version(version=1, **facets())

    (asset_dir / "v001" / "one.txt").write_text("one", encoding="utf-8")
    (asset_dir / "v001" / "two.txt").write_text("two", encoding="utf-8")
    (asset_dir / "v001" / "nested").mkdir()

    with pytest.raises(GstsVersionError, match="more than one asset file"):
        root.get_version(version=1, **facets())


def test_single_version_tag_uses_asset_level_history(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path, text="v1")
    first = root.publish(source, **facets())
    source.write_text("v2", encoding="utf-8")
    second = root.publish(source, **facets())

    first_tag = root.tag_version("ready", version="v001", **facets())
    second_tag = root.tag_version("ready", version=2, **facets())

    assert first_tag.endswith("/gtst_tags/ready/gtstTag001_ready_001.gtst")
    assert second_tag.endswith("/gtst_tags/ready/gtstTag002_ready_002.gtst")
    assert root.get_tagged_version("ready", **facets()) == second
    assert root.find_by_tag("ready", **facets()) == [second]
    assert Path(first).is_file()


def test_multi_version_tags_live_inside_versions(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path, text="v1")
    first = root.publish(source, **facets())
    source.write_text("v2", encoding="utf-8")
    second = root.publish(source, **facets())

    tag_one = root.tag_version("favorite", version=1, **facets())
    tag_two = root.tag_version("favorite", version=2, **facets())

    assert tag_one.endswith("/v001/gtst_tags/favorite.gtst")
    assert tag_two.endswith("/v002/gtst_tags/favorite.gtst")
    assert root.find_by_tag("favorite", **facets()) == [first, second]
    assert root.list_tags(version=1, **facets()) == ["favorite"]


def test_single_version_tag_ignores_multi_version_tag_with_same_name(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path)
    root.publish(source, **facets())
    asset_dir = root.asset_dir(**facets())
    ready_dir = asset_dir / "v001" / "gtst_tags"
    ready_dir.mkdir()
    (ready_dir / "ready.gtst").touch()

    assert root.find_by_tag("ready", **facets()) == []
    with pytest.raises(GstsTagError, match="not set"):
        root.get_tagged_version("ready", **facets())


def test_custom_config_version_width_and_schema(tmp_path: Path) -> None:
    root = GstsRoot.create(
        tmp_path / "root",
        schema=["project", "asset"],
        version_width=4,
        single_version_tags=["approved"],
    )
    source = write_source(tmp_path)
    first = root.publish(source, project="p", asset="a")

    assert first.endswith("/p/a/v0001/simpleBox.txt")
    tag = root.tag_version("approved", version=1, project="p", asset="a")
    assert tag.endswith("/gtst_tags/approved/gtstTag0001_approved_0001.gtst")


def test_list_values_requires_prior_facets(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path)
    root.publish(source, **facets())

    assert root.list_values("project") == ["project1"]
    assert root.list_values("tree", project="project1") == ["assets"]
    with pytest.raises(GstsPathError, match="prior facet"):
        root.list_values("asset")


def test_path_helpers_resolve_facets_and_version(tmp_path: Path) -> None:
    root = GstsRoot.create(tmp_path / "root")
    source = write_source(tmp_path)
    published = root.publish(source, **facets())

    assert root.version_from_path(published) == "v001"
    assert root.facets_from_path(published) == facets()
    assert root.asset_dir_from_path(published).endswith(
        "/project1/assets/simpleBox/base/default"
    )
    assert root.version_dir_from_path(published).endswith(
        "/project1/assets/simpleBox/base/default/v001"
    )
