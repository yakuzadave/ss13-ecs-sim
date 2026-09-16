"""Decompression scenario: station topology, crew, breach incident.

Topology:

          Bridge
             |
         Central Hall
         /    |     \
    Medbay  Security  Engineering
                         |
                    Maintenance
                         |
                       Cargo
"""

from __future__ import annotations

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import (
    Atmosphere,
    Competence,
    DoorState,
    Health,
    Identity,
    Personality,
    RadioState,
    ReportMemory,
)
from station_sim.ecs.helpers import assign_job, move_entity
from station_sim.ecs.world import new_world

BREACH_TICK = 10
BREACH_LEAK_RATE_KPA_PER_TICK = 8.0

ROOM_NAMES = (
    "Bridge",
    "Central Hall",
    "Medbay",
    "Security",
    "Engineering",
    "Maintenance",
    "Cargo",
)

# (name, side_a, side_b, open)
DOOR_LAYOUT = (
    ("door.bridge_hall", "Bridge", "Central Hall", True),
    ("door.hall_medbay", "Central Hall", "Medbay", True),
    ("door.hall_security", "Central Hall", "Security", True),
    ("door.hall_engineering", "Central Hall", "Engineering", True),
    ("door.engineering_maintenance", "Engineering", "Maintenance", True),
    ("door.maintenance_cargo", "Maintenance", "Cargo", True),
)

# (name, job, start_room, personality, competence)
CREW_ROSTER = (
    (
        "Chen", "Engineer", "Engineering",
        Personality(bravery=0.6, duty=0.9, empathy=0.4, curiosity=0.3, self_preservation=0.5),
        Competence(engineering=0.9),
    ),
    (
        "Patel", "Engineer", "Maintenance",
        Personality(bravery=0.5, duty=0.8, empathy=0.4, curiosity=0.4, self_preservation=0.5),
        Competence(engineering=0.7),
    ),
    (
        "Lin", "Security Officer", "Security",
        Personality(bravery=0.8, duty=0.9, empathy=0.3, curiosity=0.2, self_preservation=0.3),
        Competence(security=0.9),
    ),
    (
        "Rivera", "Doctor", "Medbay",
        Personality(bravery=0.4, duty=0.7, empathy=0.9, curiosity=0.3, self_preservation=0.4),
        Competence(medical=0.9),
    ),
    (
        "Morgan", "Assistant", "Central Hall",
        Personality(bravery=0.3, duty=0.2, empathy=0.3, curiosity=0.9, self_preservation=0.9),
        Competence(),
    ),
)


def _make_room(world: tcod.ecs.World, name: str) -> tcod.ecs.Entity:
    room = world.new_entity()
    room.tags.add(tags.ROOM)
    room.components[Identity] = Identity(name)
    room.components[Atmosphere] = Atmosphere()
    return room


def _make_door(
    world: tcod.ecs.World, name: str, a: tcod.ecs.Entity, b: tcod.ecs.Entity, open: bool
) -> tcod.ecs.Entity:
    door = world.new_entity()
    door.tags.add(tags.DOOR)
    door.components[Identity] = Identity(name)
    door.components[DoorState] = DoorState(open=open)
    door.relation_tag[relations.SIDE_A] = a
    door.relation_tag[relations.SIDE_B] = b
    return door


def _make_job(world: tcod.ecs.World, title: str) -> tcod.ecs.Entity:
    job = world.new_entity()
    job.tags.add(tags.JOB)
    job.components[Identity] = Identity(title)
    return job


def _make_radio(world: tcod.ecs.World, owner_name: str, powered: bool = True) -> tcod.ecs.Entity:
    radio = world.new_entity()
    radio.tags.add(tags.RADIO)
    radio.components[Identity] = Identity(f"radio.{owner_name.lower()}")
    radio.components[RadioState] = RadioState(powered=powered)
    return radio


def _make_crew(
    world: tcod.ecs.World,
    name: str,
    job: tcod.ecs.Entity,
    room: tcod.ecs.Entity,
    personality: Personality,
    competence: Competence,
    radio_powered: bool = True,
) -> tcod.ecs.Entity:
    crew = world.new_entity()
    crew.tags.add(tags.CREW)
    crew.tags.add(tags.HUMAN)
    crew.tags.add(tags.CONSCIOUS)
    crew.components[Identity] = Identity(name)
    crew.components[Health] = Health()
    crew.components[Personality] = personality
    crew.components[Competence] = competence
    crew.components[ReportMemory] = ReportMemory()
    assign_job(crew, job)
    move_entity(crew, room)
    radio = _make_radio(world, name, powered=radio_powered)
    crew.relation_tag[relations.OWNS_RADIO] = radio
    return crew


def _jittered(personality: Personality, rng, amount: float = 0.15) -> Personality:
    """Small deterministic per-seed personality variation.

    The roster's explicit personalities remain the baseline; the world
    RNG perturbs them slightly so multi-seed sweeps produce divergent
    runs while each seed stays exactly reproducible.
    """
    clamp = lambda v: min(1.0, max(0.0, v))
    return Personality(
        bravery=clamp(personality.bravery + rng.uniform(-amount, amount)),
        duty=clamp(personality.duty + rng.uniform(-amount, amount)),
        empathy=clamp(personality.empathy + rng.uniform(-amount, amount)),
        curiosity=clamp(personality.curiosity + rng.uniform(-amount, amount)),
        self_preservation=clamp(
            personality.self_preservation + rng.uniform(-amount, amount)
        ),
    )


def build_station(seed: int = 0, radio_overrides: dict[str, bool] | None = None) -> tcod.ecs.World:
    """Build the station world. radio_overrides maps crew name -> radio powered."""
    from station_sim.ecs.world import sim_state

    radio_overrides = radio_overrides or {}
    world = new_world(seed=seed)
    rng = sim_state(world).rng
    # The seed also determines incident severity: sweeps explore a range
    # of breaches while each seed stays exactly reproducible.
    sim_state(world).breach_leak_rate = rng.uniform(6.0, 12.0)

    rooms = {name: _make_room(world, name) for name in ROOM_NAMES}
    for door_name, a, b, is_open in DOOR_LAYOUT:
        _make_door(world, door_name, rooms[a], rooms[b], is_open)

    jobs: dict[str, tcod.ecs.Entity] = {}
    for name, job_title, room_name, personality, competence in CREW_ROSTER:
        if job_title not in jobs:
            jobs[job_title] = _make_job(world, job_title)
        _make_crew(
            world, name, jobs[job_title], rooms[room_name],
            _jittered(personality, rng), competence,
            radio_powered=radio_overrides.get(name, True),
        )
    return world


def incident_tick(world: tcod.ecs.World) -> None:
    """Apply the scheduled incident for the current tick, if any."""
    from station_sim.ecs.world import sim_state
    from station_sim.ecs.queries import room_named
    from station_sim.systems.atmosphere import trigger_breach

    if sim_state(world).tick == BREACH_TICK:
        trigger_breach(
            world, room_named(world, "Maintenance"), sim_state(world).breach_leak_rate
        )
