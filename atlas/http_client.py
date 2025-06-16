import logging
import tomllib
from datetime import datetime, timedelta
from os import environ
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urljoin

import requests


class AtlasConfigError(Exception):
    """Custom exception class for configuration errors."""

    def __init__(self, message):
        self.message = message


class AuthError(Exception):
    """Custom exception class for authentication errors."""

    def __init__(self, message, response):
        self.message = message
        self.response = response


class AtlasHTTPError(requests.HTTPError):
    """Custom exception class for HTTP errors."""

    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


class AtlasHTTPClient(requests.Session):
    BASE_URL = "https://atlaslive.io"
    LOGIN_ENDPOINT = "/api/login/v3/login"
    USERINFO_ENDPOINT = "/api/login/v3/userinfo"
    ATLAS_REFRESH_TOKEN_ENV_KEY = "ATLAS_REFRESH_TOKEN"
    DEFAULT_CONFIG_FILE_PATH = Path.home() / ".config/atlas/config.toml"
    HEADERS = "headers"
    REFRESH_TOKEN = "refresh_token"
    GRANT_TYPE = "grant_type"
    ACCESS_TOKEN = "access_token"
    EXPIRES_IN = "expires_in"
    AUTHORIZATION = "Authorization"
    BEARER = "Bearer"

    def __init__(
        self,
        refresh_token: Optional[str] = None,
        debug: Optional[bool] = False,
        **kwargs,
    ):
        """
        Parameters
        ----------
        refresh_token : Optional[str], optional
            refresh token can be provided directly, by default None
            If not provided, the refresh token will be read from the
            environment variable ATLAS_REFRESH_TOKEN or from the
            config file ~/.config/atlas/config.toml
        """
        super().__init__(**kwargs)
        self._refresh_token = self._get_refresh_token(refresh_token)
        self._auto_refresh_url = urljoin(self.BASE_URL, self.LOGIN_ENDPOINT)
        self._userinfo_url = urljoin(self.BASE_URL, self.USERINFO_ENDPOINT)
        self._api_url_prefix = urljoin(self.BASE_URL, "/api/front/v1")
        self._access_token = None
        self._expires_at = datetime.now() - timedelta(days=1)
        self._expiration_margin = timedelta(minutes=30)
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger = logging.getLogger("requests.packages.urllib3")
            logger.setLevel(logging.DEBUG)
            logger.propagate = True

    def get_user_id(self):
        return self._user_id

    def _get_refresh_token(self, refresh_token: Union[str, None]) -> str:
        """
        Parameters
        ----------
        refresh_token : Union[str, None]
            refresh token can be provided directly or found if None, by default None

        Returns
        -------
        str
            refresh token

        Raises
        ------
        AtlasConfigError
            Raised if no refresh token is provided and no config file is found at
            ~/.config/atlas/config.toml
        AtlasConfigError
            Raised if no refresh token is found for the passed environment in the config
            file
        """
        if refresh_token is None:
            refresh_token = environ.get(self.ATLAS_REFRESH_TOKEN_ENV_KEY, None)

        if refresh_token:
            return refresh_token

        if not self.DEFAULT_CONFIG_FILE_PATH.exists():
            raise AtlasConfigError(
                f"""No refresh token provided, and ATLAS config file not found at {self.DEFAULT_CONFIG_FILE_PATH}"""
            )

        with open(self.DEFAULT_CONFIG_FILE_PATH, "rb") as fn:
            atlas_config_file = tomllib.load(fn)

        refresh_token = atlas_config_file.get("production", {}).get(self.REFRESH_TOKEN, None)
        if not refresh_token:
            raise AtlasConfigError(
                f"""could not find refresh token for ATLAS" in
                {self.DEFAULT_CONFIG_FILE_PATH}"""
            )

        return refresh_token

    def refresh_access_token(self):
        """
        Refreshes the access token if it is about to expire and retrieves the user id.

        Raises
        ------
        ResponseError
            If the response from the auto refresh endpoint does not contain an
            access token or an expires in value.
        """
        if (self._expires_at - datetime.now()) < self._expiration_margin:
            auth = {
                self.GRANT_TYPE: self.REFRESH_TOKEN,
                self.REFRESH_TOKEN: self._refresh_token,
            }
            auth_response = requests.post(self._auto_refresh_url, data=auth, timeout=5)
            auth_response.raise_for_status()
            response_json = auth_response.json()
            self._access_token = response_json.get(self.ACCESS_TOKEN, None)
            expires_in = response_json.get(self.EXPIRES_IN, None)
            if not self._access_token:
                raise AuthError(
                    f"Could not find {self.ACCESS_TOKEN} in response from {self._auto_refresh_url}",
                    response=response_json,
                )
            if not expires_in:
                raise AuthError(
                    f"Could not find {self.EXPIRES_IN} in response from {self._auto_refresh_url}",
                    response=response_json,
                )
            self._expires_at = datetime.now() + timedelta(seconds=expires_in)
            userinfo = requests.get(
                self._userinfo_url, headers={self.AUTHORIZATION: f"{self.BEARER} {self._access_token}"}
            )
            userinfo.raise_for_status()
            data = userinfo.json()
            self._user_id = data.get("sub", None)

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Make an HTTP request to the ATLAS API with the provided method and URL.

        Parameters
        ----------
        method : str
            HTTP method, e.g. GET, POST, PUT, DELETE
        url : str
            URL to request

        Returns
        -------
        requests.Response

        Raises
        ------
        AtlasHTTPError
            Raised if the underlying request raises an HTTPError
        """
        response = None
        try:
            self.refresh_access_token()

            # call the underlying request method
            kwargs[self.HEADERS] = {self.AUTHORIZATION: f"{self.BEARER} {self._access_token}"}
            response = super().request(method, self._api_url_prefix + url, **kwargs)
            response.raise_for_status()
        except requests.HTTPError as ex:
            if response is not None:
                raise AtlasHTTPError(f"{ex} - {response.text}", response=response) from ex
            else:
                raise AtlasHTTPError(f"{ex} - No additional detail received") from ex

        return response
