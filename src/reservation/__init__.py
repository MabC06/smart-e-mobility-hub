"""Install the rental tables, student API and ReservationDemand port (D-013)."""

from fastapi import FastAPI

from core.facade import CoreFacade
from core.providers import ProviderPort


def install(core: CoreFacade, app: FastAPI) -> None:
    """Install the reservation module once per application."""
    from reservation.lifecycle import RentalLifecycle
    from reservation.providers import ReservationDemandProvider
    from reservation.router import create_router
    from reservation.service import BookingService
    from reservation.storage import register_tables

    installed = getattr(app.state, "reservation", None)
    if isinstance(installed, BookingService) and installed.core is core:
        return
    register_tables(core)
    service = BookingService(core)
    lifecycle = RentalLifecycle(core)
    if not core.providers.is_registered(ProviderPort.RESERVATION_DEMAND):
        core.register_provider(ProviderPort.RESERVATION_DEMAND, ReservationDemandProvider(core))
    app.include_router(create_router(core, service, lifecycle))
    app.state.reservation = service
    app.state.reservation_lifecycle = lifecycle
