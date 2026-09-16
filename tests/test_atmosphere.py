"""Atmosphere behavior."""

from station_sim.domain import relations
from station_sim.domain.components import Atmosphere, DoorState
from station_sim.ecs.queries import doors, name_of, room_named
from station_sim.scenarios.decompression import build_station
from station_sim.simulation import run
from station_sim.systems.atmosphere import atmosphere_system, trigger_breach


def _pressure(world, room_name):
    return room_named(world, room_name).components[Atmosphere].pressure_kpa


def _door_named(world, door_name):
    for door in doors(world):
        if name_of(door) == door_name:
            return door
    raise KeyError(door_name)


def _close_door(door):
    state = door.components[DoorState]
    door.components[DoorState] = DoorState(
        open=False, locked=state.locked, powered=state.powered, integrity=state.integrity
    )


def test_breached_room_loses_pressure():
    world = build_station(seed=1)
    trigger_breach(world, room_named(world, "Maintenance"), leak_rate=8.0)
    before = _pressure(world, "Maintenance")
    atmosphere_system(world)
    assert _pressure(world, "Maintenance") < before


def test_pressure_never_goes_negative():
    world = build_station(seed=1)
    trigger_breach(world, room_named(world, "Maintenance"), leak_rate=50.0)
    run(world, 20)
    assert _pressure(world, "Maintenance") >= 0.0


def test_open_door_allows_pressure_equalization():
    world = build_station(seed=1)
    trigger_breach(world, room_named(world, "Maintenance"), leak_rate=8.0)
    atmosphere_system(world)
    engineering_before = _pressure(world, "Engineering")
    atmosphere_system(world)
    # Engineering neighbors Maintenance through an open door.
    assert _pressure(world, "Engineering") < engineering_before


def test_closed_door_prevents_equalization():
    world = build_station(seed=1)
    _close_door(_door_named(world, "door.engineering_maintenance"))
    _close_door(_door_named(world, "door.maintenance_cargo"))
    trigger_breach(world, room_named(world, "Maintenance"), leak_rate=8.0)
    engineering_before = _pressure(world, "Engineering")
    cargo_before = _pressure(world, "Cargo")
    for _ in range(5):
        atmosphere_system(world)
    assert _pressure(world, "Maintenance") < 101.3
    assert _pressure(world, "Engineering") == engineering_before
    assert _pressure(world, "Cargo") == cargo_before
