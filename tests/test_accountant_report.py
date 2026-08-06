import json
import subprocess
import sys
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(APP_ROOT))

from app.accountant_report import ReportInputError, build_report, render_json, render_markdown


@pytest.fixture
def events():
    return {
        "events": [
            {"type": "task", "title": "Собрать отчёт", "agent": "Ада", "input_tokens": 100, "output_tokens": 40, "cost": "0.012", "currency": "USD", "timestamp": "2026-08-06T10:00:00Z"},
            {"type": "fix", "fix": "Исправить расчёт", "agent": "Ада", "tokens": 25, "cost": 0.003, "currency": "USD", "status": "completed"},
            {"type": "error", "error": "Таймаут инструмента", "agent": "Борис", "tokens": 10, "cost": 0.001, "currency": "EUR", "status": "failed"},
        ]
    }


def test_json_report_aggregates_sanitized_events(events):
    report = build_report(events, generated_at="2026-08-06T13:00:00+00:00")
    assert report["schema_version"] == 1
    assert report["summary"] == {
        "events": 3, "tasks": 1, "fixes": 1, "errors": 1,
        "tokens": 175, "input_tokens": 100, "output_tokens": 40,
        "cost_by_currency": {"EUR": 0.001, "USD": 0.015},
    }
    assert report["agents"][0] == {"agent": "Ада", "events": 2, "tasks": 1, "fixes": 1, "errors": 0, "tokens": 165}
    decoded = json.loads(render_json(events, generated_at="fixed"))
    assert decoded["generated_at"] == "fixed"


def test_markdown_is_polished_russian_and_escapes_cells(events):
    events["events"][0]["title"] = "Смета | квартал"
    markdown = render_markdown(events, generated_at="fixed")
    assert markdown.startswith("# Отчёт виртуального офиса")
    assert "## Итоги" in markdown
    assert "## По агентам" in markdown
    assert "| Задача | Смета \\| квартал | Ада |" in markdown
    assert "0.015000 USD" in markdown
    assert "Отчёт построен локально" in markdown


def test_sensitive_fields_are_rejected_even_when_nested(events):
    events["events"][0]["prompt"] = "не должно попасть в отчёт"
    with pytest.raises(ReportInputError):
        build_report(events)


def test_category_shorthand_and_empty_payload():
    report = build_report({"tasks": ["Проверить баланс"], "fixes": [], "errors": []}, generated_at="fixed")
    assert report["summary"]["tasks"] == 1
    assert report["events"][0]["title"] == "Проверить баланс"
    empty_markdown = render_markdown({"events": []}, generated_at="fixed")
    assert "_За выбранный период событий нет._" in empty_markdown
    assert "_Записей нет._" in empty_markdown


def test_cli_reads_json_file_and_writes_markdown_and_json(tmp_path, events):
    source = tmp_path / "events.json"
    source.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    markdown_path = tmp_path / "report.md"
    json_path = tmp_path / "report.json"
    module = str(APP_ROOT / "app" / "accountant_report.py")
    for output in (markdown_path, json_path):
        result = subprocess.run(
            [sys.executable, module, "--input", str(source), "--output", str(output)],
            cwd=APP_ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        assert output.exists()
    assert markdown_path.read_text(encoding="utf-8").startswith("# Отчёт")
    assert json.loads(json_path.read_text(encoding="utf-8"))["summary"]["events"] == 3
