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
    list_vertex_reasoning_engines,
    resolve_or_provision_reasoning_engine,
    ensure_reasoning_engine_package_spec,
    deploy_or_update_reasoning_engine,
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


@patch("scripts.register_adk_agent.resolve_or_provision_reasoning_engine")
@patch("scripts.register_adk_agent.list_gemini_enterprise_agents")
@patch("scripts.register_adk_agent.run_cmd")
def test_register_or_update_adk_agent_existing(mock_run_cmd, mock_list, mock_resolve):
    mock_resolve.return_value = "projects/test-proj/locations/us-central1/reasoningEngines/974471042296709120"
    existing_agent = {
        "name": "projects/123/locations/global/collections/default_collection/engines/fdedemoapp/assistants/default_assistant/agents/agent-1",
        "displayName": "Travel Concierge",
        "sharingConfig": {"scope": "ALL_USERS"},
        "state": "ENABLED",
        "adkAgentDefinition": {
            "provisionedReasoningEngine": {
                "reasoningEngine": "projects/test-proj/locations/us-central1/reasoningEngines/974471042296709120"
            }
        }
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


@patch("scripts.register_adk_agent.resolve_or_provision_reasoning_engine")
@patch("scripts.register_adk_agent.list_gemini_enterprise_agents")
@patch("scripts.register_adk_agent.run_cmd")
def test_register_or_update_adk_agent_new(mock_run_cmd, mock_list, mock_resolve):
    mock_resolve.return_value = "projects/test-proj/locations/us-central1/reasoningEngines/974471042296709120"
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


@patch("scripts.register_adk_agent.list_vertex_reasoning_engines")
def test_resolve_or_provision_reasoning_engine_existing(mock_list_engines):
    mock_list_engines.return_value = [
        {"name": "projects/test-proj/locations/us-central1/reasoningEngines/existing-123", "displayName": "Travel Concierge Root Agent"}
    ]
    re_name = resolve_or_provision_reasoning_engine(
        project_id="test-proj",
        region="us-central1",
        display_name="Travel Concierge Root Agent",
        access_token="mock-token",
    )
    assert re_name == "projects/test-proj/locations/us-central1/reasoningEngines/existing-123"


@patch("scripts.register_adk_agent.run_cmd")
@patch("scripts.register_adk_agent.list_vertex_reasoning_engines")
def test_resolve_or_provision_reasoning_engine_provisions_new(mock_list_engines, mock_run_cmd):
    mock_list_engines.return_value = []
    # Mock REST API call or SDK
    mock_run_cmd.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps({
            "name": "operations/op-123",
            "response": {"name": "projects/test-proj/locations/us-central1/reasoningEngines/newly-created-456"}
        })
    )

    with patch("vertexai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_ae = MagicMock()
        mock_ae.api_resource.name = "projects/test-proj/locations/us-central1/reasoningEngines/sdk-created-789"
        mock_client.agent_engines.create.return_value = mock_ae
        mock_client_cls.return_value = mock_client

        re_name = resolve_or_provision_reasoning_engine(
            project_id="test-proj",
            region="us-central1",
            display_name="Travel Concierge Root Agent",
            access_token="mock-token",
        )
        assert re_name == "projects/test-proj/locations/us-central1/reasoningEngines/sdk-created-789"
        assert "123456" not in re_name


@patch("scripts.register_adk_agent.run_cmd")
@patch("scripts.register_adk_agent.list_vertex_reasoning_engines")
def test_resolve_or_provision_reasoning_engine_raises_error_no_fallback(mock_list_engines, mock_run_cmd):
    mock_list_engines.return_value = []
    mock_run_cmd.return_value = MagicMock(returncode=1, stdout="", stderr="API Error")

    with patch("vertexai.Client", side_effect=Exception("API disabled")):
        with pytest.raises(RuntimeError) as exc_info:
            resolve_or_provision_reasoning_engine(
                project_id="test-proj",
                region="us-central1",
                display_name="Travel Concierge Root Agent",
                access_token="mock-token",
            )
        assert "Unable to discover or provision a valid Vertex AI Reasoning Engine" in str(exc_info.value)
        assert "123456" not in str(exc_info.value)


@patch("google.cloud.aiplatform_v1.ReasoningEngineServiceClient")
def test_ensure_reasoning_engine_package_spec_valid(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_re = MagicMock()
    mock_re.spec.package_spec.pickle_object_gcs_uri = "gs://bucket/re.pkl"
    mock_re.spec.package_spec.python_version = "3.12"
    mock_client.get_reasoning_engine.return_value = mock_re

    valid = ensure_reasoning_engine_package_spec(
        reasoning_engine_name="projects/p/locations/us-central1/reasoningEngines/123",
        project_id="p",
        region="us-central1",
        auto_repair=False,
    )
    assert valid is True


@patch("scripts.register_adk_agent.deploy_or_update_reasoning_engine")
@patch("google.cloud.aiplatform_v1.ReasoningEngineServiceClient")
def test_ensure_reasoning_engine_package_spec_auto_repair(mock_client_cls, mock_deploy):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_re = MagicMock()
    # Missing package_spec
    mock_re.spec.package_spec = None
    mock_client.get_reasoning_engine.return_value = mock_re
    mock_deploy.return_value = "projects/p/locations/us-central1/reasoningEngines/123"

    valid = ensure_reasoning_engine_package_spec(
        reasoning_engine_name="projects/p/locations/us-central1/reasoningEngines/123",
        project_id="p",
        region="us-central1",
        auto_repair=True,
    )
    assert valid is True
    mock_deploy.assert_called_once_with(
        reasoning_engine_name="projects/p/locations/us-central1/reasoningEngines/123",
        project_id="p",
        region="us-central1",
    )

