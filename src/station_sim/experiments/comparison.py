"""Comparison and Pandas conversion for experiment results.

Pandas lives here, never in the simulation core.
"""

from __future__ import annotations

import pandas as pd

from station_sim.experiments.runner import ExperimentResult


def runs_df(results: list[ExperimentResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "seed": r.seed,
                "comms_enabled": r.comms_enabled,
                "ticks_run": r.ticks_run,
                "crew_surviving": r.crew_surviving,
                "crew_injured": r.crew_injured,
                "crew_dead": r.crew_dead,
                "crew_conscious": r.crew_conscious,
                "number_of_actions": r.number_of_actions,
                "actions_completed": r.actions_completed,
                "number_of_radio_messages": r.number_of_radio_messages,
                "doors_closed": r.doors_closed,
                "crew_aware_of_incident": r.crew_aware_of_incident,
                "first_observation_tick": r.first_observation_tick,
                "first_broadcast_tick": r.first_broadcast_tick,
                "first_remote_awareness_tick": r.first_remote_awareness_tick,
                "maintenance_min_pressure": r.maintenance_min_pressure,
                "engineering_min_pressure": r.engineering_min_pressure,
                "incident_contained_tick": r.incident_contained_tick,
            }
            for r in results
        ]
    )


def rooms_df(result: ExperimentResult) -> pd.DataFrame:
    return pd.DataFrame(
        [{"room": name, "pressure_kpa": p} for name, p in result.final_room_pressures.items()]
    )


def crew_df(result: ExperimentResult) -> pd.DataFrame:
    from station_sim.domain.components import Health, Personality, Competence
    from station_sim.ecs.queries import crew_members, name_of
    from station_sim.ecs.helpers import location_of
    from station_sim.systems.knowledge import aware_of_breach

    assert result.world is not None, "result was built with keep_world=False"
    rows = []
    for crew in crew_members(result.world):
        health = crew.components[Health]
        personality = crew.components[Personality]
        competence = crew.components[Competence]
        location = location_of(crew)
        rows.append(
            {
                "name": name_of(crew),
                "location": name_of(location) if location else None,
                "hp": health.hp,
                "oxygenation": round(health.oxygenation, 3),
                "conscious": health.conscious,
                "aware_of_breach": aware_of_breach(crew),
                "duty": personality.duty,
                "self_preservation": personality.self_preservation,
                "engineering": competence.engineering,
            }
        )
    return pd.DataFrame(rows)


def facts_df(result: ExperimentResult) -> pd.DataFrame:
    return pd.DataFrame(result.knowledge_report)


def actions_df(result: ExperimentResult) -> pd.DataFrame:
    from station_sim.domain import relations, tags
    from station_sim.domain.components import ActionState
    from station_sim.ecs.queries import name_of

    assert result.world is not None, "result was built with keep_world=False"
    rows = []
    for action in result.world.Q.all_of(tags=[tags.ACTION]):
        state = action.components[ActionState]
        actor = action.relation_tag[relations.PERFORMED_BY]
        rows.append(
            {
                "actor": name_of(actor),
                "kind": state.kind,
                "utility": state.utility,
                "selected_tick": state.selected_tick,
                "status": state.status,
            }
        )
    return pd.DataFrame(rows)


def compare_runs(a: ExperimentResult, b: ExperimentResult) -> pd.DataFrame:
    """Side-by-side comparison of two runs (e.g. comms on vs off)."""
    return runs_df([a, b]).set_index("comms_enabled").T.rename(
        columns={True: "comms_on", False: "comms_off"}
    )


def run_paired_sweep(
    seeds: range | list[int], ticks: int = 40
) -> pd.DataFrame:
    """Paired multi-seed experiment: every seed runs comms ON and comms
    OFF against identical initial conditions, so outcome differences are
    attributable to communication, not initial randomness.
    """
    from station_sim.experiments.runner import run_decompression_experiment

    results = []
    for seed in seeds:
        results.append(
            run_decompression_experiment(
                seed=seed, comms_enabled=True, ticks=ticks, keep_world=False
            )
        )
        results.append(
            run_decompression_experiment(
                seed=seed, comms_enabled=False, ticks=ticks, keep_world=False
            )
        )
    return runs_df(results)


def knowledge_timeline(result: ExperimentResult) -> pd.DataFrame:
    """First tick each crew member became aware of the incident.

    Returns one row per crew member: name, first_aware_tick, and how
    they learned (direct_observation / radio_report / never). The raw
    material for a knowledge-propagation timeline plot.
    """
    from station_sim.domain import relations
    from station_sim.domain.components import FactState
    from station_sim.ecs.helpers import beliefs_of
    from station_sim.ecs.queries import crew_members, name_of

    assert result.world is not None, "result was built with keep_world=False"
    from station_sim.domain.components import PressureState, classify_pressure

    rows = []
    for crew in sorted(crew_members(result.world), key=name_of):
        first_tick = None
        how = "never"
        for fact in beliefs_of(crew):
            state = fact.components.get(FactState)
            if (
                state is None
                or state.predicate != "room_pressure_kpa"
                or not isinstance(state.value, (int, float))
                or classify_pressure(state.value) is PressureState.NORMAL
            ):
                continue
            if first_tick is None or state.observed_tick < first_tick:
                first_tick = state.observed_tick
                how = state.source_kind
        rows.append(
            {"crew": name_of(crew), "first_aware_tick": first_tick, "learned_via": how}
        )
    return pd.DataFrame(rows)


def knowledge_timeline_grid(result: ExperimentResult) -> pd.DataFrame:
    """ASCII-friendly tick x crew grid: '●' once a crew member is aware."""
    timeline = knowledge_timeline(result)
    crew_names = timeline["crew"].tolist()
    grid = {}
    for _, row in timeline.iterrows():
        ticks = {
            t: ("●" if row["first_aware_tick"] is not None and t >= row["first_aware_tick"] else "")
            for t in range(result.ticks_run + 1)
        }
        grid[row["crew"]] = ticks
    return pd.DataFrame(grid).rename_axis("tick")
