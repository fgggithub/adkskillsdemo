# Travel Concierge Multi-Agent System — Architecture Document

## 1. System Overview

The **Travel Concierge Multi-Agent System** is an enterprise-grade agentic application built on the **Google Agent Development Kit (ADK)** and Python, exposing **Agent-to-Agent (A2A)** standard interfaces. It coordinates specialized, decoupled subagents to deliver multi-turn travel itinerary planning, dietary compliance validation, hotel reservations, restaurant discovery via MCP (Model Context Protocol), and human-in-the-loop (HITL) payment verification.

All components adhere to the **Agent eXperience Interface (AXI)** methodology, **Zero-Trust networking**, **least-privilege IAM**, dynamic **Model Armor** defense, and automated **GCP Agent Runtime Skills Registry** integration.

### Core Architecture Principle: Zero-Trust Gateway PEP Interception
In compliance with enterprise Zero-Trust principles, **all communication from the Root Orchestrator Agent to Subagents must pass through the Agent Gateway Policy Enforcement Point (PEP)**. No direct or unverified subagent invocation is permitted. The Gateway strictly validates:
1. **Caller Identity** via `Proxy-Authorization: Bearer <caller_spiffe_gateway_token>`
2. **Target Audience Binding** via `Authorization: Bearer <target_subagent_token>` (preventing token reuse/confused deputy attacks)
3. **Payload Sanitization** via **Model Armor** (inspecting all prompts/payloads for prompt injection, hate speech, and criminal activity)

```mermaid
graph TD
    User([User / Browser]) -->|HTTP / HTML| PortalUI[Gemini Enterprise StreamAssist Web Portal<br/>Single-Page Application]
    PortalUI -->|SSE streamAssist API| StreamService[StreamAssist Service Bridge<br/>Discovery Engine Protocol]
    StreamService -->|Inspect Payload| RootAgent[Root Orchestrator Agent<br/>travel-concierge-orchestrator<br/>Cloud Run / Agent Runtime]
    
    subgraph ZeroTrustGateway ["Agent Gateway Policy Enforcement Point (PEP)"]
        GatewayServer[Agent Gateway Service<br/>agent-gateway-pep<br/>Cloud Run]
        ModelArmor[Model Armor Filter<br/>Prompt Injection / Abuse / Crime]
        AudienceVerifier[Zero-Trust Audience & SPIFFE Verifier]
        GatewayServer --- ModelArmor
        GatewayServer --- AudienceVerifier
    end

    subgraph Subagents ["Decoupled Cloud Run Subagents (Scale-to-Zero, FDEDEMO)"]
        HotelAgent[Hotel Booking Specialist<br/>hotel-booking-specialist<br/>Port 8080]
        RestaurantAgent[Restaurant Specialist<br/>restaurant-booking-specialist<br/>Port 8080]
        VerificationAgent[Final Verification Agent<br/>final-verification-agent<br/>HITL Task Streaming]
    end

    subgraph SkillsRegistry ["GCP Agent Runtime Skills Registry"]
        DietarySkill[dietary_advisor<br/>Filter First, Rank Second]
        CompareRatings[scripts/compare_ratings.py<br/>NYC / UK / Tokyo Normalization]
    end

    subgraph ExternalServices ["External Tools & Services"]
        ZomatoMCP[Zomato MCP Server]
        HotelService[Partner Hotel Engine]
        PaymentGateway[Payment Authorization]
    end

    subgraph Observability ["Telemetry & Budgeting"]
        CloudTrace[Google Cloud Trace]
        BudgetTracker[Budget & Cost Tracker<br/>$5.00 Hard Budget Cap]
        ContextCache[Vertex AI Context Cache<br/>75% Token Discount]
    end

    RootAgent --> ContextCache
    RootAgent --> BudgetTracker
    RootAgent --> CloudTrace

    %% Zero-Trust Gateway Interception
    RootAgent -->|1. Proxy-Auth + Aud-Bound Token| GatewayServer
    GatewayServer -->|2. Validated Live Dispatch| HotelAgent
    GatewayServer -->|2. Validated Live Dispatch| RestaurantAgent
    GatewayServer -->|2. Validated Live Dispatch| VerificationAgent

    HotelAgent --> HotelService
    RestaurantAgent --> DietarySkill
    RestaurantAgent --> ZomatoMCP
    VerificationAgent --> PaymentGateway
```

