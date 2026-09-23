# Cost-Aware Inference Router — Prototype Spec

**Plan item:** §7 "Prove the routing idea" (`unified-model-serving-plan.md`)
**Author:** Sandeep Gupta · **Date:** 2026-09-22 · **Status:** Draft for sign-off

---

## 1. Purpose & scope

Build a **functional prototype** that proves the routing idea from the plan:
given a batch of inference requests and a pool of mocked machines, assign each
request to the machine that **respects its latency SLA at the lowest cost**, then
report **cost per successful prediction per model** and compare the router
against always-cheapest and always-fastest baselines.

**In scope**
- Deterministic batch simulator with a CLI (`route` a scenario → report).
- The plan's 4-step pipeline: Match → Check time → Choose cost → Watch.
- Load-aware latency estimation; unassigned handling; cost report + baselines.
- Unit tests and a couple of example scenarios.

**Out of scope (noted for later)**
- Live HTTP service, real GPUs, autoscaling, real billing integration.
- Multi-version canary routing (we keep the requested version; see §4.1).
- Persistent state / concurrency across processes.

**Decisions locked (this spec):** batch simulator + CLI · Python stdlib only ·
load-aware latency curve. Add **logger support** (structured, `--log-level`) per
the standing dev-task convention.

---

## 2. Data model

All inputs come from a single JSON **scenario** file. Types below are the
in-memory `@dataclass` shapes.

### 2.1 Request
| Field | Type | Meaning |
|---|---|---|
| `id` | str | Unique request id |
| `model_id` | str | Model **version** requested (e.g. `search-ranker:v3`) |
| `priority` | enum `high\|medium\|low` | Scheduling importance |
| `sla_ms` | float | Max acceptable end-to-end latency (ms) |

### 2.2 Instance (mocked machine)
| Field | Type | Meaning |
|---|---|---|
| `id` | str | Unique instance id |
| `kind` | enum `cpu\|gpu` | Hardware class |
| `models` | list[str] | Model versions this instance can serve |
| `hourly_cost` | float | USD/hour when running (drives cost) |
| `base_latency_ms` | map model_id→float | **Measured** service time per model at **zero load**. **Optional/partial** — any servable model without an entry is filled from defaults (§2.5). |
| `concurrency` | int | Max simultaneous in-flight requests (capacity) |
| `load` | int | In-flight requests at scenario start |
| `healthy` | bool | Unhealthy instances are never matched |

> GPU instances typically have **lower `base_latency_ms`** but **higher
> `hourly_cost`**; CPU instances the reverse. This is what makes the
> cost-vs-SLA tradeoff real.
>
> Base times are **ideally real measurements** from load tests / production
> traces. When a measurement isn't available yet, the resolver (§2.5) supplies a
> reasonable default so the prototype still runs — and flags it so the placeholder
> gets replaced by a real number.

### 2.3 Scenario (top-level file)
```json
{
  "name": "flash-sale",
  "config": {
    "queue_factor": 1.0, "watch_miss_threshold": 0.5, "watch_window": 10,
    "default_base_latency_ms": { "cpu": 80, "gpu": 20 },
    "model_base_latency_ms":   { "search-ranker:v3": { "cpu": 120, "gpu": 25 } }
  },
  "requests": [ { "id": "r1", "model_id": "search-ranker:v3", "priority": "high", "sla_ms": 80 } ],
  "instances": [ { "id": "gpu-1", "kind": "gpu", "models": ["search-ranker:v3"],
                   "hourly_cost": 3.60, "base_latency_ms": {"search-ranker:v3": 20},
                   "concurrency": 4, "load": 1, "healthy": true } ]
}
```

### 2.4 Base-time resolution (measured → default)

Every servable **(instance, model)** pair must end up with a positive base time,
but it does **not** have to be spelled out. The resolver fills each pair by the
first source that applies, and records which one — so measurements are used when
present and defaults are visible and replaceable:

