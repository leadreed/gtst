# GSTS

GSTS is a Python filesystem asset manager for small studios that need simple versioning and tagging for generated text, images, videos, and arbitrary files.

The system stores assets directly in folders. There is no database, no hidden index, and no content parsing. Published assets are normal files in version folders, and tags are normal `.gtst` files.

## Status

This repository contains the first Python API implementation. A CLI can be layered on top of the same API later.

## Filesystem Layout

A GSTS root contains a required `gtst.json` config file and one or more projects:

```text
myGTSTroot/
  gtst.json
  project1/
    assets/
      simpleBox/
        base/
          default/
            v001/
              simpleBox.txt
            v002/
              simpleBox.txt
            gtst_tags/
              ready/
                gtstTag001_ready_001.gtst
                gtstTag002_ready_002.gtst
```

The default schema is:

```python
["project", "tree", "asset", "variant", "subVariant"]
```

The schema maps directly to folders beneath the GSTS root.

## Basic Usage

```python
from gsts import GstsRoot

root = GstsRoot.create("/path/to/myGTSTroot")

published = root.publish(
    source="/tmp/simpleBox.txt",
    project="project1",
    tree="assets",
    asset="simpleBox",
    variant="base",
    subVariant="default",
)

latest = root.get_latest(
    project="project1",
    tree="assets",
    asset="simpleBox",
    variant="base",
    subVariant="default",
)
```

Both `published` and `latest` are absolute filesystem paths to the asset file.

Facet values can also be passed as a dictionary:

```python
facets = {
    "project": "project1",
    "tree": "assets",
    "asset": "simpleBox",
    "variant": "base",
    "subVariant": "default",
}

root.publish(source="/tmp/simpleBox.txt", facets=facets)
```

## Tags

GSTS supports two tag types.

Single-version tags can exist on only one version of an asset at a time. The built-in `ready` tag is single-version:

```python
root.tag_version("ready", version="v002", **facets)
ready_file = root.get_tagged_version("ready", **facets)
```

Single-version tag history is stored at the asset level:

```text
gtst_tags/
  ready/
    gtstTag001_ready_001.gtst
    gtstTag002_ready_002.gtst
```

Multi-version tags can exist on many versions:

```python
root.tag_version("favorite", version="v001", **facets)
root.tag_version("favorite", version="v002", **facets)
favorite_files = root.find_by_tag("favorite", **facets)
```

Multi-version tags are stored inside each version folder:

```text
v001/
  simpleBox.txt
  gtst_tags/
    favorite.gtst
```

## Config

`gtst.json` is created with these defaults:

```json
{
  "schema": ["project", "tree", "asset", "variant", "subVariant"],
  "version_width": 3,
  "single_version_tags": ["ready"]
}
```

The version width controls folder names such as `v001`.

## Design Notes

- GSTS publishes one file per version.
- Publish preserves the source filename.
- Publish never overwrites existing version folders or files.
- Malformed version folders are ignored.
- Retrieval returns an error if the requested version folder has zero asset files or more than one direct asset file.
- Tags are ignored if their format does not match GSTS rules.
- Facet values and tag names must use only letters, numbers, underscore, dash, and dot.
