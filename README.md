# GSTS

GSTS is a Python filesystem asset manager for small studios that need simple
versioning and tagging for generated text, images, videos, and arbitrary files.

The system stores assets directly in folders. There is no database, no hidden
index, and no content parsing. Published assets are normal files in version
folders, and tags are normal `.gtst` files.

## Status

This repository contains the first Python API and CLI implementation.

## CLI Setup

Clone the repository, create a virtual environment, and install GSTS in editable
mode:

```bash
git clone <repo-url> gtst
cd gtst
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

Create a GSTS root:

```bash
gsts init /path/to/myGTSTroot
```

The command prints the root path and the environment variable to use:

```bash
GSTS root: /path/to/myGTSTroot
Set it as your active root:
export GSTS_ROOT=/path/to/myGTSTroot
```

Set that variable in your shell:

```bash
export GSTS_ROOT=/path/to/myGTSTroot
```

GSTS CLI commands use `GSTS_ROOT` as the active root. `gsts init ROOT` is the
only command that does not require it.

## CLI Usage

Publish a file to an asset:

```bash
gsts publish ./hero.png project1/assets/hero/base/default
```

Publish and mark the new version ready:

```bash
gsts publish ./hero.png project1/assets/hero/base/default --ready
```

Get the latest version:

```bash
gsts latest project1/assets/hero/base/default
```

Get a specific version:

```bash
gsts get project1/assets/hero/base/default/v001
gsts get project1/assets/hero/base/default/v1
```

Mark an existing version ready:

```bash
gsts ready project1/assets/hero/base/default/v001
gsts ready /path/to/myGTSTroot/project1/assets/hero/base/default/v001/hero.png
```

Tag an existing version:

```bash
gsts tag favorite project1/assets/hero/base/default/v001
gsts tag favorite /path/to/myGTSTroot/project1/assets/hero/base/default/v001/hero.png
```

Get the latest version carrying a tag:

```bash
gsts tagged favorite project1/assets/hero/base/default
```

List versions:

```bash
gsts versions project1/assets/hero/base/default
```

List child facet values:

```bash
gsts values
gsts values project1
gsts values project1/assets
gsts values project1/assets/hero
```

Show information for an asset, version, or file:

```bash
gsts info project1/assets/hero/base/default
gsts info project1/assets/hero/base/default/v001
gsts info /path/to/myGTSTroot/project1/assets/hero/base/default/v001/hero.png
gsts info --json project1/assets/hero/base/default
```

When `gsts info` receives an asset query without a version, it resolves the
ready version first. If no ready version exists, it falls back to latest.

## Query Forms

Asset queries are slash-form paths relative to `GSTS_ROOT`:

```text
project/tree/asset/variant/subVariant
```

Version queries add a `v`-prefixed version:

```text
project/tree/asset/variant/subVariant/v001
project/tree/asset/variant/subVariant/v1
```

Queries are not absolute filesystem paths. Commands that accept filesystem
paths, such as `info`, `ready`, and `tag`, require absolute paths inside
`GSTS_ROOT`.

## Filesystem Layout

A GSTS root contains a required `gtst.json` config file and one or more
projects:

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

## Ready Tag

GSTS has a first-class ready tag. By default, the ready tag is named `ready` and
is configured with:

```json
{
  "ready_tag_name": "ready"
}
```

The ready tag always behaves as a single-version tag. Setting a new ready version
makes that version the current ready version for the asset.

Additional single-version tags can be configured with `single_version_tags`.
Multi-version tags do not need to be configured.

## Config

`gtst.json` is created with these defaults:

```json
{
  "schema": ["project", "tree", "asset", "variant", "subVariant"],
  "version_width": 3,
  "ready_tag_name": "ready",
  "single_version_tags": []
}
```

The version width controls folder names such as `v001`.

## Python API

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

Resolve the current asset file, preferring ready and falling back to latest:

```python
current = root.get_current(**facets)
```

Find the latest version carrying a tag:

```python
favorite = root.get_latest_by_tag("favorite", **facets)
```

## Tags

Single-version tags can exist on only one version of an asset at a time. The
ready tag is always single-version:

```python
root.tag_version("ready", version="v002", **facets)
ready_file = root.get_latest_by_tag("ready", **facets)
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
favorite_file = root.get_latest_by_tag("favorite", **facets)
favorite_files = root.find_by_tag("favorite", **facets)
```

Multi-version tags are stored inside each version folder:

```text
v001/
  simpleBox.txt
  gtst_tags/
    favorite.gtst
```

## Design Notes

- GSTS publishes one file per version.
- Publish preserves the source filename.
- Publish never overwrites existing version folders or files.
- Malformed version folders are ignored.
- Retrieval returns an error if the requested version folder has zero asset files
  or more than one direct asset file.
- Tags are ignored if their format does not match GSTS rules.
- Facet values and tag names must use only letters, numbers, underscore, dash,
  and dot.
