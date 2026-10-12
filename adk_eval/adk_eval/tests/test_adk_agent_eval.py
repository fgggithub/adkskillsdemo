"""
Pytest integration tests for ADK Agent Evaluation Suite.
Tests EvalSet schemas, criteria thresholds, custom metrics, autorater reliability, and full benchmark runner.
"""
import pytest
from pathlib import Path
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.eval_config import EvalConfig
from adk_eval.metrics.custom_metrics import (
    evaluate_intent_routing,
    evaluate_task_propagation,
    evaluate_guardrail_compliance,
    evaluate_cache_efficiency,
    evaluate_security_enforcement,
    evaluate_dietary_adherence,
)
from adk_eval.metrics.autorater_reliability import (
    calculate_krippendorff_alpha,
    calculate_gwets_ac1,
    calculate_gwets_ac2,
    evaluate_autorater_reliability,
)
from adk_eval.runners.run_adk_eval import ADKEvaluationRunner


def test_eval_set_schema_loading():
    dataset_path = Path("adk_eval/datasets/travel_concierge.evalset.json")
    assert dataset_path.exists(), "travel_concierge.evalset.json must exist"

    with open(dataset_path, "r", encoding="utf-8") as f:
        eval_set = EvalSet.model_validate_json(f.read())

    assert eval_set.eval_set_id == "travel_concierge_benchmarks"
    assert len(eval_set.eval_cases) >= 5
    for case in eval_set.eval_cases:
        assert case.eval_id.startswith("eval_")
        assert len(case.conversation) >= 1
        inv = case.conversation[0]
        assert inv.user_content is not None
        assert inv.final_response is not None


def test_eval_config_schema_loading():
    config_path = Path("adk_eval/configs/eval_config.json")
    assert config_path.exists(), "eval_config.json must exist"

    with open(config_path, "r", encoding="utf-8") as f:
        eval_config = EvalConfig.model_validate_json(f.read())

    assert "tool_trajectory_avg_score" in eval_config.criteria
    assert "custom_intent_routing" in eval_config.criteria
    assert eval_config.custom_metrics is not None
    assert "custom_intent_routing" in eval_config.custom_metrics


def test_custom_metric_intent_routing():
    res_correct = evaluate_intent_routing({
        "expected_target_agent": "hotel_booking_specialist",
        "routed_agent": "hotel_booking_specialist",
        "tool_uses": [{"name": "search_and_hold_hotel"}],
    })
    assert res_correct["score"] == 1.0

    res_wrong = evaluate_intent_routing({
        "expected_target_agent": "hotel_booking_specialist",
        "routed_agent": "weather_specialist",
        "tool_uses": [{"name": "get_weather"}],
    })
    assert res_wrong["score"] == 0.0


def test_custom_metric_task_propagation():
    res_prop = evaluate_task_propagation({
        "expected_task_id": "task-hotel-shinjuku-99",
        "received_task_ids": ["task-hotel-shinjuku-99"],
        "response": "Hotel task-hotel-shinjuku-99 held",
    })
    assert res_prop["score"] == 1.0

    res_missing = evaluate_task_propagation({
        "expected_task_id": "task-hotel-shinjuku-99",
        "received_task_ids": [],
        "response": "No hotel task ID",
    })
    assert res_missing["score"] == 0.0


def test_custom_metric_cache_efficiency():
    res_high = evaluate_cache_efficiency({
        "telemetry": {"cache_hit_rate": 0.80, "cached_tokens": 8000, "prompt_tokens": 10000},
        "target_cache_hit_rate": 0.50,
    })
    assert res_high["score"] == 1.0

    res_low = evaluate_cache_efficiency({
        "telemetry": {"cache_hit_rate": 0.20, "cached_tokens": 200, "prompt_tokens": 1000},
        "target_cache_hit_rate": 0.50,
    })
    assert res_low["score"] == 0.40


def test_custom_metric_security_enforcement():
    res_denied = evaluate_security_enforcement({
        "token_claims": {"sub": "user:guest@example.com", "groups": ["GUEST"]},
        "status_code": 403,
        "is_error": True,
        "expected_status": 403,
    })
    assert res_denied["score"] == 1.0

    res_breach = evaluate_security_enforcement({
        "token_claims": {"sub": "user:guest@example.com", "groups": ["GUEST"]},
        "status_code": 200,
        "is_error": False,
        "expected_status": 403,
    })
    assert res_breach["score"] == 0.0


def test_custom_metric_dietary_adherence():
    res_compliant = evaluate_dietary_adherence({
        "dietary_preference": "vegan",
        "response": "Ain Soph Tokyo 100% plant-based vegan noodles",
    })
    assert res_compliant["score"] == 1.0

    res_violation = evaluate_dietary_adherence({
        "dietary_preference": "vegan",
        "response": "Tokyo Wagyu House premium beef steak",
    })
    assert res_violation["score"] == 0.0


def test_autorater_reliability_metrics():
    # Perfect agreement
    ratings_perfect = [[5.0, 5.0], [4.0, 4.0], [5.0, 5.0], [3.0, 3.0]]
    alpha_perfect = calculate_krippendorff_alpha(ratings_perfect, level_of_measurement="ordinal")
    assert alpha_perfect >= 0.99

    ac2_perfect = calculate_gwets_ac2(ratings_perfect)
    assert ac2_perfect >= 0.99

    # Partial agreement
    gold = [5.0, 4.0, 5.0, 3.0, 2.0]
    autorater = [5.0, 4.0, 4.0, 3.0, 2.0]
    rel = evaluate_autorater_reliability(gold, autorater, metric_type="ordinal")
    assert rel["krippendorff_alpha"] > 0.80
    assert rel["gwets_ac"] > 0.80
    assert rel["raw_agreement"] == 0.80


def test_adk_runner_full_benchmark(tmp_path):
    runner = ADKEvaluationRunner(
        dataset_path="adk_eval/datasets/travel_concierge.evalset.json",
        config_path="adk_eval/configs/eval_config.json",
        output_dir=str(tmp_path),
    )

    summary = runner.run_benchmark(num_runs=1)
    assert summary["overall_status"] == "PASSED"
    assert summary["pass_rate"] == 1.0
    assert summary["total_cases"] == len(runner.eval_set.eval_cases)
    assert (tmp_path / "latest_eval_report.json").exists()
    assert (tmp_path / "latest_eval_report.md").exists()