---

## 2. Component Topologies & Interaction Flows

### 2.1 Multi-Agent Orchestration & Zero-Trust A2A Communication
1. **Root Orchestrator Agent (`travel-concierge-orchestrator`)**:
   - Deployed to **Cloud Run / GCP Agent Runtime** (`min_instance_count = 0`).
   - Manages global session state, explicit context caching, token compaction, and multi-turn itinerary refinements.
   - Features **dynamic model escalation** from `gemini-3.5-flash` to `gemini-3.5` when constraint complexity or conflicting regional criteria require deeper reasoning.
   - Routes **all downstream requests through the Agent Gateway PEP** with caller SPIFFE identity (`spiffe://prod.corp/agent/travel-concierge`) and target audience tokens.
2. **Agent Gateway PEP (`agent-gateway-pep`)**:
   - Independent **Cloud Run** service acting as the central Policy Enforcement Point.
   - Validates `Proxy-Authorization` and inspects `Authorization` audience binding before delegating.
   - Applies active **Model Armor** inspection on all outbound request bodies to block prompt injections before they reach subagents.
3. **Hotel Booking Specialist (`hotel-booking-specialist`)**:
   - Independent **Cloud Run** microservice.
   - Enforces audience claim (`hotel-booking-specialist`).
   - Reserves temporary room holds and emits a durable `reference_task_id` (e.g., `task-hotel-shinjuku-99`).
4. **Restaurant Specialist (`restaurant-booking-specialist`)**:
   - Independent **Cloud Run** microservice.
   - Enforces audience claim (`restaurant-booking-specialist`).
   - Integrates with the **Zomato MCP Server** with IAM group membership (`MCPUSERS`) and OAuth 2.0 scope (`restaurants.read`).
   - Uses the `dietary_advisor` skill to filter and rank restaurants.
5. **Final Verification Agent (`final-verification-agent`)**:
   - Independent **Cloud Run** microservice.
   - Enforces audience claim (`final-verification-agent`).
   - Manages asynchronous Human-in-the-Loop (HITL) task streaming with `input-required` state interrupts, confirming charges before final execution.

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Gemini Enterprise
    participant Root as Root Orchestrator (Cloud Run)
    participant GW as Agent Gateway PEP (Cloud Run)
    participant Hotel as Hotel Agent (Cloud Run)
    participant Rest as Restaurant Agent (Cloud Run)
    participant Verif as Verification Agent (Cloud Run)
    participant Trace as Cloud Trace & Cost Tracker

    User->>Root: POST /v1/trips/plan
    Root->>Trace: Start Span "orchestrate_trip_planning"
    Root->>Root: Evaluate Model Escalation (Flash -> Gemini 3.5)
    
    rect rgb(255, 240, 245)
        Note over Root,Hotel: Step 1: Hotel Hold via Zero-Trust Gateway PEP
        Root->>GW: POST /v1/agents/hotel_booking_specialist/messages<br/>(Proxy-Auth: SPIFFE, Auth: aud=hotel-booking-specialist)
        GW->>GW: 1. Validate Caller Identity (Proxy-Auth)<br/>2. Validate Audience Binding (aud)<br/>3. Inspect Payload via Model Armor
        GW->>Hotel: Forward Validated Request
        Hotel-->>GW: Hold Confirmed + task_id: "task-hotel-shinjuku-99"
        GW-->>Root: Gateway Response
    end

    rect rgb(255, 250, 240)
        Note over Root,Rest: Step 2: Dining Discovery via Zero-Trust Gateway PEP
        Root->>GW: POST /v1/agents/restaurant_booking_specialist/messages<br/>(Proxy-Auth: SPIFFE, Auth: aud=restaurant-booking-specialist)
        GW->>GW: 1. Validate Caller Identity & Audience<br/>2. Inspect Payload via Model Armor
        GW->>Rest: Forward Validated Request
        Rest->>Rest: Execute Zomato MCP + dietary_advisor skill
        Rest-->>GW: Ranked Dining Recommendations
        GW-->>Root: Gateway Response
    end

    rect rgb(240, 255, 240)
        Note over Root,Verif: Step 3: HITL Verification via Zero-Trust Gateway PEP
        Root->>GW: POST /v1/agents/final_verification_agent/messages<br/>(Proxy-Auth: SPIFFE, Auth: aud=final-verification-agent)
        GW->>GW: 1. Validate Caller Identity & Audience<br/>2. Inspect Payload via Model Armor
        GW->>Verif: Forward Validated Request
        Verif-->>GW: State: "completed" / "input-required"
        GW-->>Root: Gateway Response
    end

    Root->>Trace: Record Token Usage, Cache Hit Rate, Cost vs $5 Budget
    Root-->>User: Consolidated Trip Plan
