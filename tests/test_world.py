"""World creation and station topology."""

from station_sim.domain import relations, tags
from station_sim.domain.components import Atmosphere, DoorState, Identity, Personality
from station_sim.ecs.helpers import adjacent_rooms, location_of
from station_sim.ecs.queries import crew_members, doors, name_of, room_named, rooms
from station_sim.scenarios.decompression import build_station


def test_world_creates_station_rooms():
    world = build_station(seed=1)
    assert {name_of(r) for r in rooms(world)} == {
        "Bridge", "Central Hall", "Medbay", "Security",
        "Engineering", "Maintenance", "Cargo",
    }


def test_door_topology_matches_plan():
    world = build_station(seed=1)
    edges = set()
    for door in doors(world):
        a = name_of(door.relation_tag[relations.SIDE_A])
        b = name_of(door.relation_tag[relations.SIDE_B])
        edges.add(frozenset((a, b)))
    assert edges == {
        frozenset(("Bridge", "Central Hall")),
        frozenset(("Central Hall", "Medbay")),
        frozenset(("Central Hall", "Security")),
        frozenset(("Central Hall", "Engineering")),
        frozenset(("Engineering", "Maintenance")),
        frozenset(("Maintenance", "Cargo")),
    }


def test_crew_distinct_roles_and_personalities():
    world = build_station(seed=1)
    crew = {name_of(c): c for c in crew_members(world)}
    assert set(crew) == {"Chen", "Patel", "Lin", "Rivera", "Morgan"}
    personalities = {name: c.components[Personality] for name, c in crew.items()}
    assert len(set(personalities.values())) == len(personalities)  # all distinct
    assert name_of(location_of(crew["Patel"])) == "Maintenance"
    assert name_of(location_of(crew["Lin"])) == "Security"


def test_adjacency_derived_from_door_relationships():
    world = build_station(seed=1)
    engineering = room_named(world, "Engineering")
    neighbors = {name_of(r) for r in adjacent_rooms(engineering)}
    assert neighbors == {"Central Hall", "Maintenance"}
