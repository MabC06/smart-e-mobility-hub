"""User interface module (M7): the pages for students and operators.

Phase 2 is a clickable prototype (task-assignment-timeline.md, Phase 2): the screens S1 to S8 and
O1 to O6 and the error block S9 of the wireframes exist, and the links between them follow the UI
flow. The data on the pages is sample data, not read from ``core``; Phase 3 connects it.

The pages are Jinja2 templates served by the same FastAPI application (D-002), under the ``/ui``
prefix so they never clash with core's REST routes (core-api-spec.md, 8).

Traceability:
- D-002 (Jinja2 + HTMX, no Node toolchain)
- D-013 (the module joins the application through ``install``)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core.facade import CoreFacade
from ui.routes import root_router, router

STATIC_DIR = Path(__file__).parent / "static"

__all__ = ["install"]


def install(core: CoreFacade, app: FastAPI) -> None:
    """Mount the UI pages and their static files on the application (D-013).

    ``src/main.py`` installs ``ui`` last. The Phase 2 pages do not read ``core`` yet, so
    ``core`` is not used here.
    """
    app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="ui-static")
    app.include_router(router)
    app.include_router(root_router)
