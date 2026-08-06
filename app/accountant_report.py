#!/usr/bin/env python3
"""Локальный отчёт «бухгалтера» по санитизированным событиям.

Модуль обрабатывает только переданное вызывающей стороной JSON-содержимое. Он не
читает конфигурацию, переменные окружения, ключи, промпты или память и не
выполняет сетевых запросов.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

_ALLOWED_FIELDS = {
    "type", "kind", "event", "category", "status", "title", "task", "fix",
    "error", "message", "description", "agent", "agent_id", "agentId",
    "tokens", "input_tokens", "output_tokens", "inputTokens", "outputTokens",
    "cost", "currency", "timestamp", "created_at", "createdAt", "id",
}
_SENSITIVE_PARTS = (
    "api_key", "apikey", "secret", "password", "credential", "authorization",
    "prompt", "private_memory", "raw_memory", "memory_raw", "system_message",
)
_TYPES = {"task": "task", "fix": "fix", "error": "error"}
_RU_TYPES = {"task": "Задача", "fix": "Исправление", "error": "Ошибка"}


class ReportInputError(ValueError):
    """Входные данные не соответствуют безопасному формату отчёта."""


def _sensitive(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    return any(part in normalized for part in _SENSITIVE_PARTS)


def _safe_text(value: Any, *, limit: int = 500) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float, bool)):
        return ""
    text = " ".join(str(value).split())
    # Prevent supplied text from injecting report headings/tables.
    return text.replace("|", "\\|")[:limit]


def _number(value: Any, *, integer: bool = False) -> int | float:
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        return 0
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return 0
    if not number.is_finite() or number < 0:
        return 0
    return int(number) if integer else float(number)


def _event_type(record: Mapping[str, Any]) -> str:
    raw = str(record.get("type") or record.get("kind") or record.get("event") or record.get("category") or "").lower()
    raw = raw.rstrip("s")
    if raw in _TYPES:
        return raw
    for candidate in ("error", "fix", "task"):
        if record.get(candidate):
            return candidate
    return "task"


def _flatten_input(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, Mapping):
        if _sensitive_keys(payload):
            raise ReportInputError("Вход содержит запрещённые чувствительные поля")
        if isinstance(payload.get("events"), list):
            records = payload["events"]
        else:
            records = []
            for category in ("tasks", "fixes", "errors"):
                values = payload.get(category, [])
                if not isinstance(values, list):
                    raise ReportInputError(f"Поле {category!r} должно быть массивом")
                kind = category[:-1] if category != "fixes" else "fix"
                for value in values:
                    if isinstance(value, Mapping):
                        records.append({"type": kind, **value})
                    else:
                        records.append({"type": kind, "title": value})
    else:
        raise ReportInputError("Ожидается JSON-массив событий или объект с events")
    if not all(isinstance(item, Mapping) for item in records):
        raise ReportInputError("Каждое событие должно быть JSON-объектом")
    return list(records)


def _sensitive_keys(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_sensitive(key) or _sensitive_keys(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_sensitive_keys(item) for item in value)
    return False


@dataclass(frozen=True)
class Event:
    type: str
    title: str
    status: str
    agent: str
    tokens: int
    input_tokens: int
    output_tokens: int
    cost: float
    currency: str
    timestamp: str


def normalize_events(payload: Any) -> list[Event]:
    """Проверить и нормализовать только разрешённые поля событий."""
    records = _flatten_input(payload)
    result: list[Event] = []
    for record in records:
        if _sensitive_keys(record):
            raise ReportInputError("Событие содержит запрещённые чувствительные поля")
        clean = {key: value for key, value in record.items() if key in _ALLOWED_FIELDS}
        kind = _event_type(clean)
        title = _safe_text(
            clean.get(kind) or clean.get("title") or clean.get("message") or clean.get("description")
            or "Без названия"
        )
        input_tokens = _number(clean.get("input_tokens", clean.get("inputTokens")), integer=True)
        output_tokens = _number(clean.get("output_tokens", clean.get("outputTokens")), integer=True)
        tokens = _number(clean.get("tokens"), integer=True) or input_tokens + output_tokens
        result.append(Event(
            type=kind,
            title=title,
            status=_safe_text(clean.get("status") or ("failed" if kind == "error" else "completed"), limit=80),
            agent=_safe_text(clean.get("agent") or clean.get("agent_id") or clean.get("agentId") or "не указан", limit=120),
            tokens=tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=round(_number(clean.get("cost")), 6),
            currency=_safe_text(clean.get("currency") or "USD", limit=12).upper(),
            timestamp=_safe_text(clean.get("timestamp") or clean.get("created_at") or clean.get("createdAt"), limit=80),
        ))
    return result


def build_report(payload: Any, *, generated_at: str | None = None) -> dict[str, Any]:
    """Сформировать JSON-совместимую структуру отчёта."""
    events = normalize_events(payload)
    generated = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    counts = Counter(event.type for event in events)
    token_total = sum(event.tokens for event in events)
    token_input = sum(event.input_tokens for event in events)
    token_output = sum(event.output_tokens for event in events)
    costs: dict[str, float] = {}
    for event in events:
        costs[event.currency] = round(costs.get(event.currency, 0.0) + event.cost, 6)
    agents: dict[str, dict[str, Any]] = {}
    for event in events:
        row = agents.setdefault(event.agent, {"events": 0, "tasks": 0, "fixes": 0, "errors": 0, "tokens": 0})
        row["events"] += 1
        row[event.type + ("es" if event.type == "fix" else "s")] += 1
        row["tokens"] += event.tokens
    return {
        "schema_version": 1,
        "generated_at": generated,
        "summary": {
            "events": len(events), "tasks": counts["task"], "fixes": counts["fix"],
            "errors": counts["error"], "tokens": token_total,
            "input_tokens": token_input, "output_tokens": token_output,
            "cost_by_currency": dict(sorted(costs.items())),
        },
        "agents": [{"agent": name, **values} for name, values in sorted(agents.items())],
        "events": [asdict(event) for event in events],
    }


def render_json(payload: Any, *, generated_at: str | None = None) -> str:
    return json.dumps(build_report(payload, generated_at=generated_at), ensure_ascii=False, indent=2) + "\n"


def _fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def render_markdown(payload: Any, *, generated_at: str | None = None) -> str:
    """Сформировать готовый к публикации Markdown-отчёт на русском языке."""
    report = build_report(payload, generated_at=generated_at)
    summary = report["summary"]
    lines = [
        "# Отчёт виртуального офиса", "",
        f"_Сформирован: {report['generated_at']}_", "",
        "## Итоги", "",
        f"- **Событий:** {_fmt_int(summary['events'])}",
        f"- **Задач выполнено:** {_fmt_int(summary['tasks'])}",
        f"- **Исправлений:** {_fmt_int(summary['fixes'])}",
        f"- **Ошибок:** {_fmt_int(summary['errors'])}",
        f"- **Токенов:** {_fmt_int(summary['tokens'])} (вход: {_fmt_int(summary['input_tokens'])}, выход: {_fmt_int(summary['output_tokens'])})",
    ]
    costs = summary["cost_by_currency"]
    lines.append("- **Стоимость:** " + (", ".join(f"{amount:.6f} {currency}" for currency, amount in costs.items()) if costs else "0"))
    lines += ["", "## По агентам", ""]
    if report["agents"]:
        lines += ["| Агент | События | Задачи | Исправления | Ошибки | Токены |", "|---|---:|---:|---:|---:|---:|"]
        for row in report["agents"]:
            lines.append(f"| {row['agent']} | {row['events']} | {row['tasks']} | {row['fixes']} | {row['errors']} | {_fmt_int(row['tokens'])} |")
    else:
        lines.append("_За выбранный период событий нет._")
    lines += ["", "## Журнал событий", ""]
    if report["events"]:
        lines += ["| Тип | Описание | Агент | Статус | Токены | Стоимость | Время |", "|---|---|---|---|---:|---:|---|"]
        for event in report["events"]:
            cost = f"{event['cost']:.6f} {event['currency']}"
            lines.append(f"| {_RU_TYPES[event['type']]} | {event['title']} | {event['agent']} | {event['status']} | {_fmt_int(event['tokens'])} | {cost} | {event['timestamp'] or '—'} |")
    else:
        lines.append("_Записей нет._")
    lines += ["", "> Отчёт построен локально только по переданным санитизированным событиям.", ""]
    return "\n".join(lines)


def _load_input(argument: str) -> Any:
    """Принять JSON-строку или путь к JSON-файлу — и ничего больше."""
    candidate = Path(argument)
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8")
    else:
        text = argument
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReportInputError(f"Некорректный JSON: {exc.msg}") from exc


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Локальный отчёт по санитизированным событиям")
    parser.add_argument("--input", required=True, help="JSON-строка или путь к JSON-файлу")
    parser.add_argument("--output", required=True, help="Файл .md или .json")
    args = parser.parse_args(argv)
    output = Path(args.output)
    try:
        payload = _load_input(args.input)
        content = render_json(payload) if output.suffix.lower() == ".json" else render_markdown(payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
    except (OSError, ReportInputError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
