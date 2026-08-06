"""Safe, local token/model optimization helpers.

This module only scores caller-provided candidates and records decisions.  It does
not discover models, call A6API, or modify OpenClaw configuration.  Integrators
must provide candidate data and an explicit apply callback if they want changes.

The :class:`SafariA6APIController` below is an intentionally narrow, read-first
adapter for the A6API page in Safari.  It accepts only a mocked/local browser
adapter; it never opens a URL, makes an HTTP request, or handles secret values.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

CADENCE_SECONDS = 5 * 60
A6API_TAB_TITLE = "A6api-Token聚合站"
MIN_SUCCESS_RATE = 0.90


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


def active_work_detected(work: Any, *, now: Any = None, idle_after_seconds: int = 300) -> bool:
    """Return whether a work item looks active, without contacting any service."""
    if work is None:
        return False
    if isinstance(work, (list, tuple, set)):
        return any(active_work_detected(item, now=now, idle_after_seconds=idle_after_seconds) for item in work)
    if not isinstance(work, Mapping):
        work = getattr(work, "__dict__", {})
    state = str(work.get("status", work.get("state", ""))).lower()
    if state in {"idle", "inactive", "done", "completed", "complete", "stopped", "failed", "cancelled", "canceled"}:
        return False
    if state in {"active", "working", "running", "thinking", "busy", "queued", "in_progress", "in-progress"}:
        return True
    current = _timestamp(now) if now is not None else _now().timestamp()
    for key in ("last_active", "lastActiveAt", "updated_at", "updatedAt", "activity_at", "activityAt"):
        stamp = _timestamp(work.get(key))
        if stamp is not None:
            return current - stamp <= idle_after_seconds
    return bool(work.get("active", False))


@dataclass(frozen=True)
class ModelCandidate:
    model: str
    price: float = 0.0
    success_rate: float = 1.0
    complexity: float = 0.5
    metadata: Optional[dict[str, Any]] = None

    @classmethod
    def from_value(cls, value: Any) -> "ModelCandidate":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(model=value)
        data = dict(value)
        return cls(model=str(data.get("model") or data.get("id") or data.get("name") or ""), price=float(data.get("price", data.get("cost", 0.0)) or 0.0), success_rate=float(data.get("success_rate", data.get("successRate", data.get("success", 1.0))) or 0.0), complexity=float(data.get("complexity", data.get("capability", 0.5)) or 0.0), metadata=data.get("metadata"))


def score_candidate(candidate: Any, *, task_complexity: float = 0.5, price_weight: float = 0.45, success_weight: float = 0.4, complexity_weight: float = 0.15, max_price: Optional[float] = None) -> float:
    """Score a candidate; higher is better. Inputs are normalized and bounded."""
    c = ModelCandidate.from_value(candidate)
    price = max(0.0, c.price)
    if max_price is None:
        max_price = max(price, 1.0)
    price_score = 1.0 - min(1.0, price / max(max_price, 1e-12))
    success = min(1.0, max(0.0, c.success_rate))
    capability = min(1.0, max(0.0, c.complexity))
    requested = min(1.0, max(0.0, task_complexity))
    complexity_score = capability if capability >= requested else capability / max(requested, 1e-9)
    return price_weight * price_score + success_weight * success + complexity_weight * complexity_score


def choose_model(candidates: Iterable[Any], *, current_model: Optional[str] = None, task_complexity: float = 0.5, min_improvement: float = 0.05, hysteresis: Optional[float] = None) -> tuple[Optional[ModelCandidate], float, float]:
    items = [ModelCandidate.from_value(x) for x in candidates if ModelCandidate.from_value(x).model]
    if not items:
        return None, 0.0, 0.0
    max_price = max(c.price for c in items)
    scored = [(score_candidate(c, task_complexity=task_complexity, max_price=max_price), c) for c in items]
    scored.sort(key=lambda pair: (-pair[0], pair[1].model))
    best_score, best = scored[0]
    current_score = next((s for s, c in scored if c.model == current_model), 0.0)
    threshold = hysteresis if hysteresis is not None else min_improvement
    if current_model and best.model != current_model and best_score < current_score + threshold:
        return next((c for _, c in scored if c.model == current_model), best), current_score, current_score
    return best, best_score, current_score


def cadence_due(last_evaluated_at: Any = None, *, now: Any = None, cadence_seconds: int = CADENCE_SECONDS) -> bool:
    stamp = _timestamp(last_evaluated_at)
    return stamp is None or (_timestamp(now) if now is not None else _now().timestamp()) - stamp >= cadence_seconds


@dataclass(frozen=True)
class OptimizerConfig:
    dry_run: bool = True
    min_improvement: float = 0.05
    hysteresis: float = 0.02
    cooldown_seconds: int = 900
    cadence_seconds: int = CADENCE_SECONDS
    idle_after_seconds: int = 300


@dataclass(frozen=True)
class Decision:
    action: str
    current_model: Optional[str]
    recommended_model: Optional[str]
    best_score: float
    current_score: float
    reason: str
    dry_run: bool
    at: str


class DecisionJournal:
    """Append-only JSONL journal; absent path means in-memory only."""
    def __init__(self, path: Optional[str | Path] = None):
        self.path = Path(path) if path else None
        self.entries: list[dict[str, Any]] = []

    def record(self, decision: Decision) -> None:
        entry = asdict(decision)
        self.entries.append(entry)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, sort_keys=True) + "\n")


class BrowserAdapter(Protocol):
    """Local/mock Safari surface. Implementations must not expose secrets."""
    def current_tab_title(self) -> str: ...
    def refresh(self) -> None: ...
    def open_marketplace(self) -> None: ...
    def select_agent_token(self, agent: str, token_id: str) -> None: ...
    def select_model(self, model: str) -> None: ...
    def seller_rows(self) -> Sequence[Mapping[str, Any]]: ...
    def route(self) -> Mapping[str, Any]: ...
    def usage_log(self) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class SellerRow:
    seller: str
    model: str
    price: float
    success_rate: float


class SafariA6APIController:
    """Allowlisted, current-tab-only controller for the A6API Safari page.

    All methods are dry-run by default. Mutating adapter calls are made only when
    ``apply=True`` is passed to the constructor. ``token_id`` is an identifier,
    never a token/key value; secret-looking fields are rejected rather than stored.
    """
    ALLOWED_ACTIONS = frozenset({"refresh", "open_marketplace", "select_agent_token", "select_model", "inspect_seller_rows", "choose_minimum_price", "confirm_route_fixed", "inspect_usage_log"})

    def __init__(self, adapter: BrowserAdapter, *, apply: bool = False, tab_title: str = A6API_TAB_TITLE):
        self.adapter = adapter
        self.apply = bool(apply)
        self.tab_title = tab_title

    def _guard(self) -> None:
        if self.adapter.current_tab_title() != self.tab_title:
            raise PermissionError("refusing to act: Safari current tab is not the A6API page")

    def _mutate(self, action: str, fn: Callable[[], Any]) -> bool:
        if action not in self.ALLOWED_ACTIONS:
            raise ValueError("action is not allowlisted")
        self._guard()
        if not self.apply:
            return False
        fn()
        return True

    def refresh(self) -> bool:
        return self._mutate("refresh", self.adapter.refresh)

    def open_marketplace(self) -> bool:
        return self._mutate("open_marketplace", self.adapter.open_marketplace)

    def select_agent_token(self, agent: str, token_id: str) -> bool:
        self._safe_identifier(agent, "agent")
        self._safe_identifier(token_id, "token_id")
        return self._mutate("select_agent_token", lambda: self.adapter.select_agent_token(agent, token_id))

    def select_model(self, model: str) -> bool:
        self._safe_identifier(model, "model")
        return self._mutate("select_model", lambda: self.adapter.select_model(model))

    def inspect_seller_rows(self) -> tuple[SellerRow, ...]:
        self._guard()
        return tuple(self._row(row) for row in self.adapter.seller_rows())

    def choose_minimum_price(self, rows: Optional[Iterable[Any]] = None, *, min_success_rate: float = MIN_SUCCESS_RATE) -> Optional[SellerRow]:
        candidates = tuple(rows) if rows is not None else self.inspect_seller_rows()
        parsed = tuple(r if isinstance(r, SellerRow) else self._row(r) for r in candidates)
        eligible = [r for r in parsed if r.success_rate >= min_success_rate]
        return min(eligible, key=lambda r: (r.price, r.seller, r.model), default=None)

    def confirm_route_fixed(self, *, expected: Mapping[str, Any]) -> bool:
        self._guard()
        actual = self.adapter.route()
        return dict(actual) == dict(expected)

    def inspect_usage_log(self) -> tuple[Mapping[str, Any], ...]:
        self._guard()
        return tuple(dict(item) for item in self.adapter.usage_log())

    @staticmethod
    def _safe_identifier(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty identifier")
        lowered = value.lower()
        if any(marker in lowered for marker in ("api_key", "apikey", "secret", "password", "bearer")):
            raise ValueError(f"{name} looks like a secret and is refused")

    @staticmethod
    def _row(value: Mapping[str, Any]) -> SellerRow:
        forbidden = {"key", "api_key", "apikey", "secret", "password", "token_value", "token_secret"}
        if forbidden.intersection(str(k).lower() for k in value):
            raise ValueError("seller row contains a forbidden secret field")
        return SellerRow(str(value.get("seller", value.get("vendor", ""))), str(value.get("model", "")), float(value.get("price", 0.0)), float(value.get("success_rate", value.get("successRate", 0.0))))


class TokenOptimizer:
    """Local decision engine. It never performs network I/O or config writes."""
    def __init__(self, config: Optional[OptimizerConfig] = None, journal: Optional[DecisionJournal] = None):
        self.config = config or OptimizerConfig()
        self.journal = journal or DecisionJournal()
        self._last_evaluated: Optional[float] = None
        self._last_changed: Optional[float] = None

    def evaluate(self, current_model: Optional[str], candidates: Iterable[Any], *, work: Any = None, task_complexity: float = 0.5, now: Any = None, apply_model: Optional[Callable[[str], None]] = None) -> Decision:
        timestamp = _timestamp(now) if now is not None else _now().timestamp()
        iso = datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
        if work is not None and active_work_detected(work, now=timestamp, idle_after_seconds=self.config.idle_after_seconds):
            return self._record(Decision("hold", current_model, current_model, 0.0, 0.0, "active_work", self.config.dry_run, iso))
        if self._last_evaluated is not None and timestamp - self._last_evaluated < self.config.cadence_seconds:
            return self._record(Decision("hold", current_model, current_model, 0.0, 0.0, "cadence", self.config.dry_run, iso))
        self._last_evaluated = timestamp
        best, best_score, current_score = choose_model(candidates, current_model=current_model, task_complexity=task_complexity, min_improvement=self.config.min_improvement, hysteresis=self.config.hysteresis)
        if not best or best.model == current_model:
            return self._record(Decision("hold", current_model, current_model, best_score, current_score, "no_improvement", self.config.dry_run, iso))
        if self._last_changed is not None and timestamp - self._last_changed < self.config.cooldown_seconds:
            return self._record(Decision("hold", current_model, current_model, best_score, current_score, "cooldown", self.config.dry_run, iso))
        action = "recommend" if self.config.dry_run else "apply"
        if action == "apply" and apply_model is not None:
            apply_model(best.model)
            self._last_changed = timestamp
        return self._record(Decision(action, current_model, best.model, best_score, current_score, "improvement", self.config.dry_run, iso))

    def _record(self, decision: Decision) -> Decision:
        self.journal.record(decision)
        return decision
