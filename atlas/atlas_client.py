from datetime import datetime, timedelta, timezone
from typing import Optional
import json

from atlas.http_client import AtlasHTTPClient, AtlasHTTPError
from atlas.models import (
    AggregateBy,
    Condition,
    ControlPoint,
    Deployment,
    Device,
    DeviceAssociations,
    Facility,
    HistoricalHourlyRates,
    HistoricalSettingQuery,
    HistoricalSettingQuerySource,
    HistoricalReadingQuery,
    ReadingSourceResult,
    SettingSourceResult,
    HourlyRates,
    Metric,
    Output,
    Setting,
)


class AtlasClient:
    """
    API Client for retrieving data from the ATLAS platform.
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

    def list_facilities(self) -> list[Facility]:
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

    def list_devices(self, org_id: str, agent_id: str) -> list[Device]:
        """
        List all devices for a given facility.

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
        url = f"/orgs/{org_id}/agents/{agent_id}/controlled-devices"

        try:
            response = self.client.request("GET", url)
            controlled_devices = response.json()
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

        devices: list[Device] = []
        device_associations = self._get_device_associations(org_id, agent_id)

        for controlled_device in controlled_devices.get("values", []):
            device = Device(
                id=controlled_device["device_id"],
                name=controlled_device["name"],
                alias=controlled_device["alias"],
                kind=controlled_device["kind"],
                control_points=[
                    ControlPoint(**control_point) for control_point in controlled_device.get("control_points", [])
                ],
                metrics=[Metric(**metric) for metric in controlled_device.get("metrics", [])],
                outputs=[Output(**output) for output in controlled_device.get("outputs", [])],
                conditions=[Condition(**condition) for condition in controlled_device.get("conditions", [])],
                settings=[Setting(**setting) for setting in controlled_device.get("settings", [])],
            )
            associations = device_associations.get(device.id, DeviceAssociations())
            device.upstream = associations.upstream
            device.downstream = associations.downstream
            devices.append(device)

        return devices

    def get_historical_reading_values(
        self,
        org_id: str,
        agent_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        queries: list[HistoricalReadingQuery] | None = None,
        interval: int = 60,
        changes_only: bool = False,
        include_scaled: bool = True,
        include_raw: bool = False,
    ) -> list[ReadingSourceResult]:
        """
        Get historical reading values. A single request may return results for multiple sources
        and multiple aggregation methods for each source.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities
        start : Optional[datetime], optional
            start time for the query, by default 10 minutes ago
        end : Optional[datetime], optional
            end time for the query, by default now
        queries : dict[str, list[AggregateBy]], optional
            a dictionary of source IDs (point IDs) to aggregation methods to apply to each source
        interval : int, optional
            sample interval in seconds, by default 60
        changes_only : bool, optional
            true when only changed values should be returned
        include_scaled : bool, optional
            return scaled values for numeric sources, by default True
        include_raw : bool, optional
            return raw values for numeric sources, by default False

        Returns
        -------
        List[ReadingSourceResult]
            list of historical reading results

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        url = f"/orgs/{org_id}/agents/{agent_id}/readings/queries"
        if start is not None:
            if start.tzinfo is None:
                raise ValueError("start must be timezone aware")

        if end is not None:
            if end.tzinfo is None:
                raise ValueError("end must be timezone aware")

        # queries must be provided and non-empty
        if queries is None or len(queries) == 0:
            raise ValueError("queries must be a non-empty list of ReadingQuery")

        # Validate each query (aggregate_by is optional)
        for query in queries:
            if not isinstance(query, HistoricalReadingQuery):
                raise ValueError("each item in queries must be a ReadingQuery")

        payload = {
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ")
            if start
            else (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")
            if end
            else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval": interval,
            "changes_only": changes_only,
            "include_scaled": include_scaled,
            "include_raw": include_raw,
            # ensure models/enums are JSON-serializable
            "queries": [q.model_dump(mode="json", exclude_none=True) for q in queries],
        }
        try:
            # Stream response to handle NDJSON
            response = self.client.request("POST", url, json=payload, stream=True)
            results: list[ReadingSourceResult] = []
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                # Parse NDJSON line and map API fields to model fields
                parsed = json.loads(line)
                transformed = {
                    "time": parsed.get("time"),
                    "source_id": parsed.get("sourceId"),
                    "forced": parsed.get("forced", False),
                    "results": [],
                }
                for res in parsed.get("results", []):
                    res_obj = {}
                    if "aggregation" in res:
                        res_obj["aggregation"] = res["aggregation"]
                    if "numberValue" in res:
                        res_obj["numberValue"] = res["numberValue"]
                    if "boolValue" in res:
                        res_obj["boolValue"] = res["boolValue"]
                    if "enumValue" in res:
                        res_obj["enumValue"] = res["enumValue"]
                    transformed["results"].append(res_obj)

                results.append(ReadingSourceResult(**transformed))
            return results
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

    def get_historical_setting_values(
        self,
        org_id: str,
        agent_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        queries: list[HistoricalSettingQuery] | None = None,
        interval: str = "1m",
        changes_only: bool = False,
    ) -> list[SettingSourceResult]:
        """
        Get historical setting values. A single request may return results for multiple sources
        and multiple aggregation methods for each source.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities
        start : Optional[datetime], optional
            start time for the query, by default 10 minutes ago
        end : Optional[datetime], optional
            end time for the query, by default now
        queries : dict[str, list[AggregateBy]], optional
            a dictionary of source IDs (point IDs) to aggregation methods to apply to each source
        interval : string, optional
            sample interval duration string (e.g. "1m", "5m", "1h", "1d"), by default "1m"
        changes_only : bool, optional
            true when only changed values should be returned

        Returns
        -------
        List[SettingSourceResult]
            list of historical setting results

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        url = f"/orgs/{org_id}/agents/{agent_id}/settings/queries"
        if start is not None:
            if start.tzinfo is None:
                raise ValueError("start must be timezone aware")

        if end is not None:
            if end.tzinfo is None:
                raise ValueError("end must be timezone aware")
        
        # queries must be provided and non-empty
        if queries is None or len(queries) == 0:
            raise ValueError("queries must be a non-empty list of HistoricalSettingQuery")

        for query in queries:
            if not isinstance(query, HistoricalSettingQuery):
                raise ValueError("each item in queries must be a HistoricalSettingQuery")

        payload = {
            "start": start.strftime("%Y-%m-%dT%H:%M:%SZ")
            if start
            else (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%SZ")
            if end
            else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval": interval,
            "changes_only": changes_only,
            # ensure models/enums are JSON-serializable
            "queries": [q.model_dump(mode="json", exclude_none=True) for q in queries],
        }
        try:
            # Stream response to handle NDJSON
            response = self.client.request("POST", url, json=payload, stream=True)
            results: list[SettingSourceResult] = []
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                # Parse NDJSON line and map API fields to model fields
                parsed = json.loads(line)
                transformed = {
                    "time": parsed.get("time"),
                    "setting_id": parsed.get("settingId"),
                    "results": [],
                }
                for res in parsed.get("results", []):
                    res_obj = {}
                    if "aggregation" in res:
                        res_obj["aggregation"] = res["aggregation"]
                    if "unset" in res:
                        res_obj["unset"] = res["unset"]
                    if "enumValue" in res:
                        res_obj["enumValue"] = res["enumValue"]
                    if "boolValue" in res:
                        res_obj["boolValue"] = res["boolValue"]
                    if "numberValue" in res:
                        res_obj["numberValue"] = res["numberValue"]
                    if "sequenceValue" in res:
                        res_obj["sequenceValue"] = res["sequenceValue"]
                    if "scheduleValue" in res:
                        res_obj["scheduleValue"] = res["scheduleValue"]
                    transformed["results"].append(res_obj)

                results.append(SettingSourceResult(**transformed))
            return results
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

    def filter_facilities(self, filter: list[str]) -> list[Facility]:
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

    def _get_device_associations(self, org_id: str, agent_id: str) -> dict[str, DeviceAssociations]:
        """
        Get to devices connections for a given facility by device ID.

        Parameters
        ----------
        org_id : str
            organization ID associated with the facility as returned by list_facilities
        agent_id : str
            agent ID associated with the facility as returned by list_facilities

        Returns
        -------
        Dict[str, DeviceAssociations]
            Dictionary of device IDs to device associations

        Raises
        ------
        AtlasHTTPError
            Raised if an error occurs while making the request
        """
        active_deployment = self._get_current_deployment(org_id, agent_id)
        devices_url = f"/orgs/{org_id}/agents/{agent_id}/devices"  # used for connections only
        params = {"version": active_deployment.blueprint_version}

        try:
            response = self.client.request("GET", devices_url, params=params)
            devices = response.json()
        except ValueError as e:
            raise AtlasHTTPError(f"{e}, got {response}", response=response)

        return {
            device["id"]: DeviceAssociations(
                upstream=device.get("upstream", []), downstream=device.get("downstream", [])
            )
            for device in devices.get("values", [])
        }