| Order | Source | `source` tag |
|---|---|---|
| 1 | Instance's own `base_latency_ms[model]` (a real measurement) | `measured` |
| 2 | `config.model_base_latency_ms[model][kind]` (per-model, per-kind default) | `model-default` |
| 3 | `config.default_base_latency_ms[kind]` (per-kind default) | `kind-default` |
| 4 | Built-in fallback: **gpu = 20 ms, cpu = 80 ms** | `builtin-default` |

- Resolution happens **once at load**, producing a fully-populated
  `resolved_base_ms[(instance, model)]` the router reads from. §3 always sees a
  real number.
- The report and logs show **how many pairs used a default and which** (a
  `defaulted_base_times` list), because these are placeholders that **should be
  replaced with actual measurements**. This is a warning surface, not a failure.
- Built-in constants and the per-kind defaults live in one config block so they
  are easy to tune as real numbers arrive.

### 2.5 Validation (fail-fast at scenario load)

The loader **rejects the scenario** (clear error, non-zero exit) only for things
it genuinely cannot resolve. A missing base time is **not** one of them — it is
resolved and flagged per §2.4. Hard-fail rules:

- **Referenced models are servable** — every `request.model_id` is served by at
  least one instance; otherwise the request can only ever be `unassigned`, so we
  warn loudly (still routed, still reported as unassigned — we don't hide it).
- **Sane numbers** — `hourly_cost > 0`, `concurrency ≥ 1`, `0 ≤ load ≤ concurrency`,
  `sla_ms > 0`, and every **provided** or **default** `base_latency_ms > 0`.
  Unique `id`s for requests and instances.
- **Enums valid** — `kind ∈ {cpu,gpu}`, `priority ∈ {high,medium,low}`.
- **Defaults resolvable** — a per-kind default (config or built-in) exists for
  every `kind` present, so resolution (§2.4) can never leave a pair empty.

---

## 3. Core formulas

**Utilization** of an instance with `n` in-flight and capacity `C`:
`u = n / C`.

**Predicted latency** for a candidate request on instance `i` running model `m`,
*after* the request would be admitted (so `n' = n + 1`):
```
predicted_ms = base_latency_ms[m] * (1 + queue_factor * n'/C)
```
This **linear** load penalty is the locked default.
- `queue_factor` (default 1.0) tunes how sharply latency degrades under load.
- If `n' > C` the instance is **at/over capacity** → not a candidate (fails Match).

**Per-request cost** = occupancy time × price:
`cost = (predicted_ms / 1000 / 3600) * hourly_cost`  (USD).
Faster machines occupy for less time; the router weighs the higher GPU hourly
rate against its shorter occupancy.

> Linear is transparent and monotonic — enough to prove the routing behavior.
> A sharper curve (M/M/1-style `1/(1-u)`) or one fitted from real
> latency-at-load traces can replace it later; it lives behind one function
> (`latency.py`), so the router logic never changes.

---

## 4. Routing algorithm

Requests are processed in a **deterministic order**: by priority
(`high`→`low`), then tightest `sla_ms` first, then `id`. This sends scarce fast
capacity to the requests that need it most. As each request is assigned, the
chosen instance's `load` increments, so later requests see realistic contention.
Lower-priority requests are ordered behind higher ones and never proactively
dropped; under scarcity they may be starved (→ `unassigned`), which is accepted
for now and reported per priority (§9.2, §10).

For each request, the 4 plan steps:

### 4.1 Match
Keep instances that are **healthy**, **serve `request.model_id`**, and have
**free capacity** (`load + 1 ≤ concurrency`). The requested version is kept as-is
(no version substitution in the prototype).

### 4.2 Check time
Compute `predicted_ms` (§3) for each matched instance. **Drop** any where
`predicted_ms > request.sla_ms`. Instances flagged by Watch (§4.4) as a
missing pool are **deprioritized** (only used if nothing better qualifies).

### 4.3 Choose cost
Among survivors, pick the **lowest per-request `cost`** (§3). Ties broken by
lower predicted latency, then instance id. Assign; increment that instance's
load. Record the decision.

If **no instance qualifies** → record request as **`unassigned`** with the
reason (no-match / capacity / sla-miss). We do **not** silently route to a
machine that will miss the SLA.

### 4.4 Watch
Maintain a rolling per-instance window (`watch_window`, default 10) of recent
outcomes. If an instance's miss rate exceeds `watch_miss_threshold` (default
0.5), mark it **degraded**: emit an alert (log) and deprioritize it in §4.2 so
new traffic shifts to faster/less-loaded capacity.

