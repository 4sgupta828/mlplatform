# Case Study for Sr. EM ML Infrastructure

## Building a Unified Model Serving & Cost Optimization Platform

## Scenario

Quince relies on a growing portfolio of ML models across the business — product recommendations, dynamic pricing, fraud detection, search ranking, and personalization. Each of these models was developed and deployed independently by separate teams, resulting in a fragmented infrastructure landscape with no shared serving layer.

This fragmentation is creating serious pain points: inference costs are growing faster than revenue, with duplicated GPU provisioning across teams. Latency SLAs are inconsistent — some models respond in 20ms, others in 500ms+ with no clear accountability. There is no centralized visibility into cost-per-prediction, model health, or capacity utilization. When traffic spikes occur (e.g., flash sales), teams scramble to manually scale their own endpoints, often over-provisioning to avoid downtime.

As a Sr. Engineering Manager for ML Infrastructure, you are responsible for owning the end-to-end delivery of a **Unified Model Serving Platform** — from defining the vision and success metrics, to building the project plan, leading the technical design, and coordinating across multiple ML and platform teams to ship infrastructure that is cost-efficient, performant, and operationally mature.

## Constraints

You are operating under the following real-world constraints, which may conflict with each other:

- **Cost pressure:** Leadership has set a target of 30% inference cost reduction within 6 months.
- **Urgent team needs:** Two ML teams (Search Ranking and a new Personalization model) are launching new models next quarter and need a serving solution now. Without one, they will spin up their own infrastructure — making the fragmentation problem worse.
- **Team capacity:** You are starting with a small team (3 engineers) and can make a case for additional headcount, but new hires would take 2–3 months to onboard.

## The Goal

Build a unified model serving platform that achieves the following:

- **Standardized Model Deployment:** Provide a single, self-service path for ML teams to deploy models to production with consistent packaging, versioning, and rollback capabilities.
- **Cost Transparency & Optimization:** Deliver real-time visibility into costs at the model and team level — covering both inference and training workloads. Include automated recommendations for right-sizing and instance selection (GPU vs. CPU, spot vs. on-demand), and surface risks from stale provisioned fleets that carry ongoing cost without active use.
- **Operational Maturity:** Implement health monitoring, alerting, and canary deployment capabilities so model owners have confidence in production stability.
- **Multi-Team Adoption:** Design the platform to serve as shared infrastructure across 4+ ML teams with different model types (real-time, near-real-time, batch) without forcing a one-size-fits-all approach.

## Expectation

### Project Planning

- **Impact Plan** (success metrics for the project — e.g., inference cost reduction %, P99 latency improvement, time-to-deploy for new models, platform adoption rate across teams)
- **Phased Project Plan** (given the constraints above, how would you stage delivery to balance short-term wins against the longer-term platform vision?)
- **Team Composition & Resource Plan** (what does the ideal team look like? Define roles, seniority levels, and how many engineers you'd need)
- **Stakeholder Identification** (roles and responsibilities — e.g., ML team leads for Recommendations/Pricing/Fraud/Search, Platform Engineering, FinOps, SRE)
- **Communication and Rollout Plan** (how you'd keep stakeholders informed, onboard teams incrementally, and handle go/no-go decisions for each migration)

### Technical System Design

Provide an architectural overview of the unified serving platform. Your design should address:

- **Core Components:** Describe the Model Registry, Serving Gateway, Autoscaler, Cost Attribution Engine, and Monitoring/Alerting layer.
- **Routing & Scheduling:** How does the platform decide which GPU instance handles a given inference request? How do you balance latency SLAs against cost efficiency, and how does request batching work?
- **Multi-Model Serving:** How do you support different model frameworks (PyTorch, TensorFlow, ONNX) and inference patterns (real-time, near-real-time, batch) on a shared platform without creating a lowest-common-denominator experience?
- **Safe Deployments:** How would you design canary deployments and automated rollback for ML models, where "correctness" is statistical rather than binary?

### Hands-on Prototype & AI Collaboration

Using an AI coding assistant (e.g., Cursor, Claude, etc.), build a functional prototype of a cost-aware inference routing service.

- **Input:** A set of inference requests, each with a model ID, priority level, and latency SLA. A pool of (mocked) GPU instances with different cost profiles and current load.
- **Logic:** The router should assign requests to instances while respecting latency SLAs and optimizing for cost. Include a simple cost report that shows cost-per-model after routing decisions are made.
- **AI Audit & Prompt History:** Please provide a transcript or summary of the prompts you used to generate and refine this code. As an "AI-forward" leader, we are looking for:
  - How you prompted the AI to handle the routing logic (e.g., SLA-aware assignment, cost trade-offs across instance types).
  - How you used AI to generate unit tests or simulations (e.g., comparing routing strategies, handling edge cases like instance unavailability).
  - How you iterated on the prompt when the AI produced "hallucinated" code or logic errors.

### Execution

- How would you track the project and delivery against timelines
- What are the considerations for Deployment
  - What do you think about rollout, QA, and potential guardrails?
  - What health and monitoring metrics should we consider?
- Post-Release Success

### Talent Assessment

3–4 sample LinkedIn profiles of Senior ICs (SDE3, Staff, etc.) you would like to add to your team with a few bullet points on the things you like about those profiles (not based on your personal experience working with them).
