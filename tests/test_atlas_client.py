from typing import cast
from unittest.mock import Mock, create_autospec

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from atlas.atlas_client import AtlasClient
from atlas.http_client import AtlasHTTPClient, AtlasHTTPError
from atlas.models import Agent, Facility


@pytest.fixture
def mock_http_client(mocker: MockerFixture) -> Mock:
    mock_http_client = cast(Mock, create_autospec(AtlasHTTPClient, spec_set=True, instance=True))
    mocker.patch("atlas.atlas_client.AtlasHTTPClient", return_value=mock_http_client)
    return mock_http_client


@pytest.fixture
def client(mock_http_client: Mock) -> AtlasClient:
    return AtlasClient()


def test_atlas_client_init_relays_args_and_refresh_auth(mocker: MockerFixture) -> None:
    mock_http_client = create_autospec(AtlasHTTPClient, spec_set=True, instance=True)
    mock_http_client_cls = mocker.patch("atlas.atlas_client.AtlasHTTPClient", return_value=mock_http_client)

    client = AtlasClient(refresh_token="test-token", debug=True)

    assert client
    mock_http_client_cls.assert_called_once_with(refresh_token="test-token", debug=True)
    mock_http_client.refresh_access_token.assert_called_once()


def test_atlas_client_list_facilities_parses_and_returns(mock_http_client: Mock, client: AtlasClient) -> None:
    expected_facility = Facility(
        organization_id="org-1",
        facility_id="fac-1",
        display_name="Test Facility",
        short_name="test",
        address="123 Main St",
        timezone="America/New_York",
        agents=[Agent(agent_id="agent-1")],
    )
    mock_http_client.get_user_id.return_value = "user-123"
    mock_http_client.request.return_value.status_code = 200
    mock_http_client.request.return_value.json.return_value = [
        expected_facility.model_dump(mode="json"),
    ]

    got_facilities = client.list_facilities()

    mock_http_client.request.assert_called_once_with("GET", "/users/user-123/facilities?view=extended")
    assert got_facilities == [expected_facility]


def test_atlas_client_list_facilities_value_error_raises_http_error(
    mock_http_client: Mock,
    client: AtlasClient,
) -> None:
    mock_http_client.get_user_id.return_value = "user-123"
    mock_http_client.request.return_value.status_code = 200
    mock_http_client.request.return_value.json.side_effect = ValueError("test error")

    with pytest.raises(AtlasHTTPError, match="test error") as exc_info:
        _ = client.list_facilities()

    assert exc_info.value.response.status_code == 200


def test_atlas_client_list_facilities_pydantic_error_raises(mock_http_client: Mock, client: AtlasClient) -> None:
    mock_http_client.get_user_id.return_value = "user-123"
    mock_http_client.request.return_value.status_code = 200
    mock_http_client.request.return_value.json.return_value = [
        {
            "organization_id": "org-1",
            "facility_id": "fac-1",
            "bad_field": "test",
        },
    ]

    with pytest.raises(ValidationError, match="bad_field"):
        _ = client.list_facilities()
