# ADK Evaluation Suite: Travel Concierge Multi-Agent System

This directory contains the official **Google ADK (Agent Development Kit)** evaluation suite for the `travel_concierge` multi-agent architecture. It implements native ADK evaluation datasets (`.evalset.json`), declarative evaluation configuration (`eval_config.json` / `eval_config.yaml`), custom deterministic and policy metrics, statistical autorater agreement analysis (**Krippendorff's Alpha** & **Gwet's AC1/AC2**), and programmatic/cloud test runners.

---

## Directory Structure

```
adk_eval/
├── README.md                              # This documentation
├── configs/
│   ├── eval_config.json                  # Canonical ADK criteria thresholds and custom metrics definition
│   ├── eval_config.yaml                  # YAML version for CLI and pipeline tooling
│   └── test_config.json                  # Auto-discovery configuration for AgentEvaluator
├── datasets/
│   ├── test_config.json                  # Dataset-adjacent config for ADK discovery
│   ├── travel_concierge.evalset.json     # Comprehensive benchmark covering all multi-agent scenarios
│   ├── routing.evalset.json              # Focused intent classification & sub-agent delegation
│   ├── dietary_compliance.evalset.json   # Dietary advisor skill & allergen filtering
│   ├── security_enforcement.evalset.json # IAM group & OAuth scope 403 Forbidden enforcement
│   └── cache_efficiency.evalset.json    # Context cache hit rate & token pricing evaluation
├── metrics/
│   ├── __init__.py
│   ├── custom_metrics.py                 # Custom policy and trajectory evaluators
│   └── autorater_reliability.py          # Krippendorff's Alpha & Gwet's AC1/AC2 agreement metrics
├── runners/
│   ├── __init__.py
│   ├── run_adk_eval.py                   # Programmatic & CLI evaluation runner
│   └── cloud_eval_job.py                 # Cloud Run Job / Vertex AI Reasoning Engine runner
├── tests/
│   ├── __init__.py
│   └── test_adk_agent_eval.py            # Pytest test suite for automated CI/CD gating
└── reports/
    ├── latest_eval_report.json           # Latest JSON evaluation run summary
    └── latest_eval_report.md             # GitHub-flavored markdown report
```

---

## Evaluation Datasets (`.evalset.json`)

All datasets conform to the ADK `EvalSet` schema (`google.adk.evaluation.eval_set.EvalSet`):

| Eval ID | Description | Tested Capabilities | Target Criteria |
| :--- | :--- | :--- | :--- |
| `eval_001_intent_routing` | Hotel booking near Tokyo Shinjuku | Sub-agent routing, `search_and_hold_hotel` tool call | `custom_intent_routing` >= 1.0, `tool_trajectory_avg_score` >= 1.0 |
| `eval_002_task_propagation` | Contextual dining near held hotel | Hotel Task ID (`task-hotel-shinjuku-99`) propagation | `custom_task_propagation` >= 1.0, `tool_trajectory_avg_score` >= 1.0 |
| `eval_003_dietary_guardrail` | Strict 100% plant-based vegan dining | Skill Registry `evaluate_dietary_compliance` skill | `custom_dietary_adherence` >= 1.0, `safety_v1` >= 1.0 |
| `eval_004_security_authorization` | Unauthorized MCP invocation (no `MCPUSERS`) | Zero Trust auth guardrails, 403 Forbidden handling | `custom_security_enforcement` >= 1.0, `safety_v1` >= 1.0 |
| `eval_005_cache_efficiency` | Multi-day trip planning with shared context | Gemini Context Caching, prompt token cost discount | `custom_cache_efficiency` >= 0.50 (target >= 50% hit rate) |
| `eval_006_human_in_the_loop_verification` | Booking confirmation with human approval | HITL approval state transition, payment verification | `custom_task_propagation` >= 1.0, `safety_v1` >= 1.0 |

---

## Evaluation Metrics & Criteria

### 1. Prebuilt ADK Metrics
- **`tool_trajectory_avg_score`** (Threshold: `1.0`, MatchType: `IN_ORDER`): Verifies required tool calls were invoked in the correct order.
- **`response_match_score`** (Threshold: `0.80`): Text similarity and semantic match to reference response.
- **`rubric_based_final_response_quality_v1`** (Threshold: `0.80`): LLM judge scoring against custom scenario rubrics.
- **`safety_v1`** (Threshold: `1.0`): Ensures no unsafe outputs or security violations occurred.

### 2. Custom Domain Metrics
- **`custom_intent_routing`**: Validates root orchestrator delegation to correct specialist (`hotel_booking_specialist`, `restaurant_booking_specialist`).
- **`custom_task_propagation`**: Ensures task correlation IDs persist across sub-agents and webhook callbacks.
- **`custom_cache_efficiency`**: Measures token cache hit rate (target >= 50%).
- **`custom_security_enforcement`**: Verifies IAM group and OAuth scope authorization, returning 403 Forbidden on violations.
- **`custom_dietary_adherence`**: Filters out prohibited ingredients (meat, dairy, seafood for vegan queries).

---

## Inter-Rater Reliability (Autorater Agreement)

To ensure that LLM-as-a-judge autoraters remain accurate and unbiased compared to human baselines, the evaluation suite computes statistical agreement metrics:

### 1. Krippendorff's Alpha ($\alpha$)
- Generalized agreement coefficient handling multiple raters, missing ratings, and ordinal scales:
  $$\alpha = 1 - \frac{D_o}{D_e}$$
- **Interpretation:** $\alpha \ge 0.800$ indicates good reliability; $\alpha \ge 0.667$ indicates acceptable/tentative agreement.

### 2. Gwet's AC1 / AC2
- Chance-corrected agreement coefficient resistant to the "high prevalence paradox" common in high-performing agent evaluation sets:
  $$AC_1 = \frac{p_a - p_e}{1 - p_e}$$
- **AC2** incorporates quadratic distance weighting for 1–5 ordinal rubric scales.

---

## How to Run Evaluations

### 1. Run via Pytest (CI/CD Gating)
```bash
USE_MOCK_CACHE=true pytest adk_eval/tests/test_adk_agent_eval.py -v
```

### 2. Run via the Programmatic / CLI Benchmark Runner
```bash
python3 adk_eval/runners/run_adk_eval.py \
  --dataset adk_eval/datasets/travel_concierge.evalset.json \
  --config adk_eval/configs/eval_config.json \
  --output-dir adk_eval/reports
```

### 3. Run via Native Google ADK CLI
```bash
adk eval travel_concierge adk_eval/datasets/travel_concierge.evalset.json \
  --config_file_path adk_eval/configs/eval_config.json \
  --print_detailed_results
```

### 4. Run Cloud Evaluation Job in Vertex AI / Agent Runtime
```bash
EVAL_DATASET_PATH=adk_eval/datasets/travel_concierge.evalset.json \
EVAL_STORAGE_URI=gs://<EVAL_BUCKET_NAME>/eval-runs/$(date +%s) \
python3 adk_eval/runners/cloud_eval_job.py
```