---

## 5. Baselines (for comparison)

Same request set, same pool, three comparison policies re-run independently.
All spill on **capacity** (a full instance is never a candidate); they differ in
whether they respect the SLA:

- **always-cheapest** — among instances with capacity (ignoring SLA), pick lowest
  `hourly_cost`. Naive floor: measures cost if we ignored latency. It accepts a
  request onto a cheap instance that has *capacity* even when that instance will
  *miss the SLA*, so it "buys failures" (high `missed_sla`).
- **cheapest-fit** — improved cheapest: among instances that have capacity **and**
  meet the SLA at current load, pick lowest `hourly_cost`; spill up the cost
  ladder past any instance that is full *or* would miss; record `unassigned` only
  when nothing can meet the SLA. This is the "go to the next instance if the
  cheapest can't do the job" policy.
- **always-fastest** — among instances with capacity, pick lowest `predicted_ms`.
  Measures latency-first cost.

The report shows the cost-aware router beside all three, so the tradeoff is
visible. **cost-aware vs cheapest-fit:** both serve only SLA-meeting instances;
cheapest-fit tie-breaks on **hourly rate** while the router tie-breaks on
**per-request cost** (occupancy × hourly). They coincide when the cheapest-hourly
SLA-meeting instance is also the cheapest per request; the router wins when a
pricier-hourly but faster instance has lower occupancy cost.

---

## 6. Output: cost report

Printed as a table (and available as JSON via `--json`).

**Per model**
| Column | Meaning |
|---|---|
| requests | total requested |
| served | assigned within SLA |
| missed_sla | assigned but predicted to miss (should be 0 for router; may be >0 for baselines) |
| unassigned | no qualifying machine |
| total_cost | USD across all *assigned* requests (served + missed_sla) |
| cost_per_success | `total_cost / served` — the per-winner cost metric |

**Per priority**: `served` / `unassigned` for `high` / `medium` / `low` — makes
starvation of lower priorities under scarcity visible (see §9.2).

**Overall summary**: a 4-row comparison (cost-aware router · always-cheapest ·
cheapest-fit · always-fastest) on served, **drop rate**, SLA-hit rate, total cost,
cost per successful prediction, and the **combined metric** below.

> **`drop_rate = (missed_sla + unassigned) / total`** is the fair cross-policy
> failure metric: a request that misses its SLA is a failure just like an
> unassigned one, whichever policy caused it. **`total_cost` alone is
> misleading** — the baselines never leave a request unassigned, so they *pay for
> SLA failures* and serve a different set. (This is why always-cheapest — cheapest
> *hourly rate*, not cheapest *total* — can show a higher total cost *and* a worse
> cost/success than the router: it buys cheap failures. Cost = occupancy_time ×
> hourly, so cramming a cheap, slow box inflates occupancy and still misses.)

### 6.1 Combined success metric

Cost/success rewards low spend **per winner** but ignores how many requests were
dropped — a policy can look cheap by serving only easy requests. Drop rate does
the opposite (ignores cost). We combine them by pricing each drop:

> **`effective_cost_per_request = (total_cost + drop_penalty_usd × dropped) / total_requests`**

- `drop_penalty_usd` (config, default 0) is the **business cost of one failed
  prediction** — lost revenue, bad UX, a fraud check that didn't run in time. It
  is the one number that says how much we dislike a drop relative to a dollar of
  compute.
- The metric is normalized over **offered** requests (not served), so policies
  that serve different sets compare fairly, and it is a single dollar figure —
  **lower is better**. The report ranks policies by it and names the best.
