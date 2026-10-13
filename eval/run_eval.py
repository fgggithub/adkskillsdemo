"""
Evaluation Runner for Travel Concierge Multi-Agent System.
Runs benchmark test cases and generates evaluation scorecards.
"""
import json
import logging
import sys
from typing import Dict, Any, List

from eval.eval_config import EVAL_DATASET, EvalTestCase
from eval.evaluators import EvaluationSuite, MetricScore
from eval.llm_judge import LLMJudge
from travel_concierge.agents.root_agent import TravelConciergeRootAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("travel_concierge.eval.runner")


def run_benchmark() -> Dict[str, Any]:
    logger.info("Initializing Travel Concierge Evaluation Benchmark...")
    root_agent = TravelConciergeRootAgent()
    judge = LLMJudge()

    results: List[Dict[str, Any]] = []
    total_passed = 0
    total_metrics_evaluated = 0

    print("\n" + "=" * 70)
    print("      TRAVEL CONCIERGE MULTI-AGENT EVALUATION BENCHMARK")
    print("=" * 70)

    for tc in EVAL_DATASET:
        print(f"\n[Running Test Case: {tc.id}] {tc.name} ({tc.category})")
        print(f"  Description: {tc.description}")

        case_passed = True
        scores: List[MetricScore] = []
        error_caught = None
        plan_result = None

        try:
            plan_result = root_agent.plan_trip(
                destination=tc.destination,
                dining_query=tc.dining_query,
                context_id=f"eval-{tc.id}",
                token_claims=tc.token_claims,
                auto_confirm_booking=True,
            )
        except Exception as e:
            error_caught = e

        if tc.expected_status == "forbidden":
            sec_score = EvaluationSuite.evaluate_security_enforcement(error_caught)
            scores.append(sec_score)
            if not sec_score.passed:
                case_passed = False
        else:
            if error_caught:
                case_passed = False
                scores.append(MetricScore("execution_success", False, 0.0, f"Error: {error_caught}"))
            else:
                # Evaluate Intent Routing
                ir_score = EvaluationSuite.evaluate_intent_routing(plan_result, tc.destination)
                scores.append(ir_score)
                if not ir_score.passed:
                    case_passed = False

                # Evaluate Task Propagation
                tp_score = EvaluationSuite.evaluate_task_propagation(plan_result, tc.expected_hotel_task_prefix)
                scores.append(tp_score)
                if not tp_score.passed:
                    case_passed = False

                # Evaluate Guardrails & Conciseness
                gr_score = EvaluationSuite.evaluate_guardrail_compliance(plan_result)
                scores.append(gr_score)
                if not gr_score.passed:
                    case_passed = False

                # Evaluate Cache Efficiency & Cost
                ce_score = EvaluationSuite.evaluate_cache_efficiency(plan_result["telemetry"], tc.min_cache_hit_rate)
                scores.append(ce_score)
                if not ce_score.passed:
                    case_passed = False

                # LLM Judge
                judge_eval = judge.judge_trip_plan(
                    user_request={"destination": tc.destination, "dining": tc.dining_query},
                    agent_output=plan_result,
                )
                print(f"  LLM Judge Score: {judge_eval['overall_score']}/5.0 | {judge_eval['reasoning']}")

                # Multi-turn Refinement & Escalation Evaluation
                if tc.refinement_query:
                    print(f"  [Executing Multi-turn Refinement]: {tc.refinement_query}")
                    refined_result = root_agent.refine_itinerary(
                        context_id=f"eval-{tc.id}",
                        refinement_query=tc.refinement_query,
                        token_claims=tc.token_claims,
                        auto_confirm_booking=True,
                    )
                    mt_score = EvaluationSuite.evaluate_multi_turn_refinement(refined_result)
                    scores.append(mt_score)
                    if not mt_score.passed:
                        case_passed = False

                    if tc.expected_escalation is not None:
                        esc_score = EvaluationSuite.evaluate_model_escalation(refined_result, tc.expected_escalation)
                        scores.append(esc_score)
                        if not esc_score.passed:
                            case_passed = False

        for s in scores:
            status_symbol = "✓ PASS" if s.passed else "✗ FAIL"
            print(f"    - [{status_symbol}] {s.metric_name}: {s.details}")
            total_metrics_evaluated += 1
            if s.passed:
                total_passed += 1

        results.append({
            "test_case_id": tc.id,
            "name": tc.name,
            "category": tc.category,
            "passed": case_passed,
            "metrics": [{"name": s.metric_name, "passed": s.passed, "score": s.score, "details": s.details} for s in scores],
        })

    pass_rate = (total_passed / total_metrics_evaluated * 100) if total_metrics_evaluated > 0 else 0

    print("\n" + "=" * 70)
    print(f"BENCHMARK SUMMARY: {total_passed}/{total_metrics_evaluated} Metrics Passed ({pass_rate:.1f}%)")
    print("=" * 70 + "\n")

    return {
        "total_test_cases": len(EVAL_DATASET),
        "total_metrics_evaluated": total_metrics_evaluated,
        "total_passed": total_passed,
        "pass_rate_percent": pass_rate,
        "details": results,
    }


if __name__ == "__main__":
    benchmark_results = run_benchmark()
    if benchmark_results["pass_rate_percent"] < 100.0:
        sys.exit(1)
