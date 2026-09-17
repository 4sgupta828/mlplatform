# Unified Model Serving Platform — Design

> Working doc. Questions and context imported from `Intake.md`. Answer inline under each prompt.

---

## 0. Context

### Scenario
Quince runs a growing portfolio of ML models — product recommendations, dynamic pricing, fraud detection, search ranking, and personalization. Each was built and deployed independently by separate teams, leaving a **fragmented infrastructure landscape with no shared serving layer**.

Pain points from this fragmentation:
- Inference costs are growing faster than revenue, with **duplicated GPU provisioning** across teams.
- Latency SLAs are inconsistent — some models respond in 20ms, others 500ms+ — with no clear accountability.
- No centralized visibility into **cost-per-prediction, model health, or capacity utilization**.
- On traffic spikes (e.g., flash sales), teams **manually scale** their own endpoints, often over-provisioning to avoid downtime.

**Your role:** Sr. Engineering Manager for ML Infrastructure, owning end-to-end delivery of a Unified Model Serving Platform — vision, success metrics, project plan, technical design, and cross-team coordination — to ship infrastructure that is cost-efficient, performant, and operationally mature.

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
_Success metrics for the project — e.g., inference cost reduction %, P99 latency improvement, time-to-deploy for new models, platform adoption rate across teams._
--All the explicit desired improvements must be measurable:
  Latency
  Cost Reduction
  Time to deploy
  Platform Adoption

--Latency improvement is function feature queries, pre processing, inferencing, post processing. 
-- Most of the benefits will come from general query optimization, query batching for same features to be queried across models that need to run in one request, concurrent queries where possible.

--Inference is bit trickier: For models that can run faster on GPUs, it can bring down latency but with added cost, with added requirement of effective GPU utilitization. This should be reserved for models with larger inferening latency that needs to significantly brought down so it stays within request serving time (typicall 1s or less)
--For other cases, explore few different runtimes like MLEAP, TensorFlow, Pytorch, Rayserve and see where latency is better by orders of magnitude. If not, pick a runtime that is supported well. As inference issues/failures are hard to debug.
--Most of the cost reduction is going to come by maximizing utilization of CPU/GPU (minizing instances)
-Another dimension is apply caching where ok to avoid expensive inferencing recompute.

-Time to deploy is function of few things (1) Developer's own due diligence (2) Is Dev env setup to mimic production on a continous basis (a day old snapshot of prod) (3) Are there proper tools/validations to ensure what the model needs is present in production (e.g. new feature ) (4) Canary feature that tests the new model on small % of traffic, and then ramps up traffic if model performance remains stable, and all other production remains stable -- as a model may disrupt (add lot of new fanout queries etc). (5) Automation of straigtforward tasks that lead up to building the model - training data sets, training, model regression testing.

--Platform Adoption
With 4 teams, the adoption is really not a problem (the scale is very much manageable via enaging with each team and address any ambiguity and blockers). The only thing that could block is team's own decision, availability to migrate. Most issues here lie how easy migration can be made, leaving almost nothing to end teams, except what to expect, how to troubleshoot, how to map from old to new world, and who to reach for support and all.



### 1.2 Phased Project Plan
_Given the constraints (30% cost reduction in 6 months, two teams launching next quarter, 3 engineers with 2–3 month onboarding for new hires), how would you stage delivery to balance short-term wins against the longer-term platform vision?_

30% cost reduction needs to be understood before it becomes a goal. This may be hard or soft goal triggering different plans.
Dividing into few meaniful phases is the idea. 
Phase1: Define, design and build the core (remove non core, incremental stuff that can come later). ~1 months- requires some cross functional validation on how platform should interface with ML developers
Phase2: Do necessary exploration(benchmarking) of model serving runtimes, online / offline databses/stores latency at some RPS at some mixture of data requests that are representative of prod traffic, explore model architecture that make sense so that key tech choices and optimizations are locked in.
Phase3: Pick 1 important use case (model and associated data) from each team and stress test that design. Improve designor or on tech choices where there are gaps. Then 




### 1.3 Team Composition & Resource Plan
_What does the ideal team look like? Define roles, seniority levels, and how many engineers you'd need._

--
--complementary skills, communication is super important (engineer in silos is anti pattern to check) 
--team work/collaboration to solve hard problems, distill learnings, unblock each other, psychologically safe env to have engineers freely express their opinion
--1 principal/staff (L6/L5), 2 senior engineers (L4/L3): basically stronly opinionated engineers who have built productions systems at scale of millions of users (consumers)


### 1.4 Stakeholder Identification
_Roles and responsibilities — e.g., ML team leads for Recommendations/Pricing/Fraud/Search, Platform Engineering, FinOps, SRE._

--All ML Eng Leads. 

### 1.5 Communication and Rollout Plan
_How you'd keep stakeholders informed, onboard teams incrementally, and handle go/no-go decisions for each migration._

-Weekly updates
-Roll out is incremental, simple use case teams first, more heavy/complex/business-critical use case later. The idea is to learn from failures on non critical cases, and have good enough bake time for robustness.
-Team also need to do some work and prepare to migrate to new platform. The teams are provided with migration guidance and tools to self serve migration for team specific data (what models to migrate with what config). Anything general is absorbed by platform (all feature data for example)

