# GTST

GTST, short for GetThisSaveThat, is a Python filesystem asset manager for small
studios that need simple versioning and tagging for generated text, images,
videos, and arbitrary files.

The system stores assets directly in folders. There is no database, no hidden
index, and no content parsing. Published assets are normal files in version
folders, and tags are normal `.gtst` files.

## Status

This repository contains the first Python API and CLI implementation.

## CLI Setup

Clone the repository, create a virtual environment, and install GTST in editable
mode:

```bash
git clone <repo-url> gtst
cd gtst
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

Create a GTST root:

```bash
gtst init /path/to/myGTSTroot
```

The command prints the root path and the environment variable to use:

```bash
GTST root: /path/to/myGTSTroot
Set it as your active root:
export GTST_ROOT=/path/to/myGTSTroot
```

Set that variable in your shell:

```bash
export GTST_ROOT=/path/to/myGTSTroot
```

GTST uses `GTST_ROOT` as the active root for both CLI commands and the Python
API. When `GTST_ROOT` points to a missing or uninitialized directory, GTST
creates the default root configuration automatically. `gtst init ROOT` is the
only CLI command that does not require `GTST_ROOT`.

## CLI Usage

Publish a file to an asset:

```bash
gtst publish ./hero.png project1/assets/hero/base/default
```

Publish and mark the new version ready:

```bash
gtst publish ./hero.png project1/assets/hero/base/default --ready
```

Get the latest version:

```bash
gtst latest project1/assets/hero/base/default
```

Get a specific version:

```bash
gtst get project1/assets/hero/base/default/v001
gtst get project1/assets/hero/base/default/v1
```

Mark an existing version ready:

```bash
gtst ready project1/assets/hero/base/default/v001
gtst ready /path/to/myGTSTroot/project1/assets/hero/base/default/v001/hero.png
```

Tag an existing version:

```bash
gtst tag favorite project1/assets/hero/base/default/v001
gtst tag favorite /path/to/myGTSTroot/project1/assets/hero/base/default/v001/hero.png
```

Get the latest version carrying a tag:

```bash
gtst tagged favorite project1/assets/hero/base/default
```

List versions:

```bash
gtst versions project1/assets/hero/base/default
```

List child facet values:

```bash
gtst values
gtst values project1
gtst values project1/assets
gtst values project1/assets/hero
```

Show information for an asset, version, or file:

```bash
gtst info project1/assets/hero/base/default
gtst info project1/assets/hero/base/default/v001
gtst info /path/to/myGTSTroot/project1/assets/hero/base/default/v001/hero.png
gtst info --json project1/assets/hero/base/default
```

When `gtst info` receives an asset query without a version, it resolves the
ready version first. If no ready version exists, it falls back to latest.

## Query Forms

Asset queries are slash-form paths relative to `GTST_ROOT`:

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
`GTST_ROOT`.

## Filesystem Layout

A GTST root contains a required `gtst.json` config file and one or more
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

The schema maps directly to folders beneath the GTST root.

## Ready Tag

GTST has a first-class ready tag. By default, the ready tag is named `ready` and
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
  "default_filename_facet": "asset",
  "single_version_tags": []
}
```

The version width controls folder names such as `v001`.
The default filename facet controls the filename stem used by ComfyUI save nodes
when their `file_name` input is empty. It must name a field in `schema`.

All config fields shown above are required. Older or hand-written config files
that omit one of these fields fail to load.

## Python API

Open the active root from `GTST_ROOT`:

```python
from gtst import GtstRoot

root = GtstRoot.from_env()

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

Create or open a specific root explicitly when setting up a root, writing tests,
or intentionally bypassing the active root:

```python
root = GtstRoot.create("/path/to/myGTSTroot")
root = GtstRoot("/path/to/myGTSTroot")
```

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

## ComfyUI Custom Nodes

GTST can be loaded directly as a ComfyUI custom node package. Clone this
repository into ComfyUI's `custom_nodes` folder and restart ComfyUI:

```bash
cd /path/to/ComfyUI/custom_nodes
git clone <repo-url> gtst
```

The repository root exposes ComfyUI's `NODE_CLASS_MAPPINGS`, and it adds the
local `src` folder to Python's import path when ComfyUI loads it. No separate
package install is required for the current GTST nodes.

Available nodes:

- `GTST Asset Ref`: build a reusable asset reference from facets plus an
  optional version or tag. Outputs a `GTST_ASSET_REF` handle, the resolved file
  path when a version exists, and metadata JSON.
- `Load GTST Image`: load a GTST image as ComfyUI `IMAGE` and `MASK`, with an
  image preview.
- `Save GTST Image`: save a ComfyUI image as a new GTST version, optionally
  marking it ready and adding tags. If `file_name` is empty, the configured
  default filename facet is used. This is an output node and shows an image
  preview.
- `Load GTST Text`: load a GTST text asset as a string.
- `Save GTST Text`: save text as a new GTST version for prompts, captions,
  JSON, notes, or metadata. If `file_name` is empty, the configured default
  filename facet is used. This is an output node and also returns the saved text
  as a normal output for downstream text preview/debug nodes.
- `Load GTST Video`: resolve a GTST video asset and output the video file path,
  with a video preview.
- `Save GTST Video`: publish an existing video file path as a new GTST version.
  If `file_name` is empty, the configured default filename facet is used with
  the source video's extension. This is an output node and shows a video
  preview.
- `Mark GTST Ready`: mark a specific version as the ready version for an asset.
  This is an output node.
- `Tag GTST Version`: add a custom tag to a specific version. This is an output
  node.
- `Browse GTST`: visually browse GTST versions in a scrollable preview grid,
  select a concrete version, and output a `GTST_ASSET_REF`, file path, and
  metadata JSON.

All nodes use `GTST_ROOT`; there are no root path inputs in the ComfyUI nodes.
Set `GTST_ROOT` in the environment that starts ComfyUI. Missing or
uninitialized roots are created with the default GTST config.

`GTST Asset Ref` is the source node for the others. Connect its `asset_ref`
output to load, save, mark-ready, and tag nodes. The facet fields are generated
from the active root's `schema` and use the exact schema field names. They are
editable autocomplete fields populated only from existing values under
`GTST_ROOT`. Focus a field to show valid suggestions for the facets already set
before it, then type to filter them or enter a new value.

`Browse GTST` uses the same schema-driven autocomplete behavior. Empty browser
facet fields match any existing value. Its result mode controls which concrete
versions appear in the preview grid:

- `current`: show one version per matching asset, preferring `ready` and
  falling back to latest.
- `latest only`: show the true latest version per matching asset, ignoring
  `ready`.
- `all versions`: show every matching version file.

Use the `tag` input to filter the displayed versions by tag.

Clicking a preview selects that exact version for the node output. If the
filters change and the selected file is no longer visible, the selection is
cleared. Text previews are truncated before display and clipped inside the
tile. Video previews autoplay muted and unmute while hovered. The preview size
slider controls grid tile size from 80 to 600 pixels.

Image load/save nodes use the Pillow, NumPy, and Torch libraries already present
in a normal ComfyUI Python environment.

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

- GTST publishes one file per version.
- Publish preserves the source filename.
- Publish never overwrites existing version folders or files.
- Malformed version folders are ignored.
- Retrieval returns an error if the requested version folder has zero asset files
  or more than one direct asset file.
- Tags are ignored if their format does not match GTST rules.
- Facet values and tag names must use only letters, numbers, underscore, dash,
  and dot.
