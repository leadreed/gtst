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
        FACET_WIDGETS,
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
        facet_suggestions_payload,
    )
except ImportError:
    from comfy_nodes import (
        FACET_WIDGETS,
        NODE_CLASS_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS,
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
        values = {name: str(query.get(name, "")) for name in FACET_WIDGETS}
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


_register_routes()

WEB_DIRECTORY = "web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
