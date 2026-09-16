"""Belief ownership, subject references, and provenance."""

from station_sim.domain import relations
from station_sim.domain.components import FactState
from station_sim.ecs.helpers import beliefs_of, find_belief
from station_sim.ecs.queries import crew_named, room_named
from station_sim.scenarios.decompression import build_station
from station_sim.systems.atmosphere import atmosphere_system, trigger_breach
from station_sim.systems.communication import transmit_report
from station_sim.systems.perception import perception_system


def _observed_patel_fact(world):
    patel = crew_named(world, "Patel")
    maintenance = room_named(world, "Maintenance")
    trigger_breach(world, maintenance, leak_rate=40.0)
    atmosphere_system(world)
    perception_system(world)
    return patel, find_belief(patel, maintenance, "room_pressure_kpa")


def test_belief_belongs_to_specific_actor():
    world = build_station(seed=1)
    patel, fact = _observed_patel_fact(world)
    lin = crew_named(world, "Lin")
    assert fact in beliefs_of(patel)
    assert fact not in beliefs_of(lin)


def test_belief_references_subject_and_source_kind():
    world = build_station(seed=1)
    patel, fact = _observed_patel_fact(world)
    maintenance = room_named(world, "Maintenance")
    assert fact.relation_tag[relations.SUBJECT] is maintenance
    state = fact.components[FactState]
    assert state.source_kind == "direct_observation"
    assert state.predicate == "room_pressure_kpa"


def test_radio_derived_fact_preserves_provenance():
    world = build_station(seed=1)
    patel, fact = _observed_patel_fact(world)
    lin = crew_named(world, "Lin")
    delivered = transmit_report(world, patel, fact)
    assert delivered >= 1
    derived = find_belief(lin, room_named(world, "Maintenance"), "room_pressure_kpa")
    assert derived is not None
    assert derived.relation_tag[relations.SOURCE] is patel
    assert derived.relation_tag[relations.DERIVED_FROM] is fact
    state = derived.components[FactState]
    assert state.source_kind == "radio_report"
    assert state.confidence < fact.components[FactState].confidence
