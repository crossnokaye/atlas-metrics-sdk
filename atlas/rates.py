from datetime import datetime, timedelta
import re
from typing import Dict, List, Optional
from pydantic import BaseModel
from .atlas_client import AtlasClient, HourlyRates

class RateFilter(BaseModel):
    facilities: List[str]

class HourlyRate(BaseModel):
    start: datetime
    rate: float

class RatesReader:
    """
    High level API Client for retrieving energy rates from the ATLAS platform.
    """

    def __init__(self, refresh_token: Optional[str] = None, debug: Optional[bool] = False):
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

    def read(self, filter: RateFilter, start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, HourlyRates]:
        """
        Retrieve hourly energy rates for a given filter and time range.

        Parameters
        ----------
        filter : Filter
            Filter for energy rates values, defines the list of facilities to retrieve rates for.
        start : Optional[datetime], optional
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
        if start is None:
            start = datetime.now() - timedelta(days=1)
        if end is None:
            end = datetime.now()

        result = {}
        for f in facilities:
            try:
                result[f.short_name] = {k: [HourlyRate(start=datetime.fromtimestamp(d.start), rate=d.rate) for d in v]
                                        for k,v in self.client.get_hourly_rates(f.organization_id, f.agents[0].agent_id, start, end)}

            except Exception as e:
                raise Exception(f"Error retrieving rates for facility {f.display_name}: {e}")

        return result