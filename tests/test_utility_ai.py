"""Utility AI reads beliefs, never objective atmosphere."""

from station_sim.domain import relations, tags
from station_sim.domain.components import Atmosphere, FactState
from station_sim.ecs.helpers import give_belief
from station_sim.ecs.queries import crew_named, room_named
from station_sim.scenarios.decompression import build_station
from station_sim.systems.atmosphere import atmosphere_system, trigger_breach
from station_sim.systems.communication import transmit_report
from station_sim.systems.perception import perception_system
from station_sim.systems.utility_ai import select_action


def _inject_false_safe_belief(world, actor, room, pressure=101.3):
    """Give the actor a belief that a room is safe, whatever the truth is."""
    fact = world.new_entity()
    fact.tags.add(tags.FACT)
    fact.components[FactState] = FactState(
        predicate="room_pressure_kpa",
        value=pressure,
        confidence=0.99,
        source_kind="direct_observation",
        observed_tick=0,
    )
    fact.relation_tag[relations.SUBJECT] = room
    give_belief(actor, fact)


def test_ai_uses_believed_pressure_not_objective_pressure():
    """Contradictory scenario: room objectively dangerous, actor believes safe.

    The actor must act on the (wrong) belief, not the truth. Note this
    test calls select_action directly without running perception, so no
    new observation can overwrite the injected belief.
    """
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    # Objective: catastrophic decompression.
    maintenance.components[Atmosphere] = Atmosphere(pressure_kpa=20.0)
    # Subjective: Patel believes it is safe.
    _inject_false_safe_belief(world, patel, maintenance, pressure=101.3)

    score = select_action(patel)
    assert score is not None
    assert score.action_kind != "evacuate", (
        "Patel evacuated despite believing the room was safe — "
        "the AI must be reading objective atmosphere."
    )


def test_ai_reacts_once_belief_matches_danger():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    trigger_breach(world, maintenance, leak_rate=40.0)
    atmosphere_system(world)
    perception_system(world)
    score = select_action(patel)
    assert score is not None
    assert score.action_kind in {"evacuate", "report_hazard", "close_door"}
    assert score.action_kind != "idle"


def test_remote_crew_does_not_react_without_information():
    """The critical anti-omniscience test, kept permanently.

    Maintenance is objectively breached. Lin is in Security with no
    observation, alarm, or communication. Lin must not react to the
    breach; after a radio report, Lin may.
    """
    world = build_station(seed=1)
    lin = crew_named(world, "Lin")
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")

    trigger_breach(world, maintenance, leak_rate=40.0)
    atmosphere_system(world)
    perception_system(world)  # Lin perceives only Security (safe).

    from station_sim.ecs.helpers import find_belief

    assert find_belief(lin, maintenance, "room_pressure_kpa") is None
    before = select_action(lin)
    assert before is not None and before.action_kind == "idle"

    # Chen in Engineering is adjacent to Maintenance but also has no
    # information yet — so Chen idles too.
    chen = crew_named(world, "Chen")
    assert find_belief(chen, maintenance, "room_pressure_kpa") is None
    chen_before = select_action(chen)
    assert chen_before is not None and chen_before.action_kind == "idle"

    # Patel observes and reports over the radio.
    patel_fact = find_belief(patel, maintenance, "room_pressure_kpa")
    assert patel_fact is not None
    delivered = transmit_report(world, patel, patel_fact)
    assert delivered >= 1

    # Lin now KNOWS (knowledge changed via communication only)...
    assert find_belief(lin, maintenance, "room_pressure_kpa") is not None
    # ...but Lin cannot reach Maintenance from Security and relays are
    # suppressed, so Lin still idles. Chen, adjacent to Maintenance,
    # can act on the same broadcast.
    assert select_action(lin).action_kind == "idle"
    assert find_belief(chen, maintenance, "room_pressure_kpa") is not None
    chen_after = select_action(chen)
    assert chen_after is not None and chen_after.action_kind in {
        "close_door",
        "investigate",
        "report_hazard",
        "evacuate",
    }


def test_scores_are_explainable():
    world = build_station(seed=1)
    patel = crew_named(world, "Patel")
    trigger_breach(world, room_named(world, "Maintenance"), leak_rate=40.0)
    atmosphere_system(world)
    perception_system(world)
    score = select_action(patel)
    assert score is not None
    assert isinstance(score.contributions, dict)
    # Every selected non-idle action should record its scoring terms.
    if score.action_kind != "idle":
        assert score.contributions
