"""
tests/test_register_adk_agent.py

Unit tests for scripts/register_adk_agent.py
Tests payload formatting, agent listing, registration logic, artifact export, and teardown.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock

from scripts.register_adk_agent import (
    build_adk_agent_payload,
    list_gemini_enterprise_agents,
    register_or_update_adk_agent,
    delete_adk_agent,
    export_agent_registration_artifacts,
)


def test_build_adk_agent_payload_defaults():
    payload = build_adk_agent_payload()
    assert payload["displayName"] == "Travel Concierge"
    assert "description" in payload
    assert "sharingConfig" in payload
    assert payload["sharingConfig"]["scope"] == "ALL_USERS"
    assert "icon" in payload


def test_build_adk_agent_payload_custom():
    payload = build_adk_agent_payload(
        display_name="Custom Concierge",
        description="Custom description",
        reasoning_engine_resource="projects/test-proj/locations/us-central1/reasoningEngines/999",
        share_with_all_users=False,
        tool_authorizations=["projects/123/locations/global/authorizations/auth-1"],
    )
    assert payload["displayName"] == "Custom Concierge"
    assert payload["description"] == "Custom description"
    assert "sharingConfig" not in payload
    assert payload["adkAgentDefinition"]["provisionedReasoningEngine"]["reasoningEngine"] == (
        "projects/test-proj/locations/us-central1/reasoningEngines/999"
    )
    assert payload["authorizationConfig"]["toolAuthorizations"] == [
        "projects/123/locations/global/authorizations/auth-1"
    ]


@patch("scripts.register_adk_agent.run_cmd")
def test_list_gemini_enterprise_agents(mock_run_cmd):
    mock_run_cmd.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "agents": [
                {
                    "name": "projects/123/locations/global/collections/default_collection/engines/fdedemoapp/assistants/default_assistant/agents/agent-1",
                    "displayName": "Travel Concierge",
                    "state": "ENABLED",
                }
            ]
        }),
    )

    agents = list_gemini_enterprise_agents(
        project_id="test-proj",
        app_id="fdedemoapp",
        location="global",
        access_token="mock-token",
    )

    assert len(agents) == 1
    assert agents[0]["displayName"] == "Travel Concierge"
    assert agents[0]["state"] == "ENABLED"


@patch("scripts.register_adk_agent.list_gemini_enterprise_agents")
@patch("scripts.register_adk_agent.run_cmd")
def test_register_or_update_adk_agent_existing(mock_run_cmd, mock_list):
    existing_agent = {
        "name": "projects/123/locations/global/collections/default_collection/engines/fdedemoapp/assistants/default_assistant/agents/agent-1",
        "displayName": "Travel Concierge",
        "sharingConfig": {"scope": "ALL_USERS"},
        "state": "ENABLED",
    }
    mock_list.return_value = [existing_agent]

    res = register_or_update_adk_agent(
        project_id="test-proj",
        app_id="fdedemoapp",
        location="global",
        display_name="Travel Concierge",
        access_token="mock-token",
    )

    assert res["displayName"] == "Travel Concierge"
    assert res["name"] == existing_agent["name"]


@patch("scripts.register_adk_agent.list_gemini_enterprise_agents")
@patch("scripts.register_adk_agent.run_cmd")
def test_register_or_update_adk_agent_new(mock_run_cmd, mock_list):
    mock_list.return_value = []
    mock_run_cmd.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "name": "projects/123/locations/global/collections/default_collection/engines/fdedemoapp/assistants/default_assistant/agents/new-agent",
            "displayName": "Travel Concierge",
            "state": "ENABLED",
        }),
    )

    res = register_or_update_adk_agent(
        project_id="test-proj",
        app_id="fdedemoapp",
        location="global",
        display_name="Travel Concierge",
        access_token="mock-token",
    )

    assert res["displayName"] == "Travel Concierge"
    assert "new-agent" in res["name"]


@patch("scripts.register_adk_agent.run_cmd")
def test_delete_adk_agent(mock_run_cmd):
    mock_run_cmd.return_value = MagicMock(returncode=0, stdout="")
    success = delete_adk_agent(
        agent_name="projects/123/locations/global/collections/default_collection/engines/fdedemoapp/assistants/default_assistant/agents/agent-1",
        project_id="test-proj",
        location="global",
        access_token="mock-token",
    )
    assert success is True


def test_export_agent_registration_artifacts(tmp_path):
    json_path = str(tmp_path / "agent_reg.json")
    yaml_path = str(tmp_path / "agent_reg.yaml")

    mock_agent = {
        "name": "projects/123/locations/global/collections/default_collection/engines/fdedemoapp/assistants/default_assistant/agents/agent-1",
        "displayName": "Travel Concierge",
        "state": "ENABLED",
    }

    export_agent_registration_artifacts(
        agent_data=mock_agent,
        project_id="test-proj",
        app_id="fdedemoapp",
        location="global",
        output_json=json_path,
        output_yaml=yaml_path,
    )

    assert os.path.exists(json_path)
    with open(json_path) as f:
        data = json.load(f)
    assert data["gemini_enterprise_adk_agent"]["project_id"] == "test-proj"
    assert data["gemini_enterprise_adk_agent"]["agent"]["displayName"] == "Travel Concierge"
