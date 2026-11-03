"""REST interface of core for the UI (core-api-spec.md, section 8)."""

from core.api.app import create_app, create_router

__all__ = ["create_app", "create_router"]
