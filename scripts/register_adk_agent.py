#!/usr/bin/env python3
"""
scripts/register_adk_agent.py

Registers and manages an ADK Agent in Gemini Enterprise App/Engine.
Follows official Google Cloud Gemini Enterprise documentation:
https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent

Features:
- Lists existing agents registered under Gemini Enterprise App assistant
- Registers ADK Agent using Discovery Engine v1alpha Assistant Agents API
- Configures agent displayName, description, icon, and provisionedReasoningEngine
- Configures agent sharing policy (scope: ALL_USERS)
- Supports idempotent registration, updating, and teardown
- Exports registration artifacts in JSON and YAML formats
"""

import os
import sys
import json
import logging
import argparse
import subprocess
from typing import Dict, Any, Optional, List
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from travel_concierge.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("travel_concierge.register_adk_agent")


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Executes a subprocess command returning stdout/stderr."""
    logger.debug(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        logger.error(f"Command failed ({result.returncode}): {' '.join(cmd)}\nStderr: {result.stderr.strip()}")
        raise RuntimeError(f"Command failed: {result.stderr.strip()}")
    return result


def get_default_project_id() -> str:
    """Retrieves project ID from gcloud config or environment variables."""
    try:
        res = run_cmd(["gcloud", "config", "get-value", "project"], check=False)
        if res.returncode == 0 and res.stdout.strip() and "(unset)" not in res.stdout:
            return res.stdout.strip()
    except Exception:
        pass
    return os.getenv("PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or settings.project_id or ""


def get_project_number(project_id: str) -> Optional[str]:
    """Retrieves numeric project number for a given GCP project ID."""
    try:
        res = run_cmd(
            ["gcloud", "projects", "describe", project_id, "--format=value(projectNumber)"],
            check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception as e:
        logger.warning(f"Could not retrieve project number via gcloud: {e}")
    return os.getenv("PROJECT_NUMBER")


def get_active_access_token() -> Optional[str]:
    """Retrieves a GCP OAuth access token."""
    token = os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")
    if token:
        return token
    try:
        res = run_cmd(["gcloud", "auth", "print-access-token"], check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to fetch gcloud access token: {e}")
    return None


def build_adk_agent_payload(
    display_name: str = "Travel Concierge",
    description: str = "Travel Concierge Agent for flight, hotel, and restaurant booking",
    reasoning_engine_resource: Optional[str] = None,
    icon_uri: Optional[str] = "https://storage.googleapis.com/cloud-samples-data/gen-app-builder/search/cymbal-bank-logo.png",
    share_with_all_users: bool = True,
    tool_authorizations: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Constructs the ADK Agent registration payload adhering to Discovery Engine v1alpha schema.
    Reference: https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent
    """
    payload: Dict[str, Any] = {
        "displayName": display_name,
        "description": description,
    }

    if icon_uri:
        payload["icon"] = {"uri": icon_uri}

    if reasoning_engine_resource:
        payload["adkAgentDefinition"] = {
            "provisionedReasoningEngine": {
                "reasoningEngine": reasoning_engine_resource
            }
        }

    if share_with_all_users:
        payload["sharingConfig"] = {
            "scope": "ALL_USERS"
        }

    if tool_authorizations:
        payload["authorizationConfig"] = {
            "toolAuthorizations": tool_authorizations
        }

    return payload


