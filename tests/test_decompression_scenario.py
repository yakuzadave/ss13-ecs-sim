"""End-to-end scenario: determinism, comms comparison, metrics."""

from station_sim.domain.components import Atmosphere
from station_sim.ecs.queries import crew_named, room_named
from station_sim.experiments.runner import run_decompression_experiment


def test_determinism_same_seed_same_events():
    a = run_decompression_experiment(seed=82741, comms_enabled=True, ticks=40)
    b = run_decompression_experiment(seed=82741, comms_enabled=True, ticks=40)
    assert a.event_log == b.event_log
    assert a.final_room_pressures == b.final_room_pressures
    assert a.number_of_actions == b.number_of_actions
    assert a.number_of_radio_messages == b.number_of_radio_messages


def test_breach_changes_atmosphere_over_ticks():
    result = run_decompression_experiment(seed=1, comms_enabled=True, ticks=40)
    assert result.final_room_pressures["Maintenance"] < 101.3


def test_patel_observes_and_reports():
    result = run_decompression_experiment(seed=1, comms_enabled=True, ticks=40)
    assert result.number_of_radio_messages >= 1
    holders = {row["holder"] for row in result.knowledge_report}
    # Someone besides Patel learned about Maintenance via the radio.
    remote_learners = {
        row["holder"]
        for row in result.knowledge_report
        if row["subject"] == "Maintenance"
        and row["source_kind"] == "radio_report"
    }
    assert remote_learners - {"Patel"}


def test_comms_disrupted_run_blocks_propagation():
    on = run_decompression_experiment(seed=82741, comms_enabled=True, ticks=40)
    off = run_decompression_experiment(seed=82741, comms_enabled=False, ticks=40)
    # The incident itself is identical: Maintenance is breached in both runs.
    assert on.final_room_pressures["Maintenance"] < 101.3
    assert off.final_room_pressures["Maintenance"] < 101.3
    # Knowledge cannot spread with radios off.
    assert off.number_of_radio_messages == 0
    assert off.crew_aware_of_incident < on.crew_aware_of_incident
    # Different information produces different physical outcomes
    # (e.g. who closes which door), which is the point of the experiment.
    assert on.event_log != off.event_log


def test_result_metrics_present():
    result = run_decompression_experiment(seed=1, comms_enabled=True, ticks=40)
    assert result.ticks_run == 40
    assert 0 <= result.crew_surviving <= 5
    assert result.number_of_actions > 0
    assert 0 <= result.crew_aware_of_incident <= 5
    assert result.event_log
