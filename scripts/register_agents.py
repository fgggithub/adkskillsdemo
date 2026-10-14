#!/usr/bin/env python3
"""
scripts/register_agents.py

Automates registration of the Travel Concierge Root Agent and associated services
into Google Cloud Agent Registry (agentregistry.googleapis.com).

Builds and uploads the A2A Agent Card specification, registers the service endpoint,
and links the dietary_advisor and travel_planning skills to the agent.
"""
import os
import sys
import json
import logging
import argparse
import subprocess
from typing import Dict, Any, Optional, List

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from travel_concierge.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("travel_concierge.agents.registry")


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Executes a subprocess command safely returning stdout/stderr."""
    logger.debug(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        logger.error(f"Command failed ({result.returncode}): {' '.join(cmd)}\nStderr: {result.stderr.strip()}")
        raise RuntimeError(f"Command failed: {result.stderr.strip()}")
    return result


def get_default_project_id() -> str:
    """Retrieves project ID from gcloud config or settings."""
    try:
        res = run_cmd(["gcloud", "config", "get-value", "project"], check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return settings.project_id or "qwiklabs-gcp-04-0f982849de12"


def get_service_url(service_name: str, region: str, project_id: str) -> Optional[str]:
    """Retrieves the live Cloud Run endpoint URL for a given service."""
    try:
        res = run_cmd(
            ["gcloud", "run", "services", "describe", service_name,
             f"--region={region}", f"--project={project_id}",
             "--format=value(status.url)"],
            check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception as e:
        logger.warning(f"Could not fetch Cloud Run URL for {service_name}: {e}")
    return None


def build_a2a_agent_card(service_url: str) -> Dict[str, Any]:
    """Builds standard A2A Agent Card JSON payload for the Root Orchestrator."""
    return {
        "name": "Travel Concierge Root Agent",
        "description": "Enterprise Travel Dining & Hotel Concierge Root Agent coordinating hotel, dining, and verification agents.",
        "version": "2.0.0",
        "protocolVersion": "0.3.0",
        "url": service_url,
        "capabilities": {
            "streaming": True,
            "contextCaching": True,
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "dietary_advisor",
                "name": "dietary_advisor",
                "description": "Rules for filtering dining options based on dietary restrictions, allergies, and safety ratings.",
                "tags": ["dietary", "dining", "safety"]
            },
            {
                "id": "travel_planning",
                "name": "travel_planning",
                "description": "Coordinates multi-agent travel reservations, hotel recommendations, and dining itineraries.",
                "tags": ["travel", "hotel", "planning"]
            }
        ]
    }


def register_service_in_location(
    service_id: str,
    location: str,
    project_id: str,
    display_name: str,
    description: str,
    agent_card: Dict[str, Any]
) -> bool:
    """Registers or verifies the service in Google Cloud Agent Registry for a location."""
    card_json_str = json.dumps(agent_card)

    # Check if service already exists
    check_res = run_cmd(
        ["gcloud", "alpha", "agent-registry", "services", "describe", service_id,
         f"--location={location}", f"--project={project_id}"],
        check=False
    )

    if check_res.returncode == 0:
        logger.info(f"Service '{service_id}' already exists in Agent Registry (location: {location}).")
        return True

    logger.info(f"Registering '{service_id}' in Agent Registry (location: {location})...")
    create_res = run_cmd(
        [
            "gcloud", "alpha", "agent-registry", "services", "create", service_id,
            f"--location={location}",
            f"--project={project_id}",
            f"--display-name={display_name}",
            f"--description={description}",
            "--agent-spec-type=a2a-agent-card",
            f"--agent-spec-content={card_json_str}"
        ],
        check=False
    )

    if create_res.returncode == 0:
        logger.info(f"✓ Successfully registered '{service_id}' in Agent Registry (location: {location}).")
        return True
    else:
        logger.warning(f"Registration in {location} returned non-zero: {create_res.stderr.strip()}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Register Root Agent in GCP Agent Registry")
    parser.add_argument("--project-id", type=str, default=None, help="GCP Project ID")
    parser.add_argument("--region", type=str, default="us-central1", help="GCP Cloud Run Region")
    parser.add_argument("--service-url", type=str, default=None, help="Cloud Run Root Agent Endpoint URL")
    parser.add_argument("--service-name", type=str, default="travel-concierge-orchestrator", help="Service ID")
    parser.add_argument("--display-name", type=str, default="Travel Concierge Root Agent", help="Display Name")
    args = parser.parse_args()

    project_id = args.project_id or get_default_project_id()
    service_url = args.service_url or get_service_url(args.service_name, args.region, project_id)

    if not service_url:
        service_url = f"https://{args.service_name}-377893749182.{args.region}.run.app"
        logger.warning(f"Service URL not resolved automatically. Using fallback: {service_url}")

    description = "Enterprise Travel Dining & Hotel Concierge Root Agent coordinating hotel, dining, and verification agents."
    agent_card = build_a2a_agent_card(service_url)

    print("\n" + "=" * 65)
    print("      GCP AGENT REGISTRY ROOT AGENT REGISTRATION")
    print("=" * 65)
    print(f"Target Project:  {project_id}")
    print(f"Service ID:      {args.service_name}")
    print(f"Service URL:     {service_url}")
    print(f"Display Name:    {args.display_name}")
    print("-" * 65)

    locations = ["global", args.region]
    success_count = 0

    for loc in locations:
        if register_service_in_location(
            service_id=args.service_name,
            location=loc,
            project_id=project_id,
            display_name=args.display_name,
            description=description,
            agent_card=agent_card
        ):
            success_count += 1

    print("\nVerification in GCP Agent Registry:")
    try:
        verify_cmd = run_cmd(
            ["gcloud", "alpha", "agent-registry", "agents", "list",
             "--location=global", f"--project={project_id}"],
            check=False
        )
        if verify_cmd.returncode == 0:
            print(verify_cmd.stdout.strip())
    except Exception as e:
        logger.warning(f"Could not list registered agents: {e}")

    print("=" * 65 + "\n")
    if success_count > 0:
        logger.info(f"Agent registration completed successfully ({success_count}/{len(locations)} locations).")
        sys.exit(0)
    else:
        logger.error("Agent registration failed across all locations.")
        sys.exit(1)


if __name__ == "__main__":
    main()
