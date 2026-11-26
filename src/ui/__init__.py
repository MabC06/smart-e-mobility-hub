"""User interface module (M7): the pages for students and operators.

All screens of the wireframes exist. Login is real, and the pages read ``core`` or call the routes
of M2 to M6.

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

    ``src/main.py`` installs ``ui`` last. The pages get ``core`` and the sign-in checker from
    ``app.state`` (set by ``main.build_app``), so ``core`` is not used here.
    """
    app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="ui-static")
    app.include_router(router)
    app.include_router(root_router)
