"""Data model + scenario loading, validation, and base-time resolution.

Spec references: §2 (data model), §2.4 (base-time resolution), §2.5 (validation).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

log = logging.getLogger("router.models")

# Built-in fallback base latencies (ms) at zero load, per hardware kind.
# Last resort in the resolution chain (§2.4). Tune as real numbers arrive.
BUILTIN_BASE_LATENCY_MS: dict[str, float] = {"gpu": 20.0, "cpu": 80.0}


class ScenarioError(ValueError):
    """Raised when a scenario is invalid and cannot be resolved (§2.5)."""


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"

    @property
    def rank(self) -> int:
        # Lower rank = served first.
        return {"high": 0, "medium": 1, "low": 2}[self.value]


class Kind(str, Enum):
    cpu = "cpu"
    gpu = "gpu"


@dataclass(frozen=True)
class Request:
    id: str
    model_id: str
    priority: Priority
    sla_ms: float


@dataclass
class Instance:
    id: str
    kind: Kind
    models: list[str]
    hourly_cost: float
    base_latency_ms: dict[str, float]  # measured entries only (may be partial)
    concurrency: int
    load: int = 0
    healthy: bool = True


@dataclass
class Config:
    queue_factor: float = 1.0
    watch_miss_threshold: float = 0.5
    watch_window: int = 10
    # Business cost (USD) of one dropped request (missed_sla or unassigned), used
    # by the combined effective-cost metric. 0 = drops not priced (report cost only).
    drop_penalty_usd: float = 0.0
    # kind -> default base latency (ms)
    default_base_latency_ms: dict[str, float] = field(default_factory=dict)
    # model -> {kind -> default base latency (ms)}
    model_base_latency_ms: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass
class ResolvedBase:
    """A single resolved (instance, model) base time and where it came from."""

    instance_id: str
    model_id: str
    kind: str
    value_ms: float
    source: str  # measured | model-default | kind-default | builtin-default


@dataclass
class Scenario:
    name: str
    config: Config
    requests: list[Request]
    instances: list[Instance]
    # (instance_id, model_id) -> ResolvedBase
    resolved_base: dict[tuple[str, str], ResolvedBase] = field(default_factory=dict)

    @property
    def instances_by_id(self) -> dict[str, Instance]:
        return {i.id: i for i in self.instances}

    def base_ms(self, instance_id: str, model_id: str) -> float:
        return self.resolved_base[(instance_id, model_id)].value_ms

    @property
    def defaulted_bases(self) -> list[ResolvedBase]:
        return [r for r in self.resolved_base.values() if r.source != "measured"]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_scenario(path: str) -> Scenario:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return scenario_from_dict(raw)


def scenario_from_dict(raw: dict) -> Scenario:
    if not isinstance(raw, dict):
        raise ScenarioError("scenario must be a JSON object")

    name = raw.get("name", "unnamed")
    config = _parse_config(raw.get("config", {}) or {})
    requests = _parse_requests(raw.get("requests", []))
    instances = _parse_instances(raw.get("instances", []))

    scenario = Scenario(name=name, config=config, requests=requests, instances=instances)
    scenario.resolved_base = _resolve_base_times(instances, config)
    _validate(scenario)
    _log_defaults(scenario)
    return scenario


def _parse_config(raw: dict) -> Config:
    return Config(
        queue_factor=float(raw.get("queue_factor", 1.0)),
        watch_miss_threshold=float(raw.get("watch_miss_threshold", 0.5)),
        watch_window=int(raw.get("watch_window", 10)),
        drop_penalty_usd=float(raw.get("drop_penalty_usd", 0.0)),
        default_base_latency_ms={k: float(v) for k, v in (raw.get("default_base_latency_ms", {}) or {}).items()},
        model_base_latency_ms={
            m: {k: float(v) for k, v in kinds.items()}
            for m, kinds in (raw.get("model_base_latency_ms", {}) or {}).items()
        },
    )


def _parse_requests(raw: list) -> list[Request]:
    out: list[Request] = []
    for i, r in enumerate(raw):
        try:
            out.append(
                Request(
                    id=str(r["id"]),
                    model_id=str(r["model_id"]),
                    priority=Priority(r["priority"]),
                    sla_ms=float(r["sla_ms"]),
                )
            )
        except (KeyError, ValueError) as exc:
            raise ScenarioError(f"request[{i}] is invalid: {exc}") from exc
    return out


def _parse_instances(raw: list) -> list[Instance]:
    out: list[Instance] = []
    for i, inst in enumerate(raw):
        try:
            out.append(
                Instance(
                    id=str(inst["id"]),
                    kind=Kind(inst["kind"]),
                    models=[str(m) for m in inst["models"]],
                    hourly_cost=float(inst["hourly_cost"]),
                    base_latency_ms={k: float(v) for k, v in (inst.get("base_latency_ms", {}) or {}).items()},
                    concurrency=int(inst["concurrency"]),
                    load=int(inst.get("load", 0)),
                    healthy=bool(inst.get("healthy", True)),
                )
            )
        except (KeyError, ValueError) as exc:
            raise ScenarioError(f"instance[{i}] is invalid: {exc}") from exc
    return out


# --------------------------------------------------------------------------- #
# Base-time resolution (§2.4): measured -> model-default -> kind-default -> builtin
# --------------------------------------------------------------------------- #

def _resolve_base_times(instances: list[Instance], config: Config) -> dict[tuple[str, str], ResolvedBase]:
    resolved: dict[tuple[str, str], ResolvedBase] = {}
    for inst in instances:
        kind = inst.kind.value
        for model in inst.models:
            value, source = _resolve_one(inst, model, kind, config)
            resolved[(inst.id, model)] = ResolvedBase(
                instance_id=inst.id,
                model_id=model,
                kind=kind,
                value_ms=value,
                source=source,
            )
    return resolved


def _resolve_one(inst: Instance, model: str, kind: str, config: Config) -> tuple[float, str]:
    measured = inst.base_latency_ms.get(model)
    if measured is not None and measured > 0:
        return measured, "measured"

    model_defaults = config.model_base_latency_ms.get(model, {})
    if kind in model_defaults and model_defaults[kind] > 0:
        return model_defaults[kind], "model-default"

    if kind in config.default_base_latency_ms and config.default_base_latency_ms[kind] > 0:
        return config.default_base_latency_ms[kind], "kind-default"

    if kind in BUILTIN_BASE_LATENCY_MS:
        return BUILTIN_BASE_LATENCY_MS[kind], "builtin-default"

    # Unreachable in practice (all kinds have a builtin); guarded by validation.
    raise ScenarioError(f"no base latency resolvable for instance={inst.id} model={model} kind={kind}")


# --------------------------------------------------------------------------- #
# Validation (§2.5) — hard-fail only on genuinely unresolvable input
# --------------------------------------------------------------------------- #

def _validate(scenario: Scenario) -> None:
    errors: list[str] = []

    # Unique ids.
    _check_unique(errors, [r.id for r in scenario.requests], "request id")
    _check_unique(errors, [i.id for i in scenario.instances], "instance id")

    # Sane numbers per instance.
    for inst in scenario.instances:
        if inst.hourly_cost <= 0:
            errors.append(f"instance {inst.id}: hourly_cost must be > 0")
        if inst.concurrency < 1:
            errors.append(f"instance {inst.id}: concurrency must be >= 1")
        if not (0 <= inst.load <= inst.concurrency):
            errors.append(f"instance {inst.id}: load {inst.load} not in [0, concurrency={inst.concurrency}]")
        for model, val in inst.base_latency_ms.items():
            if val <= 0:
                errors.append(f"instance {inst.id}: base_latency_ms[{model}] must be > 0")

    # Resolved bases must all be positive (defence in depth).
    for rb in scenario.resolved_base.values():
        if rb.value_ms <= 0:
            errors.append(f"instance {rb.instance_id}: resolved base for {rb.model_id} must be > 0")

    # Sane numbers per request.
    for req in scenario.requests:
        if req.sla_ms <= 0:
            errors.append(f"request {req.id}: sla_ms must be > 0")

    # Defaults resolvable for every kind present.
    kinds_present = {i.kind.value for i in scenario.instances}
    for kind in kinds_present:
        has_default = kind in scenario.config.default_base_latency_ms or kind in BUILTIN_BASE_LATENCY_MS
        if not has_default:
            errors.append(f"no default base latency available for kind '{kind}'")

    if errors:
        raise ScenarioError("invalid scenario:\n  - " + "\n  - ".join(errors))

    # Non-fatal: warn when a requested model is served by no eligible instance.
    for req in scenario.requests:
        eligible = [i for i in scenario.instances if i.healthy and req.model_id in i.models]
        if not eligible:
            log.warning(
                "request %s asks for model %s served by no healthy instance -> will be unassigned",
                req.id, req.model_id,
            )


def _check_unique(errors: list[str], ids: list[str], label: str) -> None:
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            errors.append(f"duplicate {label}: {i}")
        seen.add(i)


def _log_defaults(scenario: Scenario) -> None:
    defaulted = scenario.defaulted_bases
    if defaulted:
        log.warning(
            "%d of %d (instance, model) base times use estimated defaults; replace with measurements",
            len(defaulted), len(scenario.resolved_base),
        )
        for rb in defaulted:
            log.info("  defaulted base: instance=%s model=%s -> %.1fms (%s)",
                     rb.instance_id, rb.model_id, rb.value_ms, rb.source)
