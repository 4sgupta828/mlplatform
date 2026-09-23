# Unified Model Serving Platform — Design

> Working doc. Answers organized from my own notes and completed end-to-end. Remaining `MEASURE` markers are baselines only I can fill from real telemetry.

---

## 0. Context

### Scenario
Quince runs a growing portfolio of ML models — product recommendations, dynamic pricing, fraud detection, search ranking, and personalization. Each was built and deployed independently by separate teams, leaving a **fragmented infrastructure landscape with no shared serving layer**.

Pain points from this fragmentation:
- Inference costs are growing faster than revenue, with **duplicated GPU provisioning** across teams.
- Latency SLAs are inconsistent — some models respond in 20ms, others 500ms+ — with no clear accountability.
- No centralized visibility into **cost-per-prediction, model health, or capacity utilization**.
- On traffic spikes (e.g., flash sales), teams **manually scale** their own endpoints, often over-provisioning to avoid downtime.

**My role:** Sr. Engineering Manager for ML Infrastructure, owning end-to-end delivery of a Unified Model Serving Platform — vision, success metrics, project plan, technical design, and cross-team coordination — to ship infrastructure that is cost-efficient, performant, and operationally mature.

### Constraints (may conflict)
- **Cost pressure:** Leadership target of **30% inference cost reduction within 6 months**.
- **Urgent team needs:** Search Ranking and a new Personalization model launch **next quarter** and need a serving solution now — otherwise they'll spin up their own infra, worsening fragmentation.
- **Team capacity:** Start with **3 engineers**; can make a case for more headcount, but new hires take **2–3 months to onboard**.

### The Goal
- **Standardized Model Deployment:** single self-service path to production with consistent packaging, versioning, and rollback.
- **Cost Transparency & Optimization:** real-time cost visibility per model and team (inference + training); automated right-sizing / instance-selection recommendations (GPU vs. CPU, spot vs. on-demand); flag stale provisioned fleets carrying cost without use.
- **Operational Maturity:** health monitoring, alerting, and canary deployments so owners trust production stability.
- **Multi-Team Adoption:** shared infra across 4+ ML teams with different model types (real-time, near-real-time, batch) without a one-size-fits-all experience.

---

## 1. Project Planning

### 1.1 Impact Plan
_Success metrics — inference cost reduction %, P99 latency improvement, time-to-deploy, adoption rate._

**Principle:** every desired improvement must be measurable with a baseline, a target, a measurement method, and a reporting cadence. Metrics are grouped so no single one can be gamed (e.g., cutting cost by blowing latency).

| Metric | Baseline | Target | How measured | Cadence |
|---|---|---|---|---|
| Inference cost / 1k predictions | `MEASURE` | −30% in 6 mo | Cost attribution engine, per model/team | Weekly |
| GPU/CPU utilization | `MEASURE` (likely <30%) | >60% steady-state | Fleet telemetry | Weekly |
| P99 latency (per SLA tier) | 20ms / 100ms / 500ms+ | Within tier SLA, no regressions | Gateway + serving telemetry | Real-time dashboard |
| Time-to-deploy (new model → prod) | `MEASURE` (likely days–weeks) | < 1 day, self-service | Deploy pipeline timestamps | Per deploy |
| Platform adoption | 0 | 4+ teams; >80% of inference traffic on platform | Registry + traffic share | Monthly |
| Availability / SLO | `MEASURE` | 99.9% | SRE monitoring | Real-time + monthly review |

**North Star:** **cost-per-prediction at a fixed latency SLA** — captures the cost↔latency tradeoff in one number, so we can't win one metric by quietly losing the other.

**Guardrail metrics** (must not regress while we chase the above): per-model business KPIs (CTR, conversion, GMV, fraud catch-rate), error rate, and on-call load.

