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
        ASSET_REF_SUGGESTION_WIDGETS,
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
        browser_results_payload,
        facet_suggestions_payload,
    )
except ImportError:
    from comfy_nodes import (
        ASSET_REF_SUGGESTION_WIDGETS,
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
        browser_results_payload,
        facet_suggestions_payload,
    )


def _register_routes() -> None:
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return

    @PromptServer.instance.routes.get("/gtst/facet_values")
    async def gtst_facet_values(request):  # type: ignore[no-untyped-def]
        query = request.rel_url.query
        field = str(query.get("field", ""))
        values = {
            name: str(query.get(name, ""))
            for name in ASSET_REF_SUGGESTION_WIDGETS
        }
        try:
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
        mode = str(query.get("mode", "latest only"))
        values = {
            name: str(query.get(name, ""))
            for name in ASSET_REF_SUGGESTION_WIDGETS
        }
        try:
            limit = int(str(query.get("limit", "200")))
        except ValueError:
            limit = 200
        try:
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


_register_routes()

WEB_DIRECTORY = "web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
