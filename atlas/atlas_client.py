from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from atlas.http_client import AtlasHTTPClient, AtlasHTTPError
from atlas.models import (
    AggregateBy,
    Deployment,
    Device,
    Facility,
    HistoricalHourlyRates,
    HistoricalValues,
    HourlyRates,
)


class AtlasClient:
    """
    API Client for retrieving historical point values from the ATLAS platform.
    """

    def __init__(
        self,
        refresh_token: Optional[str] = None,
        debug: Optional[bool] = False,
    ):
        """
        Parameters
        ----------
        refresh_token : Optional[str], optional
            refresh token can be provided directly, by default None
            If not provided, the refresh token will be read from the
            environment variable ATLAS_REFRESH_TOKEN or from the
            config file ~/.config/atlas/config.toml
        debug : Optional[bool], optional
            enable debug logging, by default False
        """
        self.client = AtlasHTTPClient(refresh_token=refresh_token, debug=debug)
        self.client.refresh_access_token()

    def list_facilities(self) -> List[Facility]:
        """
        List facilities the logged in user has access to.

        Returns
        -------
        List[Facility]
            List of facilities

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        url = f"/users/{self.client.get_user_id()}/facilities?view=extended"
        response = self.client.request("GET", url)
        try:
            facilities = response.json()
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

        return [Facility(**facility) for facility in facilities]

    def list_devices(self, org_id: str, agent_id: str) -> List[Device]:
        """
        List all devices for a given facility. Uses the current deployment to get the devices.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities

        Returns
        -------
        List[Device]
            List of devices

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        active_deployment = self._get_current_deployment(org_id, agent_id)
        url = f"/orgs/{org_id}/agents/{agent_id}/devices"
        params = {"version": active_deployment.blueprint_version}

        try:
            response = self.client.request("GET", url, params=params)
            devices = response.json()
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

        return [Device(**device) for device in devices.get("values", [])]

    def get_point_ids(
        self,
        org_id: str,
        agent_id: str,
        point_aliases: List[str],
    ) -> Dict[str, str]:
        """
        Retrieve point IDs given an agent and point aliases.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities
        point_aliases : List[str]
            list of point aliases as returned by list_devices

        Returns
        -------
        Dict[str, str]
            dictionary of point aliases to point IDs

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        url = f"/orgs/{org_id}/agents/{agent_id}/point-ids"
        payload = {"names": point_aliases}
        try:
            response = self.client.request("POST", url, json=payload)
            return response.json()
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

    def get_historical_values(
        self,
        org_id: str,
        agent_id: str,
        point_ids: List[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: int = 60,
        aggregate_by: List[AggregateBy] = ["avg"],
        changes_only: bool = False,
        scaled: bool = True,
    ) -> List[HistoricalValues]:
        """
        Get historical point values. A single request may return multiple points
        and multiple aggregation methods for each point.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities
        point_ids : List[str]
            list of point IDs to return historical values for as returned by get_point_ids
        start : Optional[datetime], optional
            start time for the query, by default 10 minutes ago
        end : Optional[datetime], optional
            end time for the query, by default now
        interval : int, optional
            sample interval in seconds, by default 60
        aggregate_by : List[AggregateBy], optional
            list of aggregation methods, by default ["avg"]
        changes_only : bool, optional
            only return data points where the value has changed, by default False
        scaled : bool, optional
            return analog data in physical units, by default True

        Returns
        -------
        List[HistoricalValues]
            list of historical values

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        url = f"/orgs/{org_id}/agents/{agent_id}/facility-readings"
        if start is not None:
            if start.tzinfo is None:
                raise ValueError("start must be timezone aware")

        if end is not None:
            if end.tzinfo is None:
                raise ValueError("end must be timezone aware")

        payload = {
            "point_ids": point_ids,
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ")
            if start
            else (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ") if end else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval": interval,
            "aggregate_by": aggregate_by,
            "changes_only": changes_only,
            "scaled": scaled,
        }
        try:
            response = self.client.request("POST", url, json=payload)
            values = response.json()
            return [HistoricalValues(**value) for value in values]
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

    def get_hourly_rates(
        self,
        org_id: str,
        agent_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> HourlyRates:
        """
        Get hourly rates for a given facility.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities
        since : Optional[datetime], optional
            start time for the query (inclusive), by default 24 hours ago
        until : Optional[datetime], optional
            end time for the query (exclusive), by default now

        Returns
        -------
        HourlyRates
            hourly rates

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        url = f"/orgs/{org_id}/agents/{agent_id}/rates"
        if since is not None:
            if since.tzinfo is None:
                raise ValueError("since must be timezone aware")

        if until is not None:
            if until.tzinfo is None:
                raise ValueError("until must be timezone aware")

        params = {
            "since": since.strftime("%Y-%m-%dT%H:%M:%SZ")
            if since
            else (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "until": until.strftime("%Y-%m-%dT%H:%M:%SZ")
            if until
            else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        try:
            response = self.client.request("GET", url, params=params)
            return HistoricalHourlyRates(**response.json()).to_hourly_rates()
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

    def filter_facilities(self, filter: List[str]) -> List[Facility]:
        try:
            all_facilities = self.list_facilities()
        except Exception as e:
            raise Exception(f"Error listing facilities: {e}")

        if not filter:
            return all_facilities

        facilities = [f for f in all_facilities if f.short_name in filter]
        if len(facilities) != len(filter):
            not_found = set(filter) - set(f.short_name for f in facilities)
            raise Exception(f"Facilities {', '.join(not_found)} not found")

        return facilities

    def _get_current_deployment(
        self,
        org_id: str,
        agent_id: str,
    ) -> Deployment:
        """
        Get the current deployment for a given facility.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities

        Returns
        -------
        Deployment
            Current Deployment at the facility including active blueprint version

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        KeyError
            Raised if an error occurs while parsing the response
        """
        url = f"/orgs/{org_id}/agents/{agent_id}/site-narratives/deployments/current"
        try:
            response = self.client.request("GET", url)
            response_json = response.json()
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

        try:
            return Deployment(
                id=response_json["id"],
                agent_id=response_json["agent_id"],
                organization_id=response_json["org_id"],
                blueprint_version=response_json["blueprint"]["version"],
            )
        except KeyError as e:
            raise AtlasHTTPError(f"Error parsing deployment: {e}, got {response_json}", response=response)