**Where the gains come from** (summary — mechanism lives in §2):
- **Latency** = feature queries + preprocessing + inference + postprocessing. Biggest wins: general query optimization, **batching feature fetches shared across models in one request**, and concurrent queries where possible.
- **Inference latency:** GPUs cut latency for heavy models but add cost and demand high GPU utilization — reserve them for models that must fit under the request budget (~1s). For the rest, benchmark runtimes and pick one that's well-supported (inference failures are hard to debug).
- **Cost:** mostly from **maximizing CPU/GPU utilization (fewer instances)** + caching safe recompute. Other levers: right-sizing, spot vs. on-demand, scale-to-zero, multi-model packing on shared GPUs, and model optimization (quantization/distillation).
- **Time-to-deploy:** (1) developer due diligence; (2) dev env mirroring prod continuously (≈day-old snapshot); (3) validation that what the model needs exists in prod (e.g., a new feature); (4) canary that ramps on stability; (5) automation of pre-model steps — training-set builds, training, regression testing.
- **Adoption:** at 4 teams, manageable by direct engagement + clearing blockers. Real risk is each team's decision/availability to migrate — mitigated by near-zero-effort migration, leaving them only: what to expect, how to troubleshoot, how to map old→new, who to reach for support.

### 1.2 Phased Project Plan
_How to stage delivery against the constraints._

**Framing:** first confirm whether 30%/6mo is a **hard or soft** goal — the two trigger different plans. Then stage into phases, deferring non-core scope. The organizing tension is *urgent teams need it now* vs. *build the durable platform* — resolved by making the two urgent teams my **first design partners**, not a distraction from the platform.

| Phase | Duration | Focus | Exit criteria |
|---|---|---|---|
| **Phase 1 — Core + first adopters** | ~Month 1–2 | Design + build the core serving path (registry, gateway, autoscaler, basic cost telemetry). Onboard Search Ranking + Personalization as design partners — they get a serving solution now; I get real requirements + a forcing function. Drop non-core scope. | Both urgent teams serving real traffic on the platform; core APIs validated with ML devs. |
| **Phase 2 — Benchmark & lock choices** | ~Month 2–3 | Benchmark serving runtimes + online/offline stores at representative RPS and request mix; lock key tech choices and optimization patterns (batching, caching, GPU vs. CPU tiers). | Runtime + store decisions signed off with data; reference architecture documented. |
| **Phase 3 — Stress-test per team** | ~Month 3–4 | Take one important model + its data from each remaining team (Recs, Pricing, Fraud); stress-test the design; close gaps. | Each team has ≥1 model validated on-platform; design gaps closed. |
| **Phase 4 — General rollout + cost push** | ~Month 4–6 | Migrate remaining models; turn on right-sizing, spot, scale-to-zero, multi-model packing, stale-fleet GC. This is where the **30% cost reduction** is realized. | ≥80% traffic on platform; 30% cost target hit or a data-backed re-forecast delivered. |

**Headcount ramp mapped to phases:** start 3 in Phase 1; make the case for +2 early so they finish 2–3mo onboarding by Phase 3–4 when rollout + cost work is heaviest (see §1.3).

### 1.3 Team Composition & Resource Plan
_Ideal team — roles, seniority, headcount._

**Culture I'm hiring for:** complementary skills; communication as a first-class requirement (silos are an anti-pattern to watch); collaboration to solve hard problems, distill learnings, and unblock each other; a psychologically safe environment where engineers express opinions freely.

**Starting shape (3, Phase 1):**
- **1 Principal/Staff (L6/L5)** — owns architecture; deep ML-serving/runtime expertise (Triton/KServe, GPU, batching).
- **2 Senior (L4/L5)** — one strong on **K8s/platform + autoscaling**, one on **serving/data path + observability**. Strongly opinionated engineers who've built production systems at consumer scale.

High ambiguity + shared-infra blast radius justify senior levels — this isn't a place for a junior-heavy team early.

**Ramp (make the case now, +2 by Phase 3–4):**
- **+1 Senior — Observability/FinOps** — cost attribution engine, monitoring/alerting, right-sizing recommendations.
- **+1 Mid/Senior — Developer experience & migration** — self-service tooling, migration automation, docs (directly de-risks adoption in §1.5).

**Also need:** a **TPM/PM partner** for cross-team rollout coordination and go/no-go tracking; a **named SRE partner** (embedded or on-call rotation) for shared-infra reliability. On-call load is real once we're shared infra — bake rotation into the plan, don't bolt it on.

### 1.4 Stakeholder Identification
_Roles and responsibilities (RACI-style, one line each)._