```

### 2.2 Discovery Engine StreamAssist API Integration & Web Portal Architecture

The application provides a dedicated **Gemini Enterprise StreamAssist Web Portal** implementing the official Google Cloud Discovery Engine `streamAssist` API protocol (`google.cloud.discoveryengine_v1.AssistantServiceClient.stream_assist`).

```mermaid
sequenceDiagram
    autonumber
    actor Browser as User Browser (Web Portal UI)
    participant Portal as StreamAssist Portal Service
    participant Armor as Model Armor Security Gateway
    participant Root as Root Travel Concierge Agent
    participant Cache as Vertex AI Context Cache

    Browser->>Portal: POST /portal/api/stream (SSE Connection)
    Portal->>Armor: Inspect Ingress Text (Prompt Injection / Hate Speech / Crime)
    alt Content Violation Detected
        Armor-->>Portal: Blocked (Category, Heuristic Match)
        Portal-->>Browser: SSE event: state=FAILED + safetyRatings[blocked=true] + [DONE]
    else Payload Clean
        Portal-->>Browser: SSE event: queryStep (Synthesizing plan)
        Portal->>Root: Dynamic Model Escalation Evaluation
        Portal-->>Browser: SSE event: planStep (Model Escalation: Flash -> Gemini 3.5)
        Portal->>Root: Execute A2A Hotel Hold & MCP Restaurant Search
        Portal-->>Browser: SSE event: planStep (Subagent Delegation: Hotel & Zomato MCP)
        Portal->>Cache: Query Vertex AI Shared Context Cache
        Portal-->>Browser: SSE event: planStep (Context Cache: 75% Discount Verified)
        Portal-->>Browser: SSE event: answerText (Progressive Markdown Chunks)
        Portal-->>Browser: SSE event: state=SUCCEEDED + citations + suggested replies + [DONE]
    end