---

## 2. Technical System Design

_Provide an architectural overview of the unified serving platform. Address the following:_

--the core: 
(a) Retrieval (bulk/cheap retrival)
run query against a source (db, vector db, ) to get top N candidates of large number if candidates. Like 1k out of 100k.

(b) Ranking (rank 1k using an expensive ranking model, return top 100)
extract neessary feature data per ranking entity, run inferencing on model X version Vn, return the results (ranked entities). model X is trained offline to rank entities with some objective function that maximizes some metric (click, purchase, watch)

(c) other inferencing use cases (classification / prediction etc)

--the unified serving platform thus: takes an incoming request and routes it to right place.
--an orchestration layer can be offered by platform that supports invoking multiple retrievals legs, merging logic, and then sequence of ranking, re-ranking. this can standarsized as DAG.

few options:
the platform provides a mechanism to deploy each model as service (auto scales to its own traffic) - preferred for large scale deployments and mutual isolation. No multi-tenancy.
the platform offers hybrid -- large traffic models have their own service, less traffic models (long tail) are packaged in single service.
--open source platforms like kserv can be explored as well here.

The model deployment subsystem is another core building block:

The models once finalized by ML devs gets committed to online model registry (model name, version, and associated manifest with files) which then trigger k8 replacement of model vn to vn+1 or produces a deployment of a new model altogether.

Garbage collections: Models that do not receive traffic get auto scaled down and eventually reduced to single pods and flagged for removal.

The cost attribution is around 3 things:

1. Model Inferencing cost: Instance cost of model regardless of utlization X Av. num of instances/day X 30 days.
2. Model Data cost: Fraction cost of data sources provisioned across models by traffic model sends to data sources, Precompute done to land data in those data sources (e.g features, or embeddings) for the model.
3. Training time X instances used for model training.



### 2.1 Core Components
_Describe the Model Registry, Serving Gateway, Autoscaler, Cost Attribution Engine, and Monitoring/Alerting layer._

Model Registry: Offline - MLFlow, more aligned with model development
Model Registry: Online -- Custome, more aligned with what is actually deployed in production.

Serving Gateway: Route to right model, given request paramters.

Autoscaler: Use K8 built in configs to manager it -- trigger based on load. Can be more sophisticated. Right instance type must be selected (how much memory model needs? -- two things (a) Smart feature cache (b) model's own instance footprint)


### 2.2 Routing & Scheduling
_How does the platform decide which GPU instance handles a given inference request? How do you balance latency SLAs against cost efficiency, and how does request batching work?_
The runtime like Triton takes care of -- which instances, and batching.
Basially batching helps with more GPU utilization, but pushing latency a bit. 
Batching simply means the inferencing of multiple different requests happen at the same time (paying the same GPU cost), so efficiency is derived by keeping GPU more busy.
At leverl of hardware, GPUs are built for parallel matrix multiply -- leveragable by batching.


### 2.3 Multi-Model Serving
_How do you support different model frameworks (PyTorch, TensorFlow, ONNX) and inference patterns (real-time, near-real-time, batch) on a shared platform without creating a lowest-common-denominator experience?_

Support different runtimes, mode development frameworks for those runtimes. But it is better to standardized on Pytorch (larger community for support)

### 2.4 Safe Deployments
_How would you design canary deployments and automated rollback for ML models, where "correctness" is statistical rather than binary?_

Canary deployments are non trivial for models
The effect from model (Generated queries, inferencing cost) is not noticeable at smaller percentage of traffic. Not all representative traffic hits the model.
At smaller traffic the number of instances of model are less, so any instance level failure is magnified.
The solution is to gradually ramp up traffic to model in incrementals of X % to reach full traffic in day. This is much better way to check model is going to survive or not.

---

## 3. Hands-on Prototype & AI Collaboration

_Build a functional prototype of a cost-aware inference routing service using an AI coding assistant._

### 3.1 Input
_A set of inference requests, each with a model ID, priority level, and latency SLA. A pool of (mocked) GPU instances with different cost profiles and current load._



### 3.2 Logic
_The router should assign requests to instances while respecting latency SLAs and optimizing for cost. Include a simple cost report that shows cost-per-model after routing decisions are made._



### 3.3 AI Audit & Prompt History
_Provide a transcript or summary of the prompts used to generate and refine the code._

- How you prompted the AI to handle the routing logic (e.g., SLA-aware assignment, cost trade-offs across instance types).
- How you used AI to generate unit tests or simulations (e.g., comparing routing strategies, handling edge cases like instance unavailability).
- How you iterated on the prompt when the AI produced "hallucinated" code or logic errors.



---

## 4. Execution

### 4.1 Project Tracking
_How would you track the project and delivery against timelines?_



### 4.2 Deployment Considerations
_What do you think about rollout, QA, and potential guardrails?_



### 4.3 Health & Monitoring Metrics
_What health and monitoring metrics should we consider?_



### 4.4 Post-Release Success
_How do you define and measure post-release success?_



---

## 5. Talent Assessment

_3–4 sample LinkedIn profiles of Senior ICs (SDE3, Staff, etc.) you would like to add to your team, with a few bullet points on what you like about each profile (not based on personal experience working with them)._