- **Leadership / Finance** — own the 30% cost target; approve funding & headcount. *(Accountable for outcome.)*
- **FinOps** — cost model, attribution methodology, budget accountability. *(Consulted on cost design; owns the number's definition.)*
- **SRE** — SLOs, on-call, incident response for shared infra. *(Responsible for reliability jointly with my team.)*
- **Platform / Infra Eng** — K8s, GPU capacity, networking, quotas. *(Responsible for underlying infra.)*
- **ML team leads — Recs / Pricing / Fraud / Search / Personalization** — adopters; own their models' requirements, SLAs, and migration timing. *(Responsible for their side of each migration; consulted on design.)*
- **Security / Compliance** — data handling and model governance, esp. the **fraud** model. *(Consulted; can gate.)*
- **Data / Feature platform** — feature stores, embeddings, precompute pipelines. *(Responsible for upstream data dependencies.)*
- **Product** — impact of latency/model changes on user-facing metrics. *(Informed; consulted on canary business-metric guardrails.)*

### 1.5 Communication and Rollout Plan
_Keep stakeholders informed; onboard incrementally; handle go/no-go._

- **Cadence, by audience:**
  - *Exec/Finance:* monthly — progress vs. the 30% target + adoption %, on a dashboard.
  - *ML team leads + partners:* weekly status + shared migration tracker.
  - *My team:* daily standup + async written updates.
- **Rollout:** incremental — simplest use-cases first, heavier/business-critical later. Learn from failures on non-critical cases; give each migration real bake time before the next.
- **Migration split:** teams get guidance + self-serve tooling for the team-specific parts (which models, what config); the platform absorbs everything general (e.g., all feature data). Goal: near-zero effort for adopters.
- **Go/no-go gate per migration** (explicit, signed off by model owner + SRE):
  1. Shadow parity — new system within X% of old on business + system metrics.
  2. P99 within the model's SLA tier.
  3. Cost ≤ old system (or a justified exception).
  4. Rollback tested and one-click.
  5. Runbook + on-call ownership in place.
  - No-go → stay on old system, fix, re-gate. Rollback is always the default-safe action.

---

## 2. Technical System Design

_Architectural overview of the unified serving platform._

**The core request patterns:**
- **(a) Retrieval (bulk/cheap):** query a source (DB, vector DB) for top-N candidates out of a large pool — e.g., 1k out of 100k.
- **(b) Ranking (expensive):** extract feature data per candidate, run inference on model X vNn, return ranked entities (top ~100 of the 1k). X is trained offline against an objective maximizing a business metric (click, purchase, watch).
- **(c) Other inference:** classification / prediction, etc.

**The unified serving platform** takes an incoming request and routes it to the right place, and offers an **orchestration layer** for multi-leg retrieval → merge → rank → re-rank, standardized as a **DAG**.

**Deployment topology (hybrid by default):**
- **Model-as-a-service:** each high-traffic model is its own auto-scaling service — isolation, no noisy-neighbor.
- **Multi-tenant packing:** long-tail low-traffic models share a service/GPU to reclaim idle capacity.
- Evaluate **KServe** as the base rather than building from scratch.

**Model deployment subsystem:** ML devs finalize → commit to the **online model registry** (name, version, manifest) → triggers a K8s rollout of vNn→vNn+1 or a new deployment.

**Garbage collection:** models with no traffic auto-scale down → single pod → flagged for removal.

**Cost attribution — 3 buckets:**
1. **Inference:** instance cost (regardless of utilization) × avg #instances/day × 30 days.
2. **Data:** the model's fractional share of data-source cost (by traffic it sends) + precompute to land its features/embeddings.
3. **Training:** training time × instances used.
- **Shared-instance case (hybrid):** split a packed instance's cost across tenants by a usage weight — request share × compute time — so multi-tenant models get fairly charged and the incentive to consolidate stays intact.

### 2.1 Core Components

- **Model Registry — Offline (MLflow):** aligned with model development; experiments, lineage, artifacts.
- **Model Registry — Online (custom):** source of truth for what's actually deployed; drives rollouts.
- **Serving Gateway:** routes to the right model/version by request params; enforces SLA tiers, priority, auth, and quotas; entry point for canary traffic splits.
- **Autoscaler:** two distinct concerns —
  - *Autoscaling:* HPA/KEDA on **custom metrics** (queue depth, GPU util, RPS) not just CPU; **scale-to-zero** for idle models; **warm pools** to absorb flash-sale spikes without cold-start.
  - *Instance sizing (right-sizing):* pick instance type from the model's memory/compute footprint + a smart feature cache; feeds recommendations back to the cost engine.
- **Cost Attribution Engine:** collects fleet + data + training telemetry → per-model/team rollups → surfaces right-sizing recommendations and **stale-fleet alerts** (provisioned but idle). Powers the §1.1 cost metric.
- **Monitoring / Alerting layer:** three planes —
  - *System:* P99 latency, error rate, GPU/CPU util, queue depth, saturation.
  - *Model:* score distribution, drift, feature freshness/availability.
  - *Business:* per-model KPI (CTR/GMV/fraud catch-rate). Alerts route to model owners with runbooks.

### 2.2 Routing & Scheduling
_Which instance handles a request; SLA vs. cost; batching._

Two layers, deliberately separated:
- **Gateway-level routing (global):** SLA-aware assignment across the fleet — priority queues per SLA tier, least-load / cost-aware instance selection, separate pools per tier so a 20ms model never queues behind a 500ms batch job. Preempt/shed low-priority work under saturation.
- **Runtime-level batching (per server, e.g., Triton):** dynamic batching with a **batch-size↔latency knob per tier** — larger batches for latency-tolerant tiers, near-zero for tight-SLA tiers.

**Why batching works:** it runs multiple requests through inference together at the same GPU cost — efficiency comes from keeping the GPU busy. GPUs are built for parallel matrix multiply, exactly what batching exploits. The tradeoff is higher utilization for slightly higher latency, tuned per SLA tier.

**Balancing SLA vs. cost:** tight-SLA/high-value traffic → dedicated, possibly GPU, low-batch pools. Latency-tolerant/long-tail → packed, high-batch, spot-backed pools. The router's objective is *lowest cost that still meets the SLA*, not lowest cost absolute.

### 2.3 Multi-Model Serving
_Multiple frameworks + inference patterns without a lowest-common-denominator experience._

- **Standardize the contract, not the framework:** a common container/interface (e.g., **Triton backends** or **ONNX**) lets PyTorch, TensorFlow, and ONNX models all serve behind one API. PyTorch is the *recommended default* (largest community, easiest support), but teams aren't forced onto it — that avoids the lowest-common-denominator trap.
- **Serving tiers by inference pattern** (not one-size-fits-all):
  - *Real-time:* synchronous, tight-SLA pools, low batch.
  - *Near-real-time:* async/queue-backed, moderate batching.
  - *Batch:* offline scoring jobs on spot/cheap capacity, high batch, scale-to-zero between runs.
- Each tier shares the registry, gateway, cost, and monitoring planes — so teams get a consistent platform experience with a serving profile that fits their pattern.

### 2.4 Safe Deployments
_Canary + automated rollback where correctness is statistical._

**Why canary is hard for ML:** at small traffic %, the model's real effect (generated fanout queries, inference cost) isn't visible, traffic isn't representative, and on fewer instances any single-instance failure is magnified.

**Approach — layered, metric-driven:**
1. **Shadow / offline replay first:** mirror live traffic to the new model with no user impact; compare outputs + cost/fanout before it serves anyone.
2. **Gradual ramp:** increase live traffic in increments of X% to full over ~a day — a far better survival test than a fixed small slice.
3. **Statistical correctness (the crux):** "correct" is a distribution, not a bit. Gate on **guardrail business metrics** (CTR, GMV, fraud catch-rate) via **A/B with significance testing**, alongside system health (latency, error, cost) and model-health signals (score distribution, drift).
4. **Automated rollback:** if any guardrail regresses beyond threshold with significance, auto-revert to the last-good version (one-click / automatic). Rollback is the default-safe action; ramp only continues while all guardrails hold.

---

## 3. Hands-on Prototype & AI Collaboration

_Cost-aware inference routing service (prototype)._

### 3.1 Input
- **Requests:** `{ request_id, model_id, priority (high|normal|low), latency_sla_ms }`.
- **Instances (mocked):** `{ instance_id, type (gpu|cpu), cost_per_hour, capacity_rps, current_load_rps, est_latency_ms }`.

### 3.2 Logic
Router assigns each request to the **cheapest instance that still meets its latency SLA and has capacity**, respecting priority under contention:
1. Filter instances to those whose `est_latency_ms ≤ latency_sla_ms` and `current_load < capacity`.
2. Among those, pick lowest `cost_per_hour` (tie-break: most headroom).
3. Under saturation, high-priority requests preempt / are placed first; low-priority may be shed or deferred to batch.
4. Emit a **cost report**: cost-per-model and total, plus SLA-hit rate and utilization — so routing decisions are auditable.

`IMPLEMENT: build this in the repo (Python), with the cost report + strategy comparison in §3.3.`

### 3.3 AI Audit & Prompt History
_Prompts used to generate/refine the code (to capture as I build):_
- **Routing logic:** prompt the assistant for an SLA-aware, cost-minimizing assignment; iterate to add priority/preemption and the "cheapest feasible instance" objective (not cheapest absolute).
- **Tests / simulations:** prompt for unit tests + a simulation comparing strategies (cost-first vs. latency-first vs. round-robin) and edge cases (instance unavailability, all-instances-saturated, SLA impossible to meet).
- **Iterating on hallucinations:** note where the AI invented APIs or mishandled the SLA-feasibility filter, how I caught it (failing test / manual trace), and how I re-prompted with the constraint made explicit.

---

## 4. Execution

### 4.1 Project Tracking
- Milestones = the Phase exit criteria in §1.2, tracked on a shared board with a weekly burn-up.
- **Risk log** (top risks: 30% target achievability, urgent-team timing, hiring latency) reviewed weekly with mitigations.
- **Dependency tracking** across teams (features, data, capacity) surfaced in the same tracker; blockers escalated at the weekly lead sync.

### 4.2 Deployment Considerations
- **Rollout:** incremental, non-critical-first (§1.5), each gated by go/no-go criteria.
- **QA:** shadow/replay + A/B before full traffic; regression tests on the deploy pipeline.
- **Guardrails:** SLA-tier isolation, per-tenant quotas, automated rollback on metric regression, warm pools for spikes, stale-fleet GC to stop cost creep.

### 4.3 Health & Monitoring Metrics
- **System:** P99 latency, error rate, GPU/CPU util, queue depth, saturation.
- **Model:** score distribution, drift, feature freshness/availability.
- **Business:** per-model KPI (CTR/GMV/fraud catch-rate).
- **Cost:** cost-per-prediction, utilization, idle/stale fleet.

### 4.4 Post-Release Success
Did we hit the §1.1 metrics? Specifically: sustained **30% cost reduction**, **>80% traffic on platform** across 4+ teams, **time-to-deploy < 1 day**, no SLA regressions, and flat-or-better incident rate. Success = the numbers hold for a full quarter post-rollout, not just at launch.

---

## 5. Talent Assessment
_Sample senior IC profiles I'd want (illustrative, not from personal experience) — each maps to a §1.3 specialization._

- **Profile A — Staff, ML Serving/Runtime.** Built a multi-framework inference platform (Triton/KServe) at consumer scale; owned GPU batching and latency optimization.
  - *Like:* depth in the exact runtime layer we're standardizing; has made the cost↔latency tradeoff in production, not just in theory.
- **Profile B — Senior, Platform/K8s + Autoscaling.** Owned autoscaling (HPA/KEDA, scale-to-zero) and capacity for a large GPU fleet; handled traffic-spike events.
  - *Like:* directly addresses the flash-sale/over-provisioning pain point; comfortable with warm pools and custom-metric scaling.
- **Profile C — Senior, Observability/FinOps.** Built cost-attribution + right-sizing tooling; drove a measurable cloud-cost reduction.
  - *Like:* has actually delivered a cost-reduction number like our 30% target; bridges eng and finance.
- **Profile D — Senior, Developer Experience / Migration.** Built self-service deploy platforms and led team migrations onto shared infra.
  - *Like:* de-risks adoption — turns migration into near-zero effort for the 4 teams, which is where rollouts usually stall.