```

#### StreamAssist Schema Fidelity:
The portal streaming endpoint (`/portal/api/stream`) generates real-time events strictly adhering to the Google Cloud Discovery Engine `StreamAssistResponse` protobuf definition:
- **`queryStep`**: Captures user intention, conversational turn, and backend routing.
- **`planStep`**: Surface agent reasoning, dynamic model escalation triggers, subagent tool calls, and Vertex AI context caching hit rates into the UI drawer.
- **`answer`**: Progressive token streaming with markdown formatting, itinerary timetables, and pricing.
- **`citations`**: Structured metadata cards linking recommended venues, hygiene ratings, and booking confirmations.
- **`safetyRatings`**: Real-time Model Armor scanning verdicts embedded directly into the response payload.

---

## 3. Zero-Trust Security & Policy Enforcement

1. **Model Armor Enforced Through Gateway Policy**:
   - **Centralized Gateway Policy Enforcement Point (PEP)**: Model Armor is enforced directly at the Agent Gateway ingress layer (`GatewayPolicyMiddleware` / Envoy Gateway filter) **before** incoming requests can ever reach root orchestrators, subagents, or LLM backends.
   - **Inspection Categories**: Scans all request bodies, query parameters, and conversational inputs for:
     - **Prompt Injection & Jailbreaks**: Instruction overrides (`ignore previous instructions`), system prompt exfiltration, delimiter attacks.
     - **Hate Speech & Harassment**: Discriminatory slurs, dehumanizing rhetoric, protected class targeted hostility.
     - **Criminal Activity**: Financial fraud, card cloning, bypass of physical hotel locks, passport forgery.
   - **Enforcement Action**: Rejection with HTTP `403 Forbidden`, setting OpenTelemetry attributes (`gateway.policy.blocked = true`, `gateway.policy.violation_category = ...`) and terminating traffic immediately at the edge.
2. **Zero-Trust Identity & Audience Binding**:
   - External callers authenticate via `Proxy-Authorization: Bearer <spiffe_or_oidc_token>`.
   - Downstream agent calls carry audience-bound tokens (`Authorization: Bearer <agent_audience_jwt>`), preventing credential reuse across services.
3. **SSRF Validator**:
   - Validates all webhook callbacks and external URLs against DNS rebinding, loopback interfaces (`127.0.0.1`, `::1`), private RFC1918 subnets, and Cloud metadata servers (`169.254.169.254`, `metadata.google.internal`).
4. **Circuit Breaker**:
   - Protects against cascading failures from MCP and external partners. Trips to `OPEN` after 3 consecutive failures, enters `HALF-OPEN` after a 15-second recovery window.
5. **Least-Privilege IAM**:
   - Cloud Run service accounts receive only `roles/aiplatform.user`, `roles/cloudtrace.agent`, and `roles/secretmanager.secretAccessor`. No administrative or project-wide viewer roles are granted.

---

## 4. Telemetry, Tracing & Context Management

1. **W3C Distributed Trace Context**:
   - OpenTelemetry `traceparent` headers are injected across all A2A boundaries, linking root agent requests and subagent executions into a single distributed trace visible in Google Cloud Trace.
2. **Prompts & Responses Auditing**:
   - Span attributes record prompts, completions, and model versions for full forensic reproducibility.
3. **Verbose Context Management & Compaction Logging**:
   - Context caching saves 75% on prompt tokens by storing instructions and schemas in Vertex AI Explicit Context Cache.
   - When large tool results or conversational history are processed, agents log the compaction technique (e.g. semantic deduplication, schema pruning, or extractive summarization), reporting token count before and after compaction and the resulting reduction ratio.
4. **Dynamic Model Escalation Tracing**:
   - Agents default to `gemini-3.5-flash`.
   - If constraint count exceeds threshold or multi-region rating normalization exhibits high variance, the agent escalates to `gemini-3.5` (or `gemini-3.5-pro`).
   - The escalation reason, initial model, and escalated model are explicitly recorded as span attributes and logged.

---

## 5. Itemized GCP Cost Breakdown & $5.00 Budget Safeguard

A critical project requirement is that total expenditure must be easily tracked and **strictly kept within a $5.00 USD project budget**, with **zero residual costs remaining** after teardown.

### 5.1 Component Cost Analysis

| Component | GCP Service | Pricing Model | Estimated Unit Cost | Persistent Cost Risk? | Budget Safeguard Strategy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Root Agent** | Vertex AI Agent Runtime | Pay-per-invocation | ~$0.0001 / invocation | **No** (Scale to zero) | Serverless execution; minimal idle charge |
| **Subagents** | Cloud Run (v2) | Pay-per-use (CPU/Mem allocation during request) | Min instances = 0; $0.00002400 / vCPU-s | **No** (Scale to zero) | Set `min_instance_count = 0` so idle cost is **$0.00** |
| **Artifact Registry** | Artifact Registry | Storage (GB/mo) | $0.10 / GB-month (~$0.003 / day for 30MB) | **Negligible** | Deleted during teardown script |
| **LLM Inference** | Vertex AI Gemini 3.5 Flash | Token-based | $0.30/1M input, $0.075/1M cached, $2.50/1M output | **No** | Context caching cuts prompt costs by 75%; average test suite costs < $0.02 |
| **Cloud Trace** | Google Cloud Trace | Spans ingested | Free tier covers first 2.5M spans/mo | **No** | Free tier covers all demo and eval usage |
| **Agent Gateway** | Cloud API Gateway / Envoy | Forwarding rule / Gateway instance | $0.0008 / request or hourly rule | **Low** | Managed serverless gateway |
| **VPC Connector** | Serverless VPC Access | Instance hours per connector | ~$0.025 / hr (~$18.00 / month) | **HIGH RISK** ⚠️ | **Omit persistent VPC connector** for demo: use Cloud Run direct HTTPS with IAM OIDC authentication |
| **Cloud NAT** | Cloud NAT Gateway | Hourly fee + data processing | ~$0.045 / hr (~$32.40 / month) + IP costs | **HIGH RISK** ⚠️ | **Omit Cloud NAT**: all subagents and APIs use standard Google private Google access or public HTTPS |
| **Application Load Balancer** | Global External ALB | Forwarding rule hourly fee | ~$0.025 / hr (~$18.00 / month) | **HIGH RISK** ⚠️ | **Omit dedicated ALB**: use native Cloud Run URLs (`*.run.app`) and Agent Gateway serverless endpoints |

> [!CAUTION]
> **Persistent Networking Cost Trap**:
> Traditional enterprise deployments frequently spin up Cloud NAT gateways ($32.40/mo), Serverless VPC Access connectors ($18.00/mo), and static ALB forwarding rules ($18.00/mo). Leaving these running for even 4 days would consume **$9.00**, instantly busting the **$5.00 project budget**!
>
> **Safeguard Solution**:
> 1. All services are deployed strictly in **Scale-to-Zero Serverless** mode (`min_instances = 0`).
> 2. Zero-Trust security is achieved at the application and IAM layer (OIDC/SPIFFE tokens, Agent Gateway headers, and least-privilege IAM) without requiring costly persistent VPC hardware.
> 3. The automated teardown script (`scripts/teardown.sh`) and budget verification tool (`scripts/cost_report.py`) inspect and verify that **no lingering IPs, forwarding rules, or instances exist**.

### 5.2 Estimated Demo & Evaluation Run Cost

| Stage | Operations | Estimated Cost (USD) |
| :--- | :--- | :--- |
| Initial Setup & APIs | Enable required services | $0.00 |
| Skills Registration | Automated script registration | $0.00 |
| Unit & Integration Tests | 51 Pytest suites (local/mock) | $0.00 |
| Evaluation Benchmark | 5 ADK benchmark scenarios | ~$0.008 |
| Multi-turn Demo | 3 complete itineraries + refinements | ~$0.005 |
| Teardown & Verification | Cost report audit | $0.00 |
| **Total Estimated Spend** | | **~$0.013 of $5.00 budget (0.26%)** |

---

## 6. Resource Tagging & Inventory Control

All cloud resources are provisioned with the mandatory label:
- **`project: fdedemo`**
- **`environment: fdedemo`**
- **`managed_by: terraform`**

This enables instant cost tracking in Google Cloud Billing and Cloud Monitoring by filtering on the label `fdedemo`.
