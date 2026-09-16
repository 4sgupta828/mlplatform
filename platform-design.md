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


### 1.2 Phased Project Plan
_Given the constraints (30% cost reduction in 6 months, two teams launching next quarter, 3 engineers with 2–3 month onboarding for new hires), how would you stage delivery to balance short-term wins against the longer-term platform vision?_



### 1.3 Team Composition & Resource Plan
_What does the ideal team look like? Define roles, seniority levels, and how many engineers you'd need._



### 1.4 Stakeholder Identification
_Roles and responsibilities — e.g., ML team leads for Recommendations/Pricing/Fraud/Search, Platform Engineering, FinOps, SRE._



### 1.5 Communication and Rollout Plan
_How you'd keep stakeholders informed, onboard teams incrementally, and handle go/no-go decisions for each migration._



---

## 2. Technical System Design

_Provide an architectural overview of the unified serving platform. Address the following:_

### 2.1 Core Components
_Describe the Model Registry, Serving Gateway, Autoscaler, Cost Attribution Engine, and Monitoring/Alerting layer._



### 2.2 Routing & Scheduling
_How does the platform decide which GPU instance handles a given inference request? How do you balance latency SLAs against cost efficiency, and how does request batching work?_



### 2.3 Multi-Model Serving
_How do you support different model frameworks (PyTorch, TensorFlow, ONNX) and inference patterns (real-time, near-real-time, batch) on a shared platform without creating a lowest-common-denominator experience?_



### 2.4 Safe Deployments
_How would you design canary deployments and automated rollback for ML models, where "correctness" is statistical rather than binary?_



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


