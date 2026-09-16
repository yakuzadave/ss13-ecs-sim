"""v0.2: report deduplication, deterministic IDs, belief precedence,
causal invariant between communication and physics."""

from station_sim.domain import relations, tags
from station_sim.domain.components import (
    Atmosphere,
    FactState,
    Identity,
    PressureState,
    ReportMemory,
    classify_pressure,
)
from station_sim.ecs.helpers import (
    belief_value,
    find_belief,
    give_belief,
    move_entity,
)
from station_sim.ecs.queries import crew_named, name_of, room_named
from station_sim.ecs.world import new_transient_entity, sim_state
from station_sim.experiments.runner import run_decompression_experiment
from station_sim.scenarios.decompression import build_station
from station_sim.simulation import simulation_tick
from station_sim.systems.atmosphere import atmosphere_system, trigger_breach
from station_sim.systems.communication import (
    record_report,
    reportable_pressure_transitions,
    transmit_report,
)
from station_sim.systems.perception import perception_system


def _make_fact(world, actor, room, pressure, tick, source_kind, confidence=0.9):
    fact = world.new_entity()
    fact.tags.add(tags.FACT)
    fact.components[FactState] = FactState(
        predicate="room_pressure_kpa",
        value=pressure,
        confidence=confidence,
        source_kind=source_kind,
        observed_tick=tick,
    )
    fact.relation_tag[relations.SUBJECT] = room
    give_belief(actor, fact)
    return fact


# --- Pressure classification -------------------------------------------

def test_classify_pressure_boundaries():
    assert classify_pressure(101.3) is PressureState.NORMAL
    assert classify_pressure(80.0) is PressureState.NORMAL
    assert classify_pressure(79.9) is PressureState.LOW
    assert classify_pressure(50.0) is PressureState.LOW
    assert classify_pressure(49.9) is PressureState.CRITICAL
    assert classify_pressure(15.0) is PressureState.CRITICAL
    assert classify_pressure(14.9) is PressureState.VACUUM


# --- Report deduplication -----------------------------------------------

def test_report_only_on_state_transition():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")

    # Patel believes Maintenance is LOW: reportable (never reported).
    _make_fact(world, patel, maintenance, 60.0, tick=1, source_kind="direct_observation")
    transitions = reportable_pressure_transitions(patel)
    assert len(transitions) == 1
    _, state, _ = transitions[0]
    assert state is PressureState.LOW

    # After reporting LOW, a small pressure change (still LOW) is suppressed.
    record_report(patel, maintenance, state)
    _make_fact(world, patel, maintenance, 57.0, tick=2, source_kind="direct_observation")
    assert reportable_pressure_transitions(patel) == []

    # Escalation to CRITICAL is reportable again.
    _make_fact(world, patel, maintenance, 30.0, tick=3, source_kind="direct_observation")
    transitions = reportable_pressure_transitions(patel)
    assert len(transitions) == 1
    assert transitions[0][1] is PressureState.CRITICAL

    # Return to NORMAL after a report is reportable ("hazard clearing").
    record_report(patel, maintenance, PressureState.CRITICAL)
    _make_fact(world, patel, maintenance, 95.0, tick=4, source_kind="direct_observation")
    transitions = reportable_pressure_transitions(patel)
    assert len(transitions) == 1
    assert transitions[0][1] is PressureState.NORMAL


def test_normal_state_never_reported_unprompted():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    _make_fact(world, patel, maintenance, 101.3, tick=1, source_kind="direct_observation")
    assert reportable_pressure_transitions(patel) == []


def test_full_run_has_no_report_spam():
    result = run_decompression_experiment(seed=82741, comms_enabled=True, ticks=40)
    # v0.1 produced 115 messages here; transition-based reporting should
    # produce a small bounded number even with relays.
    assert 0 < result.number_of_radio_messages <= 30


# --- Deterministic transient IDs ----------------------------------------

def test_transient_entities_get_sequence_ids():
    world = build_station(seed=1)
    a = new_transient_entity(world, "fact")
    b = new_transient_entity(world, "action")
    assert name_of(a) == "fact.0001"
    assert name_of(b) == "action.0002"


def test_same_seed_produces_same_transient_ids():
    logs = []
    for _ in range(2):
        result = run_decompression_experiment(seed=42, comms_enabled=True, ticks=25)
        world = result.world
        ids = sorted(
            name_of(e)
            for e in world.Q.all_of(tags=[tags.FACT])
        )
        logs.append(ids)
    assert logs[0] == logs[1]
    assert all(name.startswith("fact.") for name in logs[0])


# --- Belief precedence --------------------------------------------------

def test_newest_observation_wins():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    _make_fact(world, patel, maintenance, 101.3, tick=12, source_kind="radio_report", confidence=0.72)
    _make_fact(world, patel, maintenance, 30.0, tick=18, source_kind="direct_observation", confidence=0.99)
    assert belief_value(patel, maintenance, "room_pressure_kpa") == 30.0


def test_equal_ticks_direct_observation_wins():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    _make_fact(world, patel, maintenance, 55.0, tick=10, source_kind="radio_report", confidence=0.99)
    _make_fact(world, patel, maintenance, 60.0, tick=10, source_kind="direct_observation", confidence=0.5)
    assert belief_value(patel, maintenance, "room_pressure_kpa") == 60.0


def test_equal_ticks_and_source_higher_confidence_wins():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    _make_fact(world, patel, maintenance, 55.0, tick=10, source_kind="radio_report", confidence=0.6)
    _make_fact(world, patel, maintenance, 60.0, tick=10, source_kind="radio_report", confidence=0.9)
    assert belief_value(patel, maintenance, "room_pressure_kpa") == 60.0


# --- Causal invariant: information never directly touches physics -------

def test_comms_do_not_directly_affect_physics_without_ai():
    """Identical worlds, AI disabled: comms ON and comms OFF must produce
    identical atmospheres. Information may only change physics THROUGH
    decisions and actions, never directly.
    """
    on = run_decompression_experiment(
        seed=82741, comms_enabled=True, ticks=40, ai_enabled=False
    )
    off = run_decompression_experiment(
        seed=82741, comms_enabled=False, ticks=40, ai_enabled=False
    )
    assert on.final_room_pressures == off.final_room_pressures
    assert on.maintenance_min_pressure == off.maintenance_min_pressure
    assert on.number_of_radio_messages == 0  # nobody acts, nobody reports


def test_comms_change_physics_only_through_actions():
    """With AI enabled, divergent information legitimately produces
    divergent physics (doors closed by informed crew)."""
    on = run_decompression_experiment(
        seed=82741, comms_enabled=True, ticks=40, ai_enabled=True
    )
    off = run_decompression_experiment(
        seed=82741, comms_enabled=False, ticks=40, ai_enabled=True
    )
    assert on.event_log != off.event_log
    # The difference must be mediated by actions: door closures differ.
    assert on.doors_closed != off.doors_closed or on.number_of_actions != off.number_of_actions


# --- Paired sweep --------------------------------------------------------

def test_paired_sweep_pairs_seeds():
    from station_sim.experiments.comparison import run_paired_sweep

    df = run_paired_sweep(range(3), ticks=25)
    assert len(df) == 6
    for seed in range(3):
        pair = df[df["seed"] == seed]
        assert set(pair["comms_enabled"]) == {True, False}
    # Deterministic: repeated sweep gives identical frame.
    df2 = run_paired_sweep(range(3), ticks=25)
    assert df.equals(df2)
