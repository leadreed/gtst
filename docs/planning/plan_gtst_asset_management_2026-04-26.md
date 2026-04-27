# GTST Filesystem Asset Management Plan

Date: 2026-04-26

## Goal

Build a Python-based asset management system named `gtst`, short for GetThisSaveThat, for small studios managing files created from generative AI workflows. GTST stores everything directly on the filesystem with no database or hidden index. Assets are reusable, versionable, and taggable.

## Filesystem Model

A GTST root can contain multiple projects:

```text
/myGTSTroot/
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

The root config is required and acts as the GTST marker file:

```json
{
  "schema": ["project", "tree", "asset", "variant", "subVariant"],
  "version_width": 3,
  "single_version_tags": ["ready"]
}
```

The default schema includes `project`, so publishing with:

```python
root.publish(
    source="/tmp/simpleBox.txt",
    project="project1",
    tree="assets",
    asset="simpleBox",
    variant="base",
    subVariant="default",
)
```

creates:

```text
/myGTSTroot/project1/assets/simpleBox/base/default/v001/simpleBox.txt
```

API calls should accept both keyword facets and `facets={...}`.

## API Shape

Version 1 is Python API only, but the package should be structured so a CLI can be added later.

The package/import name is `gtst`.

The API should return absolute filesystem paths, not wrapper objects, for publish and retrieval workflows.

Core operations:

- Create/open a GTST root.
- Publish a single file to a schema-defined asset.
- Resolve latest and explicit versions.
- Apply and query tags.
- Resolve asset/version information from paths.
- List concrete filesystem values such as projects, versions, and tags.

## Publishing Rules

- Single-file publish only.
- Preserve the source filename exactly.
- Create missing project and asset folders automatically.
- Allocate the next version folder by scanning valid version folders.
- Never overwrite existing version folders or files.
- Do not write metadata into version folders.
- Use filesystem locking for concurrent publish/tag operations.

## Version Rules

- Version folders use `v` plus a zero-padded integer, such as `v001`.
- Version width is configurable in the root config.
- Malformed version folders are ignored.
- A valid version folder may be empty.
- Retrieval returns the absolute path to the single asset file in the version folder.
- Retrieval errors clearly when the version folder has zero asset files or more than one direct asset file.
- Retrieval ignores subfolders other than `gtst_tags`.

## Tag Rules

All tags live in `gtst_tags` folders.

Multi-version tags live inside version folders:

```text
v001/
  simpleBox.txt
  gtst_tags/
    someTag.gtst
```

Single-version tags live at the asset directory level:

```text
gtst_tags/
  ready/
    gtstTag001_ready_001.gtst
    gtstTag002_ready_002.gtst
```

For single-version tags:

- The format is `gtstTag###_<tag>_<version>.gtst`.
- `gtstTag###` is the per-tag operation number.
- `<tag>` is the tag name.
- `<version>` is the numeric version without the `v` prefix.
- The latest operation number determines the current tag state.
- Tag files can be empty.
- `ready` is built in as a single-version tag.

If a tag is configured as single-version, version-level multi-version instances of that tag are ignored.

## Validation

- Facet values and tag names allow only letters, numbers, underscore, dash, and dot.
- Spaces are not allowed.
- Slashes, `.` segments, `..`, and path traversal are not allowed.
- Source files must exist and be regular files.
- GTST roots must contain a valid config file.
- Config parse errors fail loudly.
- Malformed version folders and malformed tag files are ignored.

## Testing

- Use `pytest`.
- Use real temporary directories.
- Target Python 3.11+.
- Use type hints throughout.
- Keep tooling minimal.

Test coverage should include:

- Root creation/opening and config behavior.
- Publishing first and subsequent versions.
- Filename preservation.
- Invalid facet and tag names.
- Latest and explicit version resolution.
- Retrieval error cases.
- Single-version tags.
- Multi-version tags.
- Ignoring malformed versions and tags.
- Path-based helpers.

## Implementation Steps

1. Create `pyproject.toml`, package skeleton, public exports, and README.
2. Implement config loading/creation.
3. Implement schema/facet validation and path resolution.
4. Implement filesystem locking.
5. Implement publish and version allocation.
6. Implement latest and explicit version retrieval.
7. Implement single-version and multi-version tagging.
8. Implement path-based helpers.
9. Add pytest coverage.
10. Refine README with examples and final behavior.
