"""Command line interface for GSTS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Sequence

from .errors import GstsError, GstsTagError
from .root import GstsRoot

VERSION_QUERY_PATTERN = re.compile(r"^v\d+$")


class CliError(Exception):
    """Raised for CLI input errors."""


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (CliError, GstsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gsts",
        description="Filesystem-native asset versioning.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a GSTS root.")
    init_parser.add_argument("root")
    init_parser.set_defaults(func=_cmd_init)

    publish_parser = subparsers.add_parser("publish", help="Publish a file.")
    publish_parser.add_argument("source")
    publish_parser.add_argument("asset_query")
    publish_parser.add_argument(
        "--ready",
        action="store_true",
        help="Mark the published version as ready.",
    )
    publish_parser.set_defaults(func=_cmd_publish)

    ready_parser = subparsers.add_parser("ready", help="Mark a version ready.")
    ready_parser.add_argument("target")
    ready_parser.set_defaults(func=_cmd_ready)

    tag_parser = subparsers.add_parser("tag", help="Tag a version.")
    tag_parser.add_argument("tag")
    tag_parser.add_argument("target")
    tag_parser.set_defaults(func=_cmd_tag)

    latest_parser = subparsers.add_parser("latest", help="Print the latest asset file.")
    latest_parser.add_argument("asset_query")
    latest_parser.set_defaults(func=_cmd_latest)

    get_parser = subparsers.add_parser("get", help="Print a versioned asset file.")
    get_parser.add_argument("version_query")
    get_parser.set_defaults(func=_cmd_get)

    tagged_parser = subparsers.add_parser(
        "tagged", help="Print the latest asset file with a tag."
    )
    tagged_parser.add_argument("tag")
    tagged_parser.add_argument("asset_query")
    tagged_parser.set_defaults(func=_cmd_tagged)

    versions_parser = subparsers.add_parser("versions", help="List asset versions.")
    versions_parser.add_argument("asset_query")
    versions_parser.set_defaults(func=_cmd_versions)

    values_parser = subparsers.add_parser("values", help="List child facet values.")
    values_parser.add_argument("partial_query", nargs="?")
    values_parser.set_defaults(func=_cmd_values)

    info_parser = subparsers.add_parser("info", help="Show GSTS info for targets.")
    info_parser.add_argument("--json", action="store_true", dest="as_json")
    info_parser.add_argument("targets", nargs="+")
    info_parser.set_defaults(func=_cmd_info)

    return parser


def _cmd_init(args: argparse.Namespace) -> None:
    root = GstsRoot.create(args.root)
    print(f"GSTS root: {root.path}")
    print("Set it as your active root:")
    print(f"export GSTS_ROOT={root.path}")


def _cmd_publish(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    facets = _parse_asset_query(root, args.asset_query)
    published = root.publish(args.source, facets=facets)
    if args.ready:
        version = root.version_from_path(published)
        root.tag_version(root.config.ready_tag_name, version=version, facets=facets)
    print(published)


def _cmd_ready(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    facets, version = _parse_version_target(root, args.target)
    root.tag_version(root.config.ready_tag_name, version=version, facets=facets)
    print(root.get_version(version=version, facets=facets))


def _cmd_tag(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    facets, version = _parse_version_target(root, args.target)
    root.tag_version(args.tag, version=version, facets=facets)
    print(root.get_version(version=version, facets=facets))


def _cmd_latest(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    facets = _parse_asset_query(root, args.asset_query)
    print(root.get_latest(facets=facets))


def _cmd_get(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    facets, version = _parse_version_query(root, args.version_query)
    print(root.get_version(version=version, facets=facets))


def _cmd_tagged(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    facets = _parse_asset_query(root, args.asset_query)
    print(root.get_latest_by_tag(args.tag, facets=facets))


def _cmd_versions(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    facets = _parse_asset_query(root, args.asset_query)
    for version in root.list_versions(facets=facets):
        print(version)


def _cmd_values(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    parts = _parse_query_parts(args.partial_query or "")
    if len(parts) >= len(root.config.schema):
        raise CliError("values expects a partial query. Use 'gsts versions' for versions.")
    facets = dict(zip(root.config.schema, parts))
    field = root.config.schema[len(parts)]
    for value in root.list_values(field, facets=facets):
        print(value)


def _cmd_info(args: argparse.Namespace) -> None:
    root = _load_root_from_env()
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []

    for target in args.targets:
        try:
            results.append(_info_for_target(root, target))
        except (CliError, GstsError) as exc:
            errors.append({"target": target, "error": str(exc)})

    if args.as_json:
        print(json.dumps({"results": results, "errors": errors}, indent=2))
    else:
        for index, result in enumerate(results):
            if index:
                print()
            _print_info_result(result)
        for error in errors:
            print(f"error: {error['target']}: {error['error']}", file=sys.stderr)

    if errors:
        raise CliError(f"{len(errors)} target(s) failed")


def _load_root_from_env() -> GstsRoot:
    return GstsRoot.from_env()


def _parse_query_parts(query: str) -> list[str]:
    if not query:
        return []
    if query.startswith("/") or query.endswith("/"):
        raise CliError("queries must be relative to GSTS_ROOT and cannot start or end with '/'.")
    parts = query.split("/")
    if any(part == "" for part in parts):
        raise CliError("queries cannot contain empty path parts.")
    return parts


def _parse_asset_query(root: GstsRoot, query: str) -> dict[str, str]:
    parts = _parse_query_parts(query)
    expected = len(root.config.schema)
    if len(parts) != expected:
        raise CliError(
            f"expected asset query with {expected} parts: {_schema_query(root)}"
        )
    return dict(zip(root.config.schema, parts))


def _parse_version_query(root: GstsRoot, query: str) -> tuple[dict[str, str], str]:
    parts = _parse_query_parts(query)
    expected = len(root.config.schema) + 1
    if len(parts) != expected:
        raise CliError(
            f"expected version query with {expected} parts: {_schema_query(root)}/v001"
        )
    version = parts[-1]
    if VERSION_QUERY_PATTERN.fullmatch(version) is None:
        raise CliError("version query must end with a v-prefixed version, such as v2 or v002.")
    return dict(zip(root.config.schema, parts[:-1])), version


def _parse_version_target(root: GstsRoot, target: str) -> tuple[dict[str, str], str]:
    target_path = Path(target).expanduser()
    if target_path.is_absolute():
        facets = root.facets_from_path(target_path)
        version = root.version_from_path(target_path)
        return facets, version
    return _parse_version_query(root, target)


def _info_for_target(root: GstsRoot, target: str) -> dict[str, object]:
    target_path = Path(target).expanduser()
    if target_path.is_absolute():
        facets = root.facets_from_path(target_path)
        version = root.version_from_path(target_path)
        resolved_by = "path"
        asset_file = root.get_version(version=version, facets=facets)
        return _build_info_result(root, target, asset_file, facets, version, resolved_by)

    parts = _parse_query_parts(target)
    if len(parts) == len(root.config.schema):
        facets = _parse_asset_query(root, target)
        try:
            asset_file = root.get_latest_by_tag(root.config.ready_tag_name, facets=facets)
            resolved_by = root.config.ready_tag_name
        except GstsTagError:
            asset_file = root.get_latest(facets=facets)
            resolved_by = "latest"
        version = root.version_from_path(asset_file)
        return _build_info_result(root, target, asset_file, facets, version, resolved_by)

    facets, version = _parse_version_query(root, target)
    asset_file = root.get_version(version=version, facets=facets)
    normalized_version = root.version_from_path(asset_file)
    return _build_info_result(
        root, target, asset_file, facets, normalized_version, "version"
    )


def _build_info_result(
    root: GstsRoot,
    target: str,
    asset_file: str,
    facets: dict[str, str],
    version: str,
    resolved_by: str,
) -> dict[str, object]:
    query = "/".join(facets[field] for field in root.config.schema)
    version_query = f"{query}/{version}"
    return {
        "target": target,
        "path": asset_file,
        "root": str(root.path),
        "query": query,
        "version_query": version_query,
        "asset_dir": root.asset_dir(facets=facets).as_posix(),
        "version": version,
        "version_dir": root.version_dir(root.asset_dir(facets=facets), version).as_posix(),
        "resolved_by": resolved_by,
        "facets": facets,
    }


def _print_info_result(result: dict[str, object]) -> None:
    for key in [
        "target",
        "path",
        "root",
        "query",
        "version_query",
        "asset_dir",
        "version",
        "version_dir",
        "resolved_by",
    ]:
        print(f"{key}: {result[key]}")
    facets = result["facets"]
    if isinstance(facets, dict):
        for key, value in facets.items():
            print(f"{key}: {value}")


def _schema_query(root: GstsRoot) -> str:
    return "/".join(root.config.schema)


if __name__ == "__main__":
    raise SystemExit(main())
