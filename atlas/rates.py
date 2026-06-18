from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from atlas.atlas_client import AtlasClient
from atlas.models import HourlyRates


class RateFilter(BaseModel):
    facilities: list[str]


class RatesReader:
    """
    High level API Client for retrieving energy rates from the ATLAS platform.
    """

    def __init__(self, refresh_token: str | None = None, debug: bool | None = False):
        """
        Parameters
        ----------
        refresh_token : Optional[str], optional
            Refresh token can be provided directly, by default None.
            If not provided, the refresh token will be read from the
            environment variable ATLAS_REFRESH_TOKEN or from the
            config file ~/.config/ATLAS/config.toml.
        debug : Optional[bool], optional
            Enable debug logging, by default False.
        """
        self.client = AtlasClient(refresh_token=refresh_token, debug=debug)

    def read(
        self,
        filter: RateFilter,
        begin: datetime | None = None,
        end: datetime | None = None,
    ) -> list[HourlyRates]:
        """
        Retrieve hourly energy rates for a given filter and time range.

        Parameters
        ----------
        filter : Filter
            Filter for energy rates values, defines the list of facilities to retrieve rates for.
        begin : Optional[datetime], optional
            Start time of the historical values, by default 24 hours ago.
        end : Optional[datetime], optional
            End time of the historical values, by default now.

        Returns
        -------
        Dict[str, HourlyRates]
            Dictionary of energy rates indexed by facility short name.

        Raises
        ------
        Exception
            Raised if an error occurs.
        """
        facilities = self.client.filter_facilities(filter.facilities)
        now = datetime.now(UTC)
        if begin is None:
            begin = now - timedelta(days=1)
        elif begin.tzinfo is None:
            raise ValueError("start must be timezone aware")
        if end is None:
            end = now
        elif end.tzinfo is None:
            raise ValueError("end must be timezone aware")
        result = []
        for f in facilities:
            try:
                result.append(self.client.get_hourly_rates(f.organization_id, f.agents[0].agent_id, begin, end))

            except Exception as e:
                raise Exception(f"Error retrieving rates for facility {f.display_name}: {e}")

        return result
