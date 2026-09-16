"""Radio propagation rules."""

from station_sim.domain import relations
from station_sim.domain.components import RadioState
from station_sim.ecs.helpers import find_belief, radio_owned_by
from station_sim.ecs.queries import crew_named, room_named
from station_sim.scenarios.decompression import build_station
from station_sim.systems.atmosphere import atmosphere_system, trigger_breach
from station_sim.systems.communication import eligible_receivers, transmit_report
from station_sim.systems.perception import perception_system


def _patel_fact(world):
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    trigger_breach(world, maintenance, leak_rate=40.0)
    atmosphere_system(world)
    perception_system(world)
    return patel, find_belief(patel, maintenance, "room_pressure_kpa")


def _set_radio(crew, *, powered=None, channel=None):
    radio = radio_owned_by(crew)
    state = radio.components[RadioState]
    radio.components[RadioState] = RadioState(
        powered=state.powered if powered is None else powered,
        channel=state.channel if channel is None else channel,
        integrity=state.integrity,
    )


def test_powered_radios_propagate_fact():
    world = build_station(seed=1)
    patel, fact = _patel_fact(world)
    lin = crew_named(world, "Lin")
    assert transmit_report(world, patel, fact) >= 1
    assert find_belief(lin, room_named(world, "Maintenance"), "room_pressure_kpa") is not None


def test_powered_off_receiver_gets_nothing():
    world = build_station(seed=1)
    patel, fact = _patel_fact(world)
    lin = crew_named(world, "Lin")
    _set_radio(lin, powered=False)
    assert lin not in eligible_receivers(world, patel)
    transmit_report(world, patel, fact)
    assert find_belief(lin, room_named(world, "Maintenance"), "room_pressure_kpa") is None


def test_different_channel_gets_nothing():
    world = build_station(seed=1)
    patel, fact = _patel_fact(world)
    lin = crew_named(world, "Lin")
    _set_radio(lin, channel="security")
    assert lin not in eligible_receivers(world, patel)


def test_powered_off_sender_transmits_to_nobody():
    world = build_station(seed=1)
    patel, fact = _patel_fact(world)
    _set_radio(patel, powered=False)
    assert eligible_receivers(world, patel) == []
    assert transmit_report(world, patel, fact) == 0


def test_radio_report_has_lower_confidence():
    world = build_station(seed=1)
    patel, fact = _patel_fact(world)
    lin = crew_named(world, "Lin")
    transmit_report(world, patel, fact)
    derived = find_belief(lin, room_named(world, "Maintenance"), "room_pressure_kpa")
    from station_sim.domain.components import FactState

    assert derived.components[FactState].confidence < fact.components[FactState].confidence
