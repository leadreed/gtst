"""ComfyUI custom-node entry point for GTST."""

from __future__ import annotations

import sys
from pathlib import Path


_SRC_DIR = Path(__file__).resolve().parent / "src"
if _SRC_DIR.is_dir():
    src_path = str(_SRC_DIR)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

try:
    from .comfy_nodes import (
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
        browser_results_payload,
        facet_suggestions_payload,
        path_action_payload,
        resolve_path_action_payload,
        schema_metadata_payload,
        set_ready_payload,
    )
except ImportError:
    from comfy_nodes import (
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
        browser_results_payload,
        facet_suggestions_payload,
        path_action_payload,
        resolve_path_action_payload,
        schema_metadata_payload,
        set_ready_payload,
    )


def _register_routes() -> None:
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return

    @PromptServer.instance.routes.get("/gtst/schema")
    async def gtst_schema(request):  # type: ignore[no-untyped-def]
        try:
            payload = schema_metadata_payload()
        except Exception as exc:
            payload = {
                "root_path": "",
                "schema": [],
                "facet_fields": [],
                "suggestion_fields": ["version", "tag"],
                "ready_tag_name": "",
                "default_filename_facet": "",
                "browser_modes": ["current", "latest only", "all versions"],
                "error": str(exc),
            }
        return web.json_response(payload)

    @PromptServer.instance.routes.get("/gtst/facet_values")
    async def gtst_facet_values(request):  # type: ignore[no-untyped-def]
        query = request.rel_url.query
        field = str(query.get("field", ""))
        try:
            schema_payload = schema_metadata_payload()
            values = {
                name: str(query.get(name, ""))
                for name in schema_payload["suggestion_fields"]
            }
            payload = facet_suggestions_payload(field, values)
        except Exception as exc:
            payload = {
                "field": field,
                "schema_field": field,
                "facets": {},
                "values": [],
                "error": str(exc),
            }
        return web.json_response(payload)

    @PromptServer.instance.routes.get("/gtst/browser_results")
    async def gtst_browser_results(request):  # type: ignore[no-untyped-def]
        query = request.rel_url.query
        mode = str(query.get("mode", "current"))
        try:
            limit = int(str(query.get("limit", "200")))
        except ValueError:
            limit = 200
        try:
            schema_payload = schema_metadata_payload()
            values = {
                name: str(query.get(name, ""))
                for name in schema_payload["suggestion_fields"]
            }
            payload = browser_results_payload(mode, values, limit=limit)
        except Exception as exc:
            payload = {
                "mode": mode,
                "root_path": "",
                "filters": {},
                "limit": limit,
                "capped": False,
                "items": [],
                "error": str(exc),
            }
        return web.json_response(payload)

    @PromptServer.instance.routes.get("/gtst/browser_file")
    async def gtst_browser_file(request):  # type: ignore[no-untyped-def]
        query = request.rel_url.query
        file_path = str(query.get("path", ""))
        try:
            from .comfy_nodes import _path_inside_root, _root
        except ImportError:
            from comfy_nodes import _path_inside_root, _root

        root = _root()
        path = _path_inside_root(root, file_path)
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    @PromptServer.instance.routes.post("/gtst/path_action")
    async def gtst_path_action(request):  # type: ignore[no-untyped-def]
        try:
            body = await request.json()
            payload = path_action_payload(
                str(body.get("action", "")),
                str(body.get("path", "")),
            )
        except Exception as exc:
            payload = {"ok": False, "error": str(exc)}
        return web.json_response(payload)

    @PromptServer.instance.routes.post("/gtst/resolve_path_action")
    async def gtst_resolve_path_action(request):  # type: ignore[no-untyped-def]
        try:
            body = await request.json()
            values = {
                str(key): str(value)
                for key, value in dict(body.get("values", {})).items()
            }
            payload = resolve_path_action_payload(str(body.get("action", "")), values)
        except Exception as exc:
            payload = {"ok": False, "error": str(exc)}
        return web.json_response(payload)

    @PromptServer.instance.routes.post("/gtst/set_ready")
    async def gtst_set_ready(request):  # type: ignore[no-untyped-def]
        try:
            body = await request.json()
            payload = set_ready_payload(str(body.get("path", "")))
        except Exception as exc:
            payload = {"ok": False, "error": str(exc)}
        return web.json_response(payload)


_register_routes()

WEB_DIRECTORY = "web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
