"""
tests/test_auth_platform.py

Unit and integration tests for Google Auth Platform configuration,
OAuth 2.0 client provisioning, and Gemini Enterprise Agent Identity integration.

References:
- https://docs.cloud.google.com/docs/authentication
- https://support.google.com/cloud/answer/15549257
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from scripts.setup_auth_platform import (
    build_auth_platform_configuration,
    get_or_create_oauth_brand,
    get_or_create_oauth_client,
    setup_agent_identity_auth_provider,
    store_credentials_in_secret_manager,
    write_configuration_files,
)


@pytest.fixture
def sample_brand():
    return {
        "name": "projects/1234567890/brands/1234567890",
        "applicationTitle": "Test Concierge Agent",
        "supportEmail": "test-admin@example.com",
        "orgInternalOnly": True,
    }


@pytest.fixture
def sample_client():
    return {
        "clientId": "1234567890-abcdef123456.apps.googleusercontent.com",
        "clientSecret": "GOCSPX-TestSecretValue123",
        "displayName": "gemini-enterprise-agent-client",
        "name": "projects/1234567890/brands/1234567890/identityAwareProxyClients/1234567890-abcdef123456.apps.googleusercontent.com",
    }


@pytest.fixture
def sample_auth_provider():
    return {
        "name": "projects/test-project/locations/us-central1/authProviders/travel-concierge-auth",
        "description": "Gemini Enterprise OAuth Auth Provider",
        "state": "ENABLED",
        "authProviderTypeParams": {
            "threeLeggedOauth": {
                "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth",
                "clientId": "1234567890-abcdef123456.apps.googleusercontent.com",
                "defaultContinueUri": "https://vertexaisearch.cloud.google.com/oauth-redirect",
                "enablePkce": True,
                "redirectUrl": "https://agentidentitycredentials.googleapis.com/v1/projects/test-project/locations/us-central1/authProviders/travel-concierge-auth/oauthcallback",
                "tokenUrl": "https://oauth2.googleapis.com/token",
            }
        },
    }


def test_build_auth_platform_configuration(sample_brand, sample_client, sample_auth_provider):
    """Verifies that generated Auth Platform config adheres to Google Cloud & Gemini Enterprise specs."""
    config = build_auth_platform_configuration(
        project_id="test-project",
        region="us-central1",
        brand_info=sample_brand,
        oauth_client=sample_client,
        auth_provider_info=sample_auth_provider,
        service_url="https://travel-concierge-test.a.run.app",
    )

    auth_platform = config["google_auth_platform"]
    assert auth_platform["project_id"] == "test-project"
    assert auth_platform["brand"]["name"] == sample_brand["name"]
    assert auth_platform["oauth_client"]["client_id"] == sample_client["clientId"]
    assert auth_platform["oauth_client"]["application_type"] == "WEB_APPLICATION"

    # Required Gemini Enterprise redirect URIs
    redirects = auth_platform["oauth_client"]["authorized_redirect_uris"]
    assert "https://vertexaisearch.cloud.google.com/oauth-redirect" in redirects
    assert "https://vertexaisearch.cloud.google.com/static/oauth/oauth.html" in redirects
    assert "https://agentidentitycredentials.googleapis.com/v1/projects/test-project/locations/us-central1/authProviders/travel-concierge-auth/oauthcallback" in redirects
    assert "https://travel-concierge-test.a.run.app/oauth2callback" in redirects

    # Origins
    origins = auth_platform["oauth_client"]["authorized_javascript_origins"]
    assert "https://vertexaisearch.cloud.google.com" in origins
    assert "https://travel-concierge-test.a.run.app" in origins

    # Data access scopes
    scopes = auth_platform["data_access_scopes"]
    assert "openid" in scopes
    assert "https://www.googleapis.com/auth/userinfo.email" in scopes
    assert "https://www.googleapis.com/auth/cloud-platform" in scopes

    # Gemini Enterprise Agent Identity deployment
    gemini = config["gemini_enterprise_deployment"]
    assert gemini["target_agent"] == "travel-concierge-orchestrator"
    assert gemini["auth_manager"]["enabled"] is True
    assert gemini["auth_manager"]["flow_type"] == "THREE_LEGGED_OAUTH_WITH_PKCE"
    assert gemini["auth_manager"]["pkce_enabled"] is True
    assert gemini["auth_manager"]["default_continue_uri"] == "https://vertexaisearch.cloud.google.com/oauth-redirect"


def test_get_or_create_oauth_brand_existing(sample_brand):
    """Verifies existing brand is retrieved and not recreated."""
    with patch("scripts.setup_auth_platform.run_cmd") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps([sample_brand]), stderr=""
        )
        brand = get_or_create_oauth_brand("test-project", "App Title", "email@example.com")
        assert brand["name"] == sample_brand["name"]
        assert mock_run.call_count == 1


def test_get_or_create_oauth_brand_creation(sample_brand):
    """Verifies new brand creation when none exists."""
    with patch("scripts.setup_auth_platform.run_cmd") as mock_run:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(sample_brand), stderr=""),
        ]
        brand = get_or_create_oauth_brand("test-project", "App Title", "email@example.com")
        assert brand["name"] == sample_brand["name"]
        assert mock_run.call_count == 2


def test_get_or_create_oauth_client_explicit():
    """Verifies that explicitly passed client ID and secret take precedence."""
    res = get_or_create_oauth_client(
        brand_name="projects/123/brands/123",
        project_id="test-project",
        client_display_name="my-client",
        explicit_client_id="my-custom-client-id",
        explicit_client_secret="my-custom-secret",
    )
    assert res["clientId"] == "my-custom-client-id"
    assert res["clientSecret"] == "my-custom-secret"


def test_get_or_create_oauth_client_discovery(sample_client):
    """Verifies discovery of existing OAuth client under brand."""
    with patch("scripts.setup_auth_platform.run_cmd") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps([sample_client]), stderr=""
        )
        client = get_or_create_oauth_client(
            brand_name="projects/123/brands/123",
            project_id="test-project",
            client_display_name=sample_client["displayName"],
        )
        assert client["clientId"] == sample_client["clientId"]
        assert client["clientSecret"] == sample_client["clientSecret"]


def test_setup_agent_identity_auth_provider_existing(sample_auth_provider):
    """Verifies discovery of existing Agent Identity Auth Provider."""
    with patch("scripts.setup_auth_platform.run_cmd") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(sample_auth_provider), stderr=""
        )
        provider = setup_agent_identity_auth_provider(
            project_id="test-project",
            location="us-central1",
            auth_provider_id="travel-concierge-auth",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )
        assert provider["name"] == sample_auth_provider["name"]


def test_store_credentials_in_secret_manager():
    """Verifies Secret Manager storage invocation."""
    with patch("subprocess.run") as mock_sub:
        mock_sub.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="Created", stderr="")
        success = store_credentials_in_secret_manager(
            project_id="test-project",
            secret_id="travel-concierge-api-credentials",
            credentials_payload={"client_id": "cid", "client_secret": "csec"},
        )
        assert success is True
        assert mock_sub.call_count == 1


def test_write_configuration_files(tmp_path, sample_brand, sample_client, sample_auth_provider):
    """Verifies output JSON and YAML file format and parseability."""
    config = build_auth_platform_configuration(
        project_id="test-project",
        region="us-central1",
        brand_info=sample_brand,
        oauth_client=sample_client,
        auth_provider_info=sample_auth_provider,
        service_url="https://travel-concierge.example.com",
    )

    json_file = tmp_path / "auth_config.json"
    yaml_file = tmp_path / "auth_config.yaml"

    write_configuration_files(config, json_file, yaml_file)

    assert json_file.exists()
    assert yaml_file.exists()

    with open(json_file, "r") as f:
        loaded_json = json.load(f)
    assert loaded_json["google_auth_platform"]["project_id"] == "test-project"

    with open(yaml_file, "r") as f:
        loaded_yaml = yaml.safe_load(f)
    assert loaded_yaml["gemini_enterprise_deployment"]["target_agent"] == "travel-concierge-orchestrator"
