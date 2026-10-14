#!/usr/bin/env python3
"""
Google Cloud Agent Platform - Managed Agent Gateway Provisioning & Inspection CLI

Interacts with:
- Google Cloud Network Services Agent Gateways (networkservices.googleapis.com)
- Service Extensions AuthzExtensions (serviceextensions.googleapis.com)
- Network Security AuthzPolicies (networksecurity.googleapis.com)
- Model Armor Templates (modelarmor.googleapis.com)
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent_gateway_cli")


def run_cmd(cmd, check=True):
    logger.debug(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        logger.error(f"Command failed (exit {result.returncode}): {' '.join(cmd)}\nStderr: {result.stderr.strip()}")
        raise RuntimeError(result.stderr.strip())
    return result


def get_default_project():
    res = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True)
    val = res.stdout.strip()
    return val if val and "(unset)" not in val else None


def list_gateways(location="us-central1"):
    res = run_cmd(["gcloud", "network-services", "agent-gateways", "list", f"--location={location}", "--format=json"], check=False)
    if res.returncode == 0:
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            return []
    return []


def describe_gateway(name, location="us-central1"):
    res = run_cmd(["gcloud", "network-services", "agent-gateways", "describe", name, f"--location={location}", "--format=json"], check=False)
    if res.returncode == 0:
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Manage Google Cloud Agent Platform Gateway")
    parser.add_argument("action", choices=["status", "describe", "list"], default="status", nargs="?", help="Action to perform")
    parser.add_argument("--name", default="travel-concierge-gateway", help="Agent gateway name")
    parser.add_argument("--location", default="us-central1", help="GCP Region")
    parser.add_argument("--project-id", default=None, help="GCP Project ID")
    args = parser.parse_args()

    project_id = args.project_id or os.environ.get("PROJECT_ID") or get_default_project()
    logger.info(f"Using Project: {project_id}, Region: {args.location}")

    if args.action in ["status", "describe"]:
        gw = describe_gateway(args.name, location=args.location)
        if gw:
            print("\n" + "=" * 65)
            print("       GOOGLE CLOUD AGENT PLATFORM - AGENT GATEWAY")
            print("=" * 65)
            print(f"Gateway Name:      {gw.get('name')}")
            print(f"Governed Path:     {gw.get('googleManaged', {}).get('governedAccessPath')}")
            print(f"Protocols:         {gw.get('protocols')}")
            print(f"Created Time:      {gw.get('createTime')}")
            card = gw.get("agentGatewayCard", {})
            print(f"mTLS Endpoint:     {card.get('mtlsEndpoint')}")
            print(f"Service Account:   {card.get('serviceExtensionsServiceAccount')}")
            print("=" * 65 + "\n")
        else:
            logger.warning(f"Agent Gateway '{args.name}' not found in {args.location}.")
    elif args.action == "list":
        gateways = list_gateways(location=args.location)
        print(f"Found {len(gateways)} gateway(s) in {args.location}:")
        for g in gateways:
            print(f" - {g.get('name')}")


if __name__ == "__main__":
    main()
