"""
tests/test_gemini_enterprise_app.py

Unit and integration tests for Gemini Enterprise App 'fdedemoapp' provisioning
and agent registration in Google Cloud Agent Registry.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from scripts.create_gemini_enterprise_app import (
    build_engine_payload,
    get_or_create_gemini_enterprise_app,
    delete_gemini_enterprise_app,
    register_agent_with_gemini_enterprise,
    delete_agent_binding,
    build_app_configuration,
    write_configuration_files,
)


@pytest.fixture
def sample_engine_payload():
    return build_engine_payload(
        app_id="fdedemoapp",
        display_name="fdedemoapp",
        solution_type="SOLUTION_TYPE_CHAT",
        company_name="Travel Concierge",
    )


def test_build_engine_payload_chat(sample_engine_payload):
    assert sample_engine_payload["displayName"] == "fdedemoapp"
    assert sample_engine_payload["solutionType"] == "SOLUTION_TYPE_CHAT"
    assert sample_engine_payload["industryVertical"] == "GENERIC"
    assert "chatEngineConfig" in sample_engine_payload
    agent_cfg = sample_engine_payload["chatEngineConfig"]["agentCreationConfig"]
    assert agent_cfg["business"] == "Travel Concierge"
    assert agent_cfg["defaultLanguageCode"] == "en"
    assert agent_cfg["timeZone"] == "America/Los_Angeles"
    assert sample_engine_payload["commonConfig"]["companyName"] == "Travel Concierge"


def test_build_engine_payload_search():
    payload = build_engine_payload(
        app_id="fdedemoapp-search",
        display_name="fdedemoapp-search",
        solution_type="SEARCH",
    )
    assert payload["solutionType"] == "SOLUTION_TYPE_SEARCH"
    assert "searchEngineConfig" in payload
    assert payload["searchEngineConfig"]["searchTier"] == "SEARCH_TIER_ENTERPRISE"
    assert payload["appType"] == "APP_TYPE_INTRANET"


def test_create_or_get_app_existing_sdk():
    mock_engine = MagicMock()
    mock_engine.display_name = "fdedemoapp"

    mock_client = MagicMock()
    mock_client.get_engine.return_value = mock_engine

    with patch("google.cloud.discoveryengine_v1.EngineServiceClient", return_value=mock_client), \
         patch("google.cloud.discoveryengine_v1.Engine.to_dict", return_value={"displayName": "fdedemoapp", "name": "projects/p/locations/global/collections/default_collection/engines/fdedemoapp"}):
        result = get_or_create_gemini_enterprise_app(
            project_id="test-project",
            location="global",
            app_id="fdedemoapp",
            display_name="fdedemoapp",
        )
        assert result["displayName"] == "fdedemoapp"
        mock_client.get_engine.assert_called_once()


def test_create_or_get_app_new_sdk():
    from google.api_core.exceptions import NotFound

    mock_client = MagicMock()
    mock_client.get_engine.side_effect = NotFound("Engine not found")
    
    mock_operation = MagicMock()
    mock_operation.operation.name = "operations/create_engine_123"
    mock_result_engine = MagicMock()
    mock_operation.result.return_value = mock_result_engine

    mock_client.create_engine.return_value = mock_operation

    with patch("google.cloud.discoveryengine_v1.EngineServiceClient", return_value=mock_client), \
         patch("google.cloud.discoveryengine_v1.Engine.to_dict", return_value={"displayName": "fdedemoapp", "state": "ACTIVE"}):
        result = get_or_create_gemini_enterprise_app(
            project_id="test-project",
            location="global",
            app_id="fdedemoapp",
            display_name="fdedemoapp",
        )
        assert result["displayName"] == "fdedemoapp"
        mock_client.create_engine.assert_called_once()


def test_create_or_get_app_rest_fallback():
    # Force SDK failure
    with patch("google.cloud.discoveryengine_v1.EngineServiceClient", side_effect=Exception("SDK Unavailable")), \
         patch("scripts.create_gemini_enterprise_app.get_active_access_token", return_value="fake-token"), \
         patch("scripts.create_gemini_enterprise_app.run_cmd") as mock_run:

        # Mock GET returning engine JSON
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"name": "projects/p/locations/global/collections/default_collection/engines/fdedemoapp", "displayName": "fdedemoapp"}),
            stderr=""
        )

        result = get_or_create_gemini_enterprise_app(
            project_id="test-project",
            location="global",
            app_id="fdedemoapp",
        )
        assert result["displayName"] == "fdedemoapp"


def test_create_or_get_app_fallback_metadata():
    with patch("google.cloud.discoveryengine_v1.EngineServiceClient", side_effect=Exception("SDK error")), \
         patch("scripts.create_gemini_enterprise_app.get_active_access_token", return_value=None):
        result = get_or_create_gemini_enterprise_app(
            project_id="test-project",
            location="global",
            app_id="fdedemoapp",
            display_name="fdedemoapp",
        )
        assert result["displayName"] == "fdedemoapp"
        assert result["state"] == "ACTIVE"
        assert "projects/test-project/locations/global/collections/default_collection/engines/fdedemoapp" in result["name"]


def test_delete_gemini_enterprise_app():
    mock_client = MagicMock()
    mock_op = MagicMock()
    mock_op.operation.name = "operations/delete_123"
    mock_client.delete_engine.return_value = mock_op

    with patch("google.cloud.discoveryengine_v1.EngineServiceClient", return_value=mock_client):
        res = delete_gemini_enterprise_app(
            project_id="test-project",
            location="global",
            app_id="fdedemoapp"
        )
        assert res is True
        mock_client.delete_engine.assert_called_once()


def test_register_agent_with_gemini_enterprise():
    with patch("scripts.create_gemini_enterprise_app.run_cmd") as mock_run:
        # describe service -> 0 (already exists), describe binding -> 0 (already exists)
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="{}",
            stderr=""
        )

        reg = register_agent_with_gemini_enterprise(
            project_id="test-project",
            region="us-central1",
            app_id="fdedemoapp",
            service_url="https://travel-concierge-test.run.app",
            service_name="travel-concierge-orchestrator",
            auth_provider_id="travel-concierge-auth",
            binding_id="test-binding"
        )

        assert reg["service_name"] == "travel-concierge-orchestrator"
        assert reg["service_url"] == "https://travel-concierge-test.run.app"
        assert reg["binding_id"] == "test-binding"
        assert "travel-concierge-auth" in reg["auth_provider"]
        assert reg["agent_card"]["capabilities"]["geminiEnterpriseStreamAssist"] is True
        assert reg["agent_card"]["endpoints"]["streamAssist"] == "https://travel-concierge-test.run.app/portal/api/stream"


def test_delete_agent_binding():
    with patch("scripts.create_gemini_enterprise_app.run_cmd") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        deleted = delete_agent_binding(
            project_id="test-project",
            region="us-central1",
            binding_id="test-binding"
        )
        assert deleted is True


def test_build_app_configuration():
    config = build_app_configuration(
        project_id="test-project",
        location="global",
        region="us-central1",
        app_id="fdedemoapp",
        display_name="fdedemoapp",
        service_url="https://test.run.app",
        auth_provider_id="travel-concierge-auth",
        binding_id="test-binding",
        engine_metadata={"displayName": "fdedemoapp"}
    )

    assert config["app_id"] == "fdedemoapp"
    assert config["engine_id"] == "fdedemoapp"
    assert config["solution_type"] == "SOLUTION_TYPE_CHAT"
    assert config["engine_path"] == "projects/test-project/locations/global/collections/default_collection/engines/fdedemoapp"
    assert config["assistant_path"] == "projects/test-project/locations/global/collections/default_collection/engines/fdedemoapp/assistants/default_assistant"
    assert len(config["registered_agents"]) == 1
    assert config["registered_agents"][0]["stream_url"] == "https://test.run.app/portal/api/stream"
    assert config["status"] == "ACTIVE"


def test_write_configuration_files(tmp_path):
    config = {
        "app_id": "fdedemoapp",
        "engine_id": "fdedemoapp",
        "status": "ACTIVE",
        "location": "global"
    }

    json_path = tmp_path / "deploy" / "gemini_enterprise_app_config.json"
    yaml_path = tmp_path / "deploy" / "agent_gateway" / "gemini_enterprise_app_config.yaml"

    write_configuration_files(config, json_path, yaml_path)

    assert json_path.exists()
    assert yaml_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        loaded_json = json.load(f)
    assert loaded_json["app_id"] == "fdedemoapp"

    with open(yaml_path, "r", encoding="utf-8") as f:
        loaded_yaml = yaml.safe_load(f)
    assert loaded_yaml["app_id"] == "fdedemoapp"
