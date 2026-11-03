"""Provider ports: registration and the safe call (core-api-spec.md, 6.1)."""

import pytest

from core.errors import ErrorCode
from core.facade import CoreFacade
from core.providers import ProviderPort, ProviderRegistry
from core.result import Err, Ok


class AlternativeHubs:
    def suggest(self, hub_id):
        return Ok([f"{hub_id}-neighbour"])


def test_a_registered_provider_is_called_and_its_answer_returned():
    registry = ProviderRegistry()
    registry.register(ProviderPort.ALTERNATIVE_HUB, AlternativeHubs())

    result = registry.call(ProviderPort.ALTERNATIVE_HUB, lambda provider: provider.suggest("H01"))

    assert isinstance(result, Ok)
    assert result.value == ["H01-neighbour"]
    assert registry.is_registered(ProviderPort.ALTERNATIVE_HUB)
    assert not registry.is_registered(ProviderPort.DEMAND_SOURCE)


@pytest.mark.parametrize("port", list(ProviderPort))
def test_without_a_provider_the_caller_gets_resource_unavailable(port):
    result = ProviderRegistry().call(port, lambda provider: Ok(provider))

    assert isinstance(result, Err)
    assert result.code is ErrorCode.RESOURCE_UNAVAILABLE
    assert port.value in result.message


def test_a_failing_provider_gives_resource_unavailable_and_does_not_raise():
    registry = ProviderRegistry()
    registry.register(ProviderPort.HOLD_CONSUMER, object())

    def work(provider):
        raise RuntimeError("provider bug")

    result = registry.call(ProviderPort.HOLD_CONSUMER, work)

    assert isinstance(result, Err)
    assert result.code is ErrorCode.RESOURCE_UNAVAILABLE
    assert "bug" not in result.message  # the cause goes to the log, not to the caller


def test_a_port_has_one_provider():
    registry = ProviderRegistry()
    registry.register(ProviderPort.DEMAND_SOURCE, object())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(ProviderPort.DEMAND_SOURCE, object())


def test_the_facade_registers_providers_for_the_modules():
    core = CoreFacade()
    provider = AlternativeHubs()

    core.register_provider(ProviderPort.ALTERNATIVE_HUB, provider)

    result = core.providers.call(ProviderPort.ALTERNATIVE_HUB, lambda p: p.suggest("H02"))
    assert isinstance(result, Ok) and result.value == ["H02-neighbour"]


def test_the_four_ports_of_the_spec_exist():
    assert {p.value for p in ProviderPort} == {
        "DemandSource",
        "AlternativeHubProvider",
        "AlternativeChargingProvider",
        "HoldConsumer",
    }
