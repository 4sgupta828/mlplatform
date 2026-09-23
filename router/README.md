# Cost-Aware Inference Router — Prototype

A functional prototype of the router described in
[`../unified-model-serving-plan.md`](../unified-model-serving-plan.md) §7 and
specified in [`../router-prototype-spec.md`](../router-prototype-spec.md).

Given a batch of inference requests and a pool of mocked CPU/GPU instances, it
assigns each request to the machine that **respects the latency SLA at the lowest
cost**, then reports **cost per successful prediction per model** and compares
against always-cheapest and always-fastest baselines.

No dependencies — Python 3.9+ standard library only.

> For how the code is organized and how the pieces come together to test the
> idea, see [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Run

```bash
# Table to stdout
python3 -m router.cli route scenarios/flash-sale.json

# Table to stdout AND JSON to a file (one run)
python3 -m router.cli route scenarios/flash-sale.json --json report.json

# JSON to stdout (for piping/tests)
python3 -m router.cli route scenarios/flash-sale.json --json -

# Verbose logging (to stderr; never mixes with the report on stdout)
python3 -m router.cli route scenarios/flash-sale.json --log-level INFO
```

## Example output (`scenarios/flash-sale.json`)

```
Policy comparison (drop_penalty=$0.00005; eff_cost/req is the combined metric — lower is better)
policy            served  dropped%  sla_hit    total_cost    cost/success    eff_cost/req
-----------------------------------------------------------------------------------------
cost-aware             8      20%      80%     $0.000174       $0.000022       $0.000027
always-cheapest        6      40%      60%     $0.000184       $0.000031       $0.000038
cheapest-fit           8      20%      80%     $0.000174       $0.000022       $0.000027
always-fastest         8      20%      80%     $0.000221       $0.000028       $0.000032

Best by effective cost/request: cost-aware ($0.000027)
```

The three comparison policies (all spill on capacity):
- **always-cheapest** — cheapest *hourly rate* with capacity, ignoring SLA. Naive
  floor; it "buys failures" (40% dropped here — all silent SLA misses).
- **cheapest-fit** — improved cheapest: cheapest hourly among instances that have
  capacity **and** meet the SLA; spills past would-miss instances (20% dropped).
- **always-fastest** — lowest latency with capacity, ignoring cost (most expensive).

### Metrics

- **drop_rate** = `(missed_sla + unassigned) / total` — the fair failure metric.
- **cost/success** = `total_cost / served` — cost per winner (ignores drops).
- **eff_cost/req** = `(total_cost + drop_penalty_usd × dropped) / total` — the
  **combined metric**: prices each drop at the business cost of a failed
  prediction and normalizes over offered requests. Lower is better; the report
  ranks by it. Set `drop_penalty_usd` in the scenario `config` (0 = drops not
  priced).

> **Why can always-cheapest cost more in total?** Cost is `occupancy_time ×
> hourly_rate`, not the hourly rate. always-cheapest never leaves a request
> unassigned, so it crams requests onto cheap, slow boxes that **miss the SLA
> anyway** — paying for failures. `cheapest-fit` fixes this by skipping would-miss
> instances.
>
> **cheapest-fit vs cost-aware:** both only use SLA-meeting instances; cheapest-fit
> tie-breaks on hourly rate, the router on per-request cost (occupancy × hourly).
> They tie when the cheapest-hourly instance is also cheapest per request; the
> router wins when a pricier-but-faster instance has lower occupancy cost — see
> [Where the router beats a smart baseline](#where-the-router-beats-a-smart-baseline).

## Where the router beats a smart baseline

`cheapest-fit` is a strong baseline — it already respects SLAs, so on most
scenarios it matches the router's **drop rate**. To see the router's real edge you
need a pool where the cheapest *hourly* instance is **not** the cheapest *per
request*. `scenarios/cost-tradeoff.json` is built for exactly that:

| Instance | Price | Latency | Meets 200ms SLA? |
|---|---|---|---|
| `cpu-slow` | $0.50/hr | 90ms | yes |
| `gpu-fast` | $1.20/hr | 20ms | yes |

```bash
python3 -m router.cli route scenarios/cost-tradeoff.json
```

```
policy         served  dropped%   total_cost    cost/success   routing
cost-aware          6       0%     $0.000063     $0.000011      all -> gpu-fast
cheapest-fit        6       0%     $0.000119     $0.000020      all -> cpu-slow
```

Same SLAs met, same zero drops — but **cost-aware is ~47% cheaper per success.**
Cost is `occupancy_time × hourly_rate`, so the per-request cost is:

- `cpu-slow`: 90ms × $0.50/hr → proxy **45**
- `gpu-fast`: 20ms × $1.20/hr → proxy **24**  ← cheaper

`cheapest-fit` picks `cpu-slow` because $0.50/hr looks cheapest; the router sees
the slow CPU actually costs *more per request* than the fast GPU and routes
everything to the GPU. That occupancy-awareness is the router's edge.

## How it works (spec §4)

For each request, in priority → tightest-SLA order:

1. **Match** — healthy instances that serve the model version and have free capacity.
2. **Check time** — drop instances whose *load-aware* predicted latency exceeds the SLA.
3. **Choose cost** — route to the lowest per-request cost (occupancy time × hourly price).
4. **Watch** — if a pool keeps missing, mark it degraded, alert, and shift new traffic away.

Base latencies are **measured when available**, otherwise filled from defaults
and flagged in the report ("replace with measurements").

## Files

| File | Contents |
|---|---|
| `models.py` | Data model, scenario loading, base-time resolution, validation |
| `latency.py` | Load-aware latency + per-request cost formulas |
| `router.py` | `CostAwareRouter` — the 4-step pipeline + Watch |
| `baselines.py` | always-cheapest / always-fastest comparison policies |
| `report.py` | Aggregation + table/JSON rendering |
| `cli.py` | `python -m router.cli route <scenario.json>` |
| `logging_setup.py` | Structured logging (stderr) |
| `../scenarios/` | Example scenarios (`simple.json`, `flash-sale.json`) |
| `../tests/` | `python3 -m unittest discover -s tests` |
