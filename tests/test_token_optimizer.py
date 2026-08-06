import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

from token_optimizer import (  # noqa: E402
    CADENCE_SECONDS, DecisionJournal, ModelCandidate, OptimizerConfig,
    TokenOptimizer, active_work_detected, cadence_due, choose_model,
)


def test_active_work_and_cadence_are_local():
    assert active_work_detected({"status": "running"})
    assert not active_work_detected({"status": "completed"})
    assert cadence_due("2026-08-06T00:00:00+00:00", now="2026-08-06T00:04:59+00:00") is False
    assert cadence_due("2026-08-06T00:00:00+00:00", now="2026-08-06T00:05:00+00:00") is True
    assert CADENCE_SECONDS == 300


def test_fixture_candidates_prefer_cheap_reliable_model():
    candidates = [
        {"id": "expensive", "price": 10, "success_rate": .99, "complexity": 1},
        {"id": "cheap", "price": 1, "success_rate": .99, "complexity": .8},
    ]
    chosen, best, current = choose_model(candidates, current_model="expensive", task_complexity=.5)
    assert chosen.model == "cheap"
    assert best > current


def test_dry_run_journals_without_apply_or_network(tmp_path):
    calls = []
    journal = DecisionJournal(tmp_path / "decisions.jsonl")
    optimizer = TokenOptimizer(OptimizerConfig(dry_run=True, min_improvement=.01), journal)
    result = optimizer.evaluate(
        "expensive", [{"model": "cheap", "price": 1, "success_rate": 1, "complexity": .8}],
        now="2026-08-06T00:00:00+00:00", apply_model=calls.append,
    )
    assert result.action == "recommend"
    assert calls == []
    assert len(journal.entries) == 1
    assert json.loads((tmp_path / "decisions.jsonl").read_text())["dry_run"] is True


def test_active_work_cooldown_and_no_network():
    calls = []
    optimizer = TokenOptimizer(OptimizerConfig(dry_run=False, cooldown_seconds=900, min_improvement=.01))
    held = optimizer.evaluate("old", [{"model": "new", "price": 0, "success_rate": 1}], work={"status": "working"}, apply_model=calls.append)
    assert held.reason == "active_work"
    applied = optimizer.evaluate("old", [{"model": "new", "price": 0, "success_rate": 1}], now=0, apply_model=calls.append)
    assert applied.action == "apply" and calls == ["new"]
    held = optimizer.evaluate("new", [{"model": "other", "price": 0, "success_rate": 1}], now=100, apply_model=calls.append)
    assert held.reason == "cadence"  # cadence also prevents tight-loop changes
    assert calls == ["new"]
