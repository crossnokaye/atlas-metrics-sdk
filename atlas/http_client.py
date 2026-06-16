import logging
import tomllib
from datetime import UTC, datetime, timedelta
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import requests

if TYPE_CHECKING:
    from http.cookiejar import CookieJar

    import requests._types as _t
    from requests.cookies import RequestsCookieJar


class AtlasConfigError(Exception):
    """Custom exception class for configuration errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AuthError(Exception):
    """Custom exception class for authentication errors."""

    def __init__(self, message: str, response: Any) -> None:
        self.message = message
        self.response = response
        super().__init__(message)


class AtlasHTTPError(requests.HTTPError):
    """Custom exception class for HTTP errors."""

    def __init__(self, message: str, response: requests.Response | None = None) -> None:
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
        refresh_token: str | None = None,
        debug: bool | None = False,
        **kwargs: Any,
    ) -> None:
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
        self._access_token: str | None = None
        self._user_id: str | None = None
        self._expires_at = datetime.now(UTC) - timedelta(days=1)
        self._expiration_margin = timedelta(minutes=30)
        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger = logging.getLogger("requests.packages.urllib3")
            logger.setLevel(logging.DEBUG)
            logger.propagate = True

    def get_user_id(self) -> str | None:
        return self._user_id

    def _get_refresh_token(self, refresh_token: str | None) -> str:
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
                f"""No refresh token provided, and ATLAS config file not found at {self.DEFAULT_CONFIG_FILE_PATH}""",
            )

        with open(self.DEFAULT_CONFIG_FILE_PATH, "rb") as fn:
            atlas_config_file = tomllib.load(fn)
        production = atlas_config_file.get("production", {})
        if isinstance(production, dict):
            refresh_token = production.get(self.REFRESH_TOKEN, None)
        if not isinstance(refresh_token, str) or not refresh_token:
            raise AtlasConfigError(
                f"""could not find refresh token for ATLAS" in
                {self.DEFAULT_CONFIG_FILE_PATH}""",
            )

        return refresh_token

    def refresh_access_token(self) -> None:
        """
        Refreshes the access token if it is about to expire and retrieves the user id.

        Raises
        ------
        ResponseError
            If the response from the auto refresh endpoint does not contain an
            access token or an expires in value.
        """
        if (self._expires_at - datetime.now(UTC)) < self._expiration_margin:
            auth = {
                self.GRANT_TYPE: self.REFRESH_TOKEN,
                self.REFRESH_TOKEN: self._refresh_token,
            }
            auth_response = requests.post(self._auto_refresh_url, data=auth, timeout=5)
            auth_response.raise_for_status()
            response_json: dict[str, Any] = auth_response.json()
            access_token = response_json.get(self.ACCESS_TOKEN, None)
            if access_token is None:
                raise AuthError(
                    f"Could not find {self.ACCESS_TOKEN} in response from {self._auto_refresh_url}",
                    response=response_json,
                )
            if not isinstance(access_token, str) or len(access_token) == 0:
                raise AuthError(
                    f"Invalid {self.ACCESS_TOKEN} in response from {self._auto_refresh_url}",
                    response=response_json,
                )
            self._access_token = access_token
            expires_in = response_json.get(self.EXPIRES_IN, None)
            if expires_in is None:
                raise AuthError(
                    f"Could not find {self.EXPIRES_IN} in response from {self._auto_refresh_url}",
                    response=response_json,
                )
            if not isinstance(expires_in, int | float) or expires_in <= 0:
                raise AuthError(
                    f"Invalid {self.EXPIRES_IN} in response from {self._auto_refresh_url}",
                    response=response_json,
                )
            self._expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
            userinfo = requests.get(
                self._userinfo_url,
                headers={self.AUTHORIZATION: f"{self.BEARER} {self._access_token}"},
            )
            userinfo.raise_for_status()
            data = userinfo.json()
            user_id = data.get("sub", None) if isinstance(data, dict) else None
            if user_id is None:
                raise AuthError(
                    f"Could not find sub (user id) in response from {self._userinfo_url}",
                    response=data,
                )
            if not isinstance(user_id, str) or len(user_id) == 0:
                raise AuthError(
                    f"Invalid sub (user id) in response from {self._userinfo_url}",
                    response=data,
                )
            self._user_id = user_id

    def request(
        self,
        method: str,
        url: "_t.UriType",
        params: "_t.ParamsType" = None,
        data: "_t.DataType" = None,
        headers: "_t.HeadersType" = None,
        cookies: "RequestsCookieJar | CookieJar | dict[str, str] | None" = None,
        files: "_t.FilesType" = None,
        auth: "_t.AuthType" = None,
        timeout: "_t.TimeoutType" = None,
        allow_redirects: bool = True,
        proxies: dict[str, str] | None = None,
        hooks: "_t.HooksInputType | None" = None,
        stream: bool | None = None,
        verify: "_t.VerifyType | None" = None,
        cert: "_t.CertType" = None,
        json: "_t.JsonType" = None,
    ) -> requests.Response:
        """
        Make an HTTP request to the ATLAS API with the provided method and URL.

        Behaves like :meth:`requests.Session.request`, with three addition:

        - ``url`` is resolved relative to the Atlas API prefix.
        - A bearer ``Authorization`` header is injected (refreshing the
          access token first if it is near expiry).
        - HTTP error responses are raised as :class:`AtlasHTTPError`, whose
          message includes the response body.

        Raises
        ------
        AtlasHTTPError
            Raised if the underlying request raises an HTTPError
        """
        response: requests.Response
        try:
            self.refresh_access_token()

            # call the underlying request method
            headers = dict(headers) if headers else {}
            headers[self.AUTHORIZATION] = f"{self.BEARER} {self._access_token}"
            url_str = url.decode("utf-8") if isinstance(url, bytes) else url
            response = super().request(
                method,
                self._api_url_prefix + url_str,
                params=params,
                data=data,
                headers=headers,
                cookies=cookies,
                files=files,
                auth=auth,
                timeout=timeout,
                allow_redirects=allow_redirects,
                proxies=proxies,
                hooks=hooks,
                stream=stream,
                verify=verify,
                cert=cert,
                json=json,
            )
            response.raise_for_status()
        except requests.HTTPError as ex:
            ex_response = ex.response
            if ex_response is not None:
                raise AtlasHTTPError(f"{ex} - {ex_response.text}", response=ex_response) from ex
            else:
                raise AtlasHTTPError(f"{ex} - No additional detail received") from ex

        return response
