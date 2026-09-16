"""Perception respects room-locality and consciousness."""

from station_sim.domain import tags
from station_sim.domain.components import Health
from station_sim.ecs.helpers import belief_value, move_entity
from station_sim.ecs.queries import crew_named, room_named
from station_sim.scenarios.decompression import build_station
from station_sim.systems.atmosphere import trigger_breach
from station_sim.systems.perception import perception_system


def test_crew_learns_current_room_pressure():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    trigger_breach(world, maintenance, leak_rate=40.0)
    from station_sim.systems.atmosphere import atmosphere_system

    atmosphere_system(world)
    perception_system(world)
    believed = belief_value(patel, maintenance, "room_pressure_kpa")
    assert believed is not None and believed < 101.3


def test_crew_does_not_learn_remote_room_pressure():
    world = build_station(seed=1)
    lin = crew_named(world, "Lin")
    maintenance = room_named(world, "Maintenance")
    trigger_breach(world, maintenance, leak_rate=40.0)
    from station_sim.systems.atmosphere import atmosphere_system

    atmosphere_system(world)
    perception_system(world)
    # Lin is in Security, far from Maintenance.
    assert belief_value(lin, maintenance, "room_pressure_kpa") is None


def test_unconscious_crew_does_not_perceive():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    # Force Patel unconscious.
    patel.components[Health] = Health(hp=50.0, oxygenation=0.1, conscious=False)
    patel.tags.discard(tags.CONSCIOUS)
    patel.tags.add(tags.UNCONSCIOUS)
    trigger_breach(world, maintenance, leak_rate=40.0)
    from station_sim.systems.atmosphere import atmosphere_system

    atmosphere_system(world)
    perception_system(world)
    assert belief_value(patel, maintenance, "room_pressure_kpa") is None
