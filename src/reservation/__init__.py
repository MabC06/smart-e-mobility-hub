"""Reservation module entry point (D-013).

Phase 2 exposes the in-process booking service. Provider implementations and UI
routes are not installed until their integration contracts are implemented.
"""

from fastapi import FastAPI

from core.facade import CoreFacade


def install(core: CoreFacade, app: FastAPI) -> None:
    """Register M2 tables and expose the booking service to the composition root."""
    from reservation.service import BookingService
    from reservation.storage import register_tables

    register_tables(core)
    app.state.reservation = BookingService(core)
