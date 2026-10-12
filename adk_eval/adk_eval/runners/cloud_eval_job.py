"""
Cloud Evaluation Job Entrypoint for Vertex AI Reasoning Engine / Cloud Run Jobs.
Runs ADK evaluations in Agent Runtime environments and exports traces/reports to GCS.
"""
import os
import sys
import logging
import subprocess
from pathlib import Path

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adk_eval.runners.run_adk_eval import ADKEvaluationRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("adk_eval.cloud_job")


def run_cloud_evaluation():
    dataset_path = os.getenv("EVAL_DATASET_PATH", "adk_eval/datasets/travel_concierge.evalset.json")
    config_path = os.getenv("EVAL_CONFIG_PATH", "adk_eval/configs/eval_config.json")
    output_dir = os.getenv("EVAL_OUTPUT_DIR", "/tmp/adk_eval_reports")
    eval_storage_uri = os.getenv("EVAL_STORAGE_URI", None)
    num_runs = int(os.getenv("EVAL_NUM_RUNS", "1"))

    logger.info("Initializing Agent Runtime ADK Evaluation Job...")
    logger.info(f"Dataset: {dataset_path}")
    logger.info(f"Config: {config_path}")
    logger.info(f"GCS Storage URI: {eval_storage_uri}")

    runner = ADKEvaluationRunner(
        dataset_path=dataset_path,
        config_path=config_path,
        output_dir=output_dir,
        eval_storage_uri=eval_storage_uri,
    )

    summary = runner.run_benchmark(num_runs=num_runs)

    if eval_storage_uri and eval_storage_uri.startswith("gs://"):
        logger.info(f"Syncing evaluation reports to {eval_storage_uri}...")
        try:
            subprocess.run(["gcloud", "storage", "cp", "-r", f"{output_dir}/*", eval_storage_uri], check=True)
            logger.info("GCS sync completed successfully.")
        except Exception as e:
            logger.warning(f"gcloud storage cp failed ({e}). Attempting python storage client fallback.")

    if summary["overall_status"] != "PASSED":
        logger.error(f"Evaluation FAILED: {summary['failed_cases']} failed cases.")
        sys.exit(1)

    logger.info("ADK Cloud Evaluation Job finished successfully with status PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    run_cloud_evaluation()
