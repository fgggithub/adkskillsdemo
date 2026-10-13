# Travel Concierge Multi-Agent Solution (FDEDEMO)

An enterprise multi-agent travel planning platform built on **Google Agent Development Kit (ADK)**, **Gemini 3.5**, **Model Armor**, and **OpenTelemetry**. Demonstrates Zero-Trust inter-agent communication (A2A), Model Context Protocol (MCP), dynamic model escalation, and explicit context caching—engineered to run within a strict **$5.00 project budget** with **zero persistent infrastructure costs**.

For full architecture diagrams, sequence flows, and itemized GCP cost breakdowns, see [ARCHITECTURE.MD](file:///home/student_01_b4ba902f49e6/adkskillsdemo/ARCHITECTURE.MD).

---

## Table of Contents
1. [Core Features](#core-features)
2. [Gemini Enterprise StreamAssist Web Portal](#gemini-enterprise-streamassist-web-portal)
3. [Resource Tagging & Cost Safeguards](#resource-tagging--cost-safeguards)
4. [Least Privilege IAM Practices](#least-privilege-iam-practices)
5. [Local Testing Instructions](#local-testing-instructions)
6. [Evaluation Testing Instructions](#evaluation-testing-instructions)
7. [GCP API Enablement](#gcp-api-enablement)
8. [Cloud Deployment & Estimated Times](#cloud-deployment--estimated-times)
9. [Teardown & Zero Residual Cost Verification](#teardown--zero-residual-cost-verification)

---

## Core Features

- **Multi-Agent Orchestration (A2A)**: Coordinated by `TravelConciergeRootAgent` in [travel_concierge/agents/root_agent.py](file:///home/student_01_b4ba902f49e6/adkskillsdemo/travel_concierge/agents/root_agent.py):
  - **Hotel Specialist Agent**: Reserves accommodations and passes immutable reference task IDs (`task-hotel-...`).
  - **Restaurant Specialist Agent**: Integrates with Zomato MCP Server and executes the `dietary_advisor` ADK Skill to filter and rank dining candidates.
  - **Verification Agent**: Provides streaming Human-in-the-Loop (HITL) task confirmation before payment authorization.
- **Gemini Enterprise StreamAssist Web Portal**:
  - Live interactive Single-Page Application (SPA) front-ending the multi-agent system via Discovery Engine's `streamAssist` API protocol ([travel_concierge/portal/](file:///home/student_01_b4ba902f49e6/adkskillsdemo/travel_concierge/portal/)).
  - Real-time Server-Sent Events (SSE) streaming delivering progressive `answerText`, interactive `plannerSteps` diagnostic reasoning, grounded citation cards, and one-click demo presets.
- **Agent Gateway Policy Enforcement Point (PEP)**: Enforced via `GatewayPolicyMiddleware` in [travel_concierge/security/gateway_policy.py](file:///home/student_01_b4ba902f49e6/adkskillsdemo/travel_concierge/security/gateway_policy.py):
  - Enforces **Model Armor** directly at the Gateway ingress layer, terminating malicious requests with HTTP `403 Forbidden` before agents or LLMs execute.
  - Guards against **Prompt Injection**, **Hate Speech & Harassment**, and **Criminal Fraud / Exploitation**.
- **Multi-Turn Itinerary Refinement**:
  - Full session persistence allowing users to refine hotel or dining choices across multiple turns (`POST /v1/trips/refine`).
  - Preserves trace lineage under a unified context span in Google Cloud Trace.
- **Dynamic Model Escalation Engine**:
  - Automatically assesses prompt complexity, compound dietary overlaps (e.g. Vegan + Kosher), severe cross-contact allergen risks, and multi-turn state mutations.
  - Escalates from baseline `gemini-3.5-flash` to `gemini-3.5`, recording escalation reasons on OpenTelemetry spans.
- **Explicit Context Caching & Telemetry**:
  - Pre-caches shared system instructions and schemas in Vertex AI Explicit Context Cache, yielding a **75% token discount**.
  - Emits verbose context management logs documenting prefix preservation and semantic compaction techniques.

---

## Gemini Enterprise StreamAssist Web Portal

The **StreamAssist Web Portal** ([travel_concierge/portal/](file:///home/student_01_b4ba902f49e6/adkskillsdemo/travel_concierge/portal/)) provides a Google Cloud / Gemini Enterprise styled web interface demonstrating live interaction with the multi-agent travel concierge via the official **Google Cloud Discovery Engine `streamAssist` API** specification.

### Key Capabilities:
1. **Server-Sent Events (SSE) Streaming**: Progressive rendering of answer tokens matching the Google Cloud `StreamAssistResponse` schema (`google.cloud.discoveryengine_v1.AssistantServiceClient.stream_assist`).
2. **Diagnostic Planner Steps Drawer**: Real-time visualization of agent internal reasoning (`queryStep`, `planStepId`, model escalation rationale, subagent delegations, and Vertex AI context caching statistics).
3. **Model Armor Live Defense**: Demonstrates instant detection and blocking of prompt injections, jailbreaks, and hate speech directly in the streaming event stream.
4. **Human-in-the-Loop (HITL) Interactivity**: Interactive approval buttons for payment authorization (`$420.00 charge`) and one-click dietary refinement presets.
5. **Dual-Backend Support**:
   - `concierge` (default): Bridges StreamAssist protocol directly to the Travel Concierge A2A orchestrator.
   - `discovery_engine`: Connects to Google Cloud Discovery Engine Assistants (`discoveryengine.googleapis.com`).

### How to Run Locally:
```bash
# Start the unified FastAPI server
uvicorn travel_concierge.server:app --host 0.0.0.0 --port 8080
```
Open your browser to:
- **Interactive Web Portal**: `http://localhost:8080/portal`
- **Agent Discovery Card**: `http://localhost:8080/.well-known/agent-card.json`
- **StreamAssist Configuration**: `http://localhost:8080/portal/config`

### StreamAssist API Testing:
Run the comprehensive 8-scenario portal test suite:
```bash
pytest tests/test_stream_assist_portal.py -v
```

---

## Resource Tagging & Cost Safeguards

### Mandatory Tagging
All resources deployed in Google Cloud are labeled and tagged with **`FDEDEMO`** for unified identification, cost auditing, and lifecycle management:
```hcl
labels = {
  tag         = "fdedemo"
  project     = "fdedemo"
  environment = "fdedemo"
}
```

### Strict $5.00 Budget Cap
- Persistent networking services (such as Cloud NAT at ~$32.40/mo, Serverless VPC Access Connectors at ~$18.00/mo, and Application Load Balancers at ~$18.00/mo) are **explicitly excluded**.
- Cloud Run services scale to **zero instances** (`min_instance_count = 0`), ensuring idle time incurs $0.00.
- Real-time spend is tracked against the $5.00 limit via `travel_concierge/telemetry/budget_tracker.py`.

---

## Least Privilege IAM Practices

Access control adheres strictly to least-privilege principles. No administrative (`roles/owner`, `roles/editor`) or broad viewer roles are granted.

| Identity / Service Account | Role Assigned | Purpose / Scope |
| :--- | :--- | :--- |
| `travel-concierge-sa@<PROJECT_ID>.iam.gserviceaccount.com` | `roles/aiplatform.user` | Inference calls to Vertex AI Gemini 3.5 models and context caching. |
| `travel-concierge-sa@<PROJECT_ID>.iam.gserviceaccount.com` | `roles/cloudtrace.agent` | Exporting W3C trace spans to Google Cloud Trace. |
| `travel-concierge-sa@<PROJECT_ID>.iam.gserviceaccount.com` | `roles/secretmanager.secretAccessor` | Reading API credentials for external integrations. |
| `allUsers` (or Gateway Service Account) | `roles/run.invoker` | Invoking the Cloud Run ingress endpoint. |

---

## Local Testing Instructions

Ensure Python 3.12+ and dependencies are installed:
```bash
pip install -r requirements.txt
```

### 1. Run Complete Pytest Suite
Runs all 62 unit, security, telemetry, circuit breaker, and integration tests:
```bash
pytest -v
```

### 2. Run Model Armor Security Tests
Verifies prompt injection, hate speech, and criminal activity blocking:
```bash
pytest tests/test_security.py -v
```

### 3. Run Gateway Policy Middleware Tests
Verifies that Model Armor is enforced at the Gateway Policy layer:
```bash
pytest tests/test_integration.py -v
```

### 4. Run Multi-Turn & Model Escalation Tests
```bash
pytest tests/test_agents.py -k "test_multi_turn_itinerary_refinement or test_model_escalation_evaluation" -v
```

---

## Evaluation Testing Instructions

The evaluation suite validates the solution against 9 comprehensive benchmark test cases including intent routing, reference task propagation, cache efficiency, security policy enforcement, Model Armor detection, and multi-turn refinement:

```bash
python3 eval/run_eval.py
```

Expected result:
```
======================================================================
BENCHMARK SUMMARY: 23/23 Metrics Passed (100.0%)
======================================================================
```

To run the ADK Agent Evaluation package:
```bash
pytest adk_eval/tests/ -v
```

---

## GCP API Enablement

Before deployment, enable the required Google Cloud APIs using the automated script:
```bash
bash scripts/enable_apis.sh
```

This script enables:
- `run.googleapis.com` (Cloud Run Serverless Compute)
- `aiplatform.googleapis.com` (Vertex AI & Gemini 3.5 API)
- `cloudtrace.googleapis.com` (Google Cloud Trace)
- `artifactregistry.googleapis.com` (Container Image Repository)
- `secretmanager.googleapis.com` (API Secret Storage)
- `iam.googleapis.com` (Identity & Access Management)
- `cloudbuild.googleapis.com` (Automated Image Builds)

---

## Cloud Deployment & Estimated Times

The automated deployment script handles end-to-end infrastructure setup, skills registration, container building, and Cloud Run deployment.

```bash
bash scripts/deploy.sh
```

### Estimated Deployment Times
| Phase | Action | Estimated Duration |
| :--- | :--- | :--- |
| **Phase 1** | API Enablement (`scripts/enable_apis.sh`) | ~15 – 20 seconds |
| **Phase 2** | ADK Skills Registration (`scripts/register_skills.py`) | ~3 – 5 seconds |
| **Phase 3** | Terraform Core Provisioning (Artifact Registry, IAM, Secrets) | ~15 – 20 seconds |
| **Phase 4** | Container Build & Push to Artifact Registry | ~45 – 60 seconds |
| **Phase 5** | Cloud Run Service Deployment (`google_cloud_run_v2_service`) | ~30 – 40 seconds |
| **Phase 6** | Service Health Check & Budget Audit | ~5 – 10 seconds |
| **Total** | **Full End-to-End Automated Deployment** | **~2m 00s – 2m 35s** |

---

## Teardown & Zero Residual Cost Verification

To destroy all cloud resources and verify zero residual costs:
```bash
bash scripts/teardown.sh
```

### What Teardown Performs:
1. Executes `terraform destroy` to tear down Cloud Run services, IAM bindings, secrets, and repositories.
2. Cleans up any retained Artifact Registry repository images.
3. Automatically runs `scripts/cost_report.py --verify-teardown` to audit Cloud NATs, static IPs, load balancers, and persistent disks.
4. Confirms `STATUS: PASS — Zero residual costs confirmed. Environment is clean.`

### Estimated Teardown Time
- **Total Teardown Duration**: **~45 – 60 seconds**.

---

## Cost Tracking & Budget Auditing

At any time, inspect cumulative token spend against the $5.00 limit:
```bash
python3 scripts/cost_report.py
```
To run a strict teardown audit:
```bash
python3 scripts/cost_report.py --verify-teardown
```