def list_gemini_enterprise_agents(
    project_id: str,
    app_id: str = "fdedemoapp",
    location: str = "global",
    access_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Lists all agents connected to the Gemini Enterprise App assistant."""
    token = access_token or get_active_access_token()
    if not token:
        logger.warning("No OAuth token available to list Gemini Enterprise agents.")
        return []

    base_endpoint = "discoveryengine.googleapis.com" if location == "global" else f"{location}-discoveryengine.googleapis.com"
    url = f"https://{base_endpoint}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{app_id}/assistants/default_assistant/agents"

    curl_cmd = [
        "curl", "-s", "-X", "GET",
        "-H", f"Authorization: Bearer {token}",
        "-H", f"X-Goog-User-Project: {project_id}",
        url
    ]
    res = run_cmd(curl_cmd, check=False)
    if res.returncode == 0 and res.stdout.strip():
        try:
            data = json.loads(res.stdout)
            return data.get("agents", [])
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse agent list JSON response: {res.stdout[:200]}")
    return []


def register_or_update_adk_agent(
    project_id: str,
    app_id: str = "fdedemoapp",
    location: str = "global",
    display_name: str = "Travel Concierge",
    description: str = "Travel Concierge Agent for flight, hotel, and restaurant booking",
    reasoning_engine_resource: Optional[str] = None,
    share_with_all_users: bool = True,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Registers or updates an ADK Agent in Gemini Enterprise.
    Performs idempotent lookup, updates sharingConfig if already present, or registers new.
    """
    token = access_token or get_active_access_token()
    if not token:
        raise RuntimeError("GCP access token required for agent registration.")

    base_endpoint = "discoveryengine.googleapis.com" if location == "global" else f"{location}-discoveryengine.googleapis.com"

    if not reasoning_engine_resource:
        reasoning_engine_resource = f"projects/{project_id}/locations/us-central1/reasoningEngines/123456"

    # 1. Check existing agents
    existing_agents = list_gemini_enterprise_agents(
        project_id=project_id,
        app_id=app_id,
        location=location,
        access_token=token,
    )

    matching_agent = None
    for agent in existing_agents:
        if agent.get("displayName") == display_name:
            matching_agent = agent
            break

    if matching_agent:
        agent_name = matching_agent.get("name")
        logger.info(f"✓ Agent '{display_name}' already exists in Gemini Enterprise: {agent_name}")
        # Ensure reasoningEngine points to the target resource
        current_engine = matching_agent.get("adkAgentDefinition", {}).get("provisionedReasoningEngine", {}).get("reasoningEngine")
        if reasoning_engine_resource and current_engine != reasoning_engine_resource:
            logger.info(f"Updating reasoningEngine to {reasoning_engine_resource}...")
            patch_url = f"https://{base_endpoint}/v1alpha/{agent_name}?updateMask=adkAgentDefinition"
            patch_cmd = [
                "curl", "-s", "-X", "PATCH",
                "-H", f"Authorization: Bearer {token}",
                "-H", "Content-Type: application/json",
                "-H", f"X-Goog-User-Project: {project_id}",
                patch_url,
                "-d", json.dumps({"adkAgentDefinition": {"provisionedReasoningEngine": {"reasoningEngine": reasoning_engine_resource}}})
            ]
            patch_res = run_cmd(patch_cmd, check=False)
            if patch_res.returncode == 0:
                try:
                    matching_agent = json.loads(patch_res.stdout)
                except Exception:
                    pass

        # Ensure sharingConfig is ALL_USERS
        if share_with_all_users and matching_agent.get("sharingConfig", {}).get("scope") != "ALL_USERS":
            logger.info("Updating sharingConfig to ALL_USERS...")
            patch_url = f"https://{base_endpoint}/v1alpha/{agent_name}?updateMask=sharingConfig"
            patch_cmd = [
                "curl", "-s", "-X", "PATCH",
                "-H", f"Authorization: Bearer {token}",
                "-H", "Content-Type: application/json",
                "-H", f"X-Goog-User-Project: {project_id}",
                patch_url,
                "-d", json.dumps({"sharingConfig": {"scope": "ALL_USERS"}})
            ]
            run_cmd(patch_cmd, check=False)
        return matching_agent

    # 2. Register new ADK Agent
    payload = build_adk_agent_payload(
        display_name=display_name,
        description=description,
        reasoning_engine_resource=reasoning_engine_resource,
        share_with_all_users=share_with_all_users,
    )

    create_url = f"https://{base_endpoint}/v1alpha/projects/{project_id}/locations/{location}/collections/default_collection/engines/{app_id}/assistants/default_assistant/agents"
    create_cmd = [
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-H", f"X-Goog-User-Project: {project_id}",
        create_url,
        "-d", json.dumps(payload)
    ]

    res = run_cmd(create_cmd, check=False)
    if res.returncode == 0 and res.stdout.strip():
        try:
            data = json.loads(res.stdout)
            if "error" in data:
                logger.error(f"Discovery Engine returned error: {data['error']}")
                raise RuntimeError(data["error"].get("message", "Registration failed"))
            logger.info(f"✓ Successfully registered ADK Agent '{display_name}' in Gemini Enterprise: {data.get('name')}")
            return data
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON returned: {res.stdout}")
            raise RuntimeError(f"Unexpected response: {res.stdout[:200]}")

    raise RuntimeError(f"Failed to register ADK Agent in Gemini Enterprise: {res.stderr}")


def delete_adk_agent(
    agent_name: str,
    project_id: str,
    location: str = "global",
    access_token: Optional[str] = None,
) -> bool:
    """Deletes an agent from Gemini Enterprise assistant."""
    token = access_token or get_active_access_token()
    if not token:
        return False

    base_endpoint = "discoveryengine.googleapis.com" if location == "global" else f"{location}-discoveryengine.googleapis.com"
    url = f"https://{base_endpoint}/v1alpha/{agent_name}"
    cmd = [
        "curl", "-s", "-X", "DELETE",
        "-H", f"Authorization: Bearer {token}",
        "-H", f"X-Goog-User-Project: {project_id}",
        url
    ]
    res = run_cmd(cmd, check=False)
    if res.returncode == 0:
        logger.info(f"✓ Successfully deleted agent '{agent_name}'.")
        return True
    return False


def export_agent_registration_artifacts(
    agent_data: Dict[str, Any],
    project_id: str,
    app_id: str,
    location: str,
    output_json: str = "deploy/gemini_enterprise_agent_registration.json",
    output_yaml: str = "deploy/agent_gateway/gemini_enterprise_agent_registration.yaml",
) -> None:
    """Exports registration metadata to JSON and YAML files."""
    record = {
        "$schema": "https://cloud.google.com/gemini-enterprise/schemas/agent-registration-v1.json",
        "gemini_enterprise_adk_agent": {
            "project_id": project_id,
            "app_id": app_id,
            "location": location,
            "documentation": "https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-an-adk-agent",
            "agent": agent_data,
            "console_url": f"https://console.cloud.google.com/gemini-enterprise/locations/{location}/engines/{app_id}/agentic/agents?project={project_id}"
        }
    }

    Path(output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    logger.info(f"✓ Exported registration JSON to: {output_json}")

    try:
        import yaml
        Path(output_yaml).parent.mkdir(parents=True, exist_ok=True)
        with open(output_yaml, "w", encoding="utf-8") as f:
            yaml.dump(record, f, default_flow_style=False, sort_keys=False)
        logger.info(f"✓ Exported registration YAML to: {output_yaml}")
    except ImportError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Register ADK Agent in Gemini Enterprise App")
    parser.add_argument("--project-id", type=str, default="", help="GCP Project ID")
    parser.add_argument("--app-id", type=str, default="fdedemoapp", help="Gemini Enterprise App ID")
    parser.add_argument("--location", type=str, default="global", help="Location (global or us)")
    parser.add_argument("--display-name", type=str, default="Travel Concierge", help="Agent Display Name")
    parser.add_argument("--description", type=str, default="Travel Concierge Agent for flight, hotel, and restaurant booking", help="Agent description")
    parser.add_argument("--reasoning-engine", type=str, default="", help="Vertex AI Reasoning Engine resource path")
    parser.add_argument("--list-only", action="store_true", help="Only list registered agents")
    parser.add_argument("--delete", type=str, default="", help="Resource path of agent to delete")
    args = parser.parse_args()

    project_id = args.project_id or get_default_project_id()
    if not project_id:
        logger.error("Project ID is required.")
        sys.exit(1)

    if args.delete:
        success = delete_adk_agent(agent_name=args.delete, project_id=project_id, location=args.location)
        sys.exit(0 if success else 1)

    if args.list_only:
        agents = list_gemini_enterprise_agents(project_id=project_id, app_id=args.app_id, location=args.location)
        print(json.dumps(agents, indent=2))
        sys.exit(0)

    agent_data = register_or_update_adk_agent(
        project_id=project_id,
        app_id=args.app_id,
        location=args.location,
        display_name=args.display_name,
        description=args.description,
        reasoning_engine_resource=args.reasoning_engine or None,
        share_with_all_users=True,
    )

    export_agent_registration_artifacts(
        agent_data=agent_data,
        project_id=project_id,
        app_id=args.app_id,
        location=args.location,
    )

    console_url = f"https://console.cloud.google.com/gemini-enterprise/locations/{args.location}/engines/{args.app_id}/agentic/agents?project={project_id}"
    print("\n" + "=" * 70)
    print(" [✓] GEMINI ENTERPRISE ADK AGENT REGISTRATION COMPLETED")
    print("=" * 70)
    print(f" Agent Name:     {agent_data.get('name')}")
    print(f" Display Name:   {agent_data.get('displayName')}")
    print(f" State:          {agent_data.get('state')}")
    print(f" Sharing Scope:  {agent_data.get('sharingConfig', {}).get('scope', 'N/A')}")
    print(f" Console URL:    {console_url}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