- With `drop_penalty_usd = 0` drops are not priced (it degenerates to average
  spend, which rewards cheap failures) — so a meaningful comparison sets it > 0.
  It reduces to the plan's "cost per successful prediction" spirit while making
  the cost of dropping explicit.

This is the metric to optimize: it captures "serve as much as possible **and**
serve it cheaply," with `drop_penalty_usd` setting the exchange rate between the
two.

**Alerts**: any Watch degradations, with instance id and window miss rate.

**Data-quality note**: count and list of **defaulted base times** (§2.4) —
"N of M (instance, model) pairs used estimated base latency; replace with
measurements." Makes the reliance on placeholders visible in every run.

---

## 7. Proposed file layout

```
router/
  __init__.py
  models.py        # dataclasses: Request, Instance, Scenario, Decision, Report
  latency.py       # predicted_latency(), per_request_cost()
  router.py        # CostAwareRouter (Match→CheckTime→ChooseCost→Watch)
  baselines.py     # always_cheapest, always_fastest policies
  report.py        # aggregation + table/JSON rendering
  cli.py           # argparse entrypoint: `python -m router.cli route <scenario.json>`
  logging_setup.py # structured logger, --log-level
scenarios/
  simple.json
  flash-sale.json     # GPU/CPU mix under load, some unassigned; sets drop_penalty
  cost-tradeoff.json  # cheap-slow vs pricey-fast: cost-aware beats cheapest-fit
tests/
  test_latency.py
  test_router.py
  test_baselines.py
  test_report.py
README.md          # how to run + example output
```

**CLI sketch**
```
python -m router.cli route scenarios/flash-sale.json                          # table only
python -m router.cli route scenarios/flash-sale.json --json report.json        # table + JSON file
python -m router.cli route scenarios/flash-sale.json --json -                  # JSON to stdout
python -m router.cli route scenarios/flash-sale.json --log-level INFO
```

---

## 8. Test plan

- **latency**: monotonic in load; over-capacity excluded; cost math correct.
- **router**: prefers cheaper qualifying instance; drops SLA-missers; records
  unassigned when nothing qualifies; priority ordering respected; Watch
  deprioritizes a degraded pool.
- **baselines**: always-cheapest can incur SLA misses; always-fastest costs ≥
  router on the mixed scenario.
- **report**: aggregation totals and `cost_per_success` correct; JSON schema
  stable.
- **end-to-end**: `flash-sale.json` produces a deterministic report (golden).

**Acceptance:** router achieves SLA-hit rate ≥ always-cheapest **and** cost ≤
always-fastest on `flash-sale.json`, with a non-zero `unassigned` count proving
we surface infeasible demand rather than hide it.

---

## 9. Resolved decisions

1. **Cost basis — occupancy-time × hourly** (`cost = predicted_ms/1000/3600 ×
   hourly_cost`). Locked (§3). A flat per-request price is not used.
2. **Priority — ordered, never dropped.** Requests are processed
   `high → medium → low` (then tightest SLA, then id); lower-priority requests
   are only served *after* higher ones, but are never proactively dropped to free
   capacity. **Known limitation:** under scarcity, `medium`/`low` can be
   **starved** (end up `unassigned` because fast capacity is used up). Accepted
   for the prototype — the report makes starvation visible via per-priority
   `unassigned` counts. A fairness/reservation scheme (e.g. reserve a capacity
   share per priority, or aging) is deferred; see §10.
3. **Report format — terminal table AND JSON, both from one run.** The same
   aggregation renders both. Default run prints the **table** to stdout;
   `--json PATH` **also** writes the JSON report to a file in the same run (so you
   get the human table on screen and the machine JSON on disk at once).
   `--json -` prints JSON to stdout instead of the table (for piping). The table
   is for humans; JSON is for tests, tooling, and golden comparisons.

## 10. Deferred / future work

- **Priority fairness** — reservation share or aging so `medium`/`low` aren't
  starved under sustained scarcity (revisit after we see real starvation rates).
- Sharper latency curve fitted from measured latency-at-load (§3).
- Multi-version routing / approved-version substitution (§4.1).
