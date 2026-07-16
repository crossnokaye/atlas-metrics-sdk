from pathlib import Path

import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from requests_mock import Mocker

from atlas.http_client import AtlasHTTPClient, AtlasHTTPError

LOGIN_URL = "https://atlaslive.io/api/login/v3/login"
USERINFO_URL = "https://atlaslive.io/api/login/v3/userinfo"
USER = "user-123"
MOCK_REFRESH_TOKEN = "mock-refresh-token"
MOCK_ACCESS_TOKEN = "mock-access-token"


@pytest.fixture
def client(requests_mock: Mocker) -> AtlasHTTPClient:
    requests_mock.post(
        LOGIN_URL,
        json={"access_token": MOCK_ACCESS_TOKEN, "expires_in": 3600},
    )
    requests_mock.get(USERINFO_URL, json={"sub": USER})

    client = AtlasHTTPClient(refresh_token=MOCK_REFRESH_TOKEN)
    client.refresh_access_token()

    return client


def test_http_client_init_uses_refresh_token_arg(
    requests_mock: Mocker,
    monkeypatch: pytest.MonkeyPatch,
    fs: FakeFilesystem,
) -> None:
    monkeypatch.setenv("ATLAS_REFRESH_TOKEN", "token-from-env")
    fs.create_file(
        file_path=Path.home() / ".config/atlas/config.toml",
        contents='[production]\nrefresh_token = "token-from-file"',
    )
    requests_mock.post(
        LOGIN_URL,
        additional_matcher=lambda r: r.text == "grant_type=refresh_token&refresh_token=token-from-args",
        json={"access_token": "test-access-token", "expires_in": 3600},
    )
    requests_mock.get(USERINFO_URL, json={"sub": "use-123"})

    client = AtlasHTTPClient(refresh_token="token-from-args")
    client.refresh_access_token()


def test_http_client_init_no_args_reads_refresh_token_from_env(
    requests_mock: Mocker,
    monkeypatch: pytest.MonkeyPatch,
    fs: FakeFilesystem,
) -> None:
    monkeypatch.setenv("ATLAS_REFRESH_TOKEN", "token-from-env")
    fs.create_file(
        file_path=Path.home() / ".config/atlas/config.toml",
        contents='[production]\nrefresh_token = "token-from-file"',
    )
    requests_mock.post(
        LOGIN_URL,
        additional_matcher=lambda r: r.text == "grant_type=refresh_token&refresh_token=token-from-env",
        json={"access_token": "test-access-token", "expires_in": 3600},
    )
    requests_mock.get(USERINFO_URL, json={"sub": "use-123"})

    client = AtlasHTTPClient()
    client.refresh_access_token()


def test_http_client_init_no_args_reads_refresh_token_from_file(requests_mock: Mocker, fs: FakeFilesystem) -> None:
    fs.create_file(
        file_path=Path.home() / ".config/atlas/config.toml",
        contents='[production]\nrefresh_token = "token-from-file"',
    )
    requests_mock.post(
        LOGIN_URL,
        additional_matcher=lambda r: r.text == "grant_type=refresh_token&refresh_token=token-from-file",
        json={"access_token": "test-access-token", "expires_in": 3600},
    )
    requests_mock.get(USERINFO_URL, json={"sub": "use-123"})

    client = AtlasHTTPClient()
    client.refresh_access_token()


def test_http_client_request_builds_url_and_sends_authorization_header(
    requests_mock: Mocker,
    client: AtlasHTTPClient,
) -> None:
    requests_mock.get(
        "https://atlaslive.io/api/front/v1/resource",
        additional_matcher=lambda r: r.headers.get("Authorization") == f"Bearer {MOCK_ACCESS_TOKEN}",
        json={"res": "test"},
    )

    res = client.request("GET", "/resource")
    assert res.json() == {"res": "test"}


def test_http_client_request_404_raises(
    requests_mock: Mocker,
    client: AtlasHTTPClient,
) -> None:
    requests_mock.get(
        "https://atlaslive.io/api/front/v1/missing",
        status_code=404,
        text="Test Not Found",
    )

    with pytest.raises(AtlasHTTPError, match="Test Not Found") as ex_res:
        _ = client.request("GET", "/missing")

    assert ex_res.value is not None
    assert ex_res.value.response is not None
    assert ex_res.value.response.status_code == 404
    assert ex_res.value.response.text == "Test Not Found"
