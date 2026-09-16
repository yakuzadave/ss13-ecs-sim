"""Experiment runner: deterministic decompression runs with metrics."""

from __future__ import annotations

from dataclasses import dataclass, field

import tcod.ecs

from station_sim.domain import relations, tags
from station_sim.domain.components import Atmosphere, DoorState, FactState, Health
from station_sim.ecs.helpers import beliefs_of, location_of
from station_sim.ecs.queries import crew_members, doors, name_of, room_named, rooms
from station_sim.ecs.world import sim_state
from station_sim.scenarios.decompression import build_station, incident_tick
from station_sim.simulation import simulation_tick
from station_sim.systems import atmosphere, health, knowledge, perception
from station_sim.systems.knowledge import aware_of_breach, crew_knowledge_report
from station_sim.systems.logging import event_log_entries


@dataclass
class ExperimentResult:
    seed: int
    comms_enabled: bool
    ticks_run: int
    crew_surviving: int
    crew_injured: int
    crew_dead: int
    crew_conscious: int
    final_room_pressures: dict[str, float]
    number_of_actions: int
    actions_completed: int
    number_of_radio_messages: int
    doors_closed: int
    crew_aware_of_incident: int
    first_observation_tick: int | None
    first_broadcast_tick: int | None
    first_remote_awareness_tick: int | None
    maintenance_min_pressure: float
    engineering_min_pressure: float
    incident_contained_tick: int | None
    event_log: list[str] = field(default_factory=list)
    knowledge_report: list[dict] = field(default_factory=list)
    world: tcod.ecs.World | None = None


def _tick_without_ai(world: tcod.ecs.World) -> None:
    """Physics + perception only. Used for the comms-vs-physics
    invariant: communication alone must never change atmosphere."""
    atmosphere.atmosphere_system(world)
    health.health_system(world)
    perception.perception_system(world)
    knowledge.knowledge_system(world)
    sim_state(world).tick += 1


def _maintenance_pressure(world: tcod.ecs.World) -> float:
    return room_named(world, "Maintenance").components[Atmosphere].pressure_kpa


def _remote_awareness(world: tcod.ecs.World) -> bool:
    """Any crew holding a radio-derived belief about the incident."""
    maintenance = room_named(world, "Maintenance")
    from station_sim.domain.components import PressureState, classify_pressure

    for crew in crew_members(world):
        for fact in beliefs_of(crew):
            state = fact.components.get(FactState)
            if (
                state is not None
                and state.predicate == "room_pressure_kpa"
                and state.source_kind == "radio_report"
                and fact.relation_tag.get(relations.SUBJECT) is maintenance
                and isinstance(state.value, (int, float))
                and classify_pressure(state.value) is not PressureState.NORMAL
            ):
                return True
    return False


def _any_door_to_maintenance_closed(world: tcod.ecs.World) -> bool:
    from station_sim.ecs.helpers import doors_connecting

    maintenance = room_named(world, "Maintenance")
    return any(
        not d.components[DoorState].open for d in doors_connecting(maintenance)
    )


def run_decompression_experiment(
    seed: int = 82741,
    comms_enabled: bool = True,
    ticks: int = 40,
    keep_world: bool = True,
    ai_enabled: bool = True,
) -> ExperimentResult:
    """Run the decompression scenario.

    With comms_enabled=False, every radio starts powered off: the
    incident is identical, but reports cannot propagate.
    With ai_enabled=False, no utility AI or actions run — physics and
    perception only (for causal invariant checks).
    """
    radio_overrides = {} if comms_enabled else {
        name: False for name in ("Chen", "Patel", "Lin", "Rivera", "Morgan")
    }
    world = build_station(seed=seed, radio_overrides=radio_overrides)

    maintenance_min = 101.3
    engineering_min = 101.3
    first_observation = None
    first_broadcast = None
    first_remote = None
    contained_tick = None

    for _ in range(ticks):
        incident_tick(world)
        if ai_enabled:
            simulation_tick(world)
        else:
            _tick_without_ai(world)
        state = sim_state(world)

        maintenance_min = min(maintenance_min, _maintenance_pressure(world))
        engineering_min = min(
            engineering_min,
            room_named(world, "Engineering").components[Atmosphere].pressure_kpa,
        )
        if first_observation is None and any(
            aware_of_breach(c) for c in crew_members(world)
        ):
            first_observation = state.tick
        if first_broadcast is None and state.radio_messages > 0:
            first_broadcast = state.tick
        if first_remote is None and _remote_awareness(world):
            first_remote = state.tick
        if contained_tick is None and _any_door_to_maintenance_closed(world):
            contained_tick = state.tick

    crew = list(crew_members(world))
    actions = list(world.Q.all_of(tags=[tags.ACTION]))
    from station_sim.domain.components import ActionState

    state = sim_state(world)
    return ExperimentResult(
        seed=seed,
        comms_enabled=comms_enabled,
        ticks_run=ticks,
        crew_surviving=sum(1 for c in crew if c.components[Health].hp > 0),
        crew_injured=sum(1 for c in crew if 0 < c.components[Health].hp < 100.0),
        crew_dead=sum(1 for c in crew if c.components[Health].hp <= 0),
        crew_conscious=sum(1 for c in crew if c.components[Health].conscious),
        final_room_pressures={
            name_of(r): round(r.components[Atmosphere].pressure_kpa, 2)
            for r in rooms(world)
        },
        number_of_actions=len(actions),
        actions_completed=sum(
            1 for a in actions if a.components[ActionState].status == "completed"
        ),
        number_of_radio_messages=state.radio_messages,
        doors_closed=sum(
            1 for d in doors(world) if not d.components[DoorState].open
        ),
        crew_aware_of_incident=sum(1 for c in crew if aware_of_breach(c)),
        first_observation_tick=first_observation,
        first_broadcast_tick=first_broadcast,
        first_remote_awareness_tick=first_remote,
        maintenance_min_pressure=round(maintenance_min, 2),
        engineering_min_pressure=round(engineering_min, 2),
        incident_contained_tick=contained_tick,
        event_log=event_log_entries(world),
        knowledge_report=crew_knowledge_report(world),
        world=world if keep_world else None,
    )
