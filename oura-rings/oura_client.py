# -*- coding: utf-8 -*-
"""
Oura API Client
Handles authentication and API requests to Oura Ring API v2.
"""

from __future__ import annotations

import requests
from datetime import date, timedelta
from typing import Any


API_URL = "https://api.ouraring.com"


class OuraClient:
    """Make requests to the Oura API."""

    def __init__(self, personal_access_token: str):
        """Initialize a Requests session for making API requests."""
        self._personal_access_token: str = personal_access_token
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {self._personal_access_token}"}
        )

    def __enter__(self) -> "OuraClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self):
        self.session.close()

    def get_daily_activity(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        start, end = self._format_dates(start_date, end_date)
        return self._make_paginated_request(
            "GET",
            "v2/usercollection/daily_activity",
            params={"start_date": start, "end_date": end},
        )

    def get_daily_readiness(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        start, end = self._format_dates(start_date, end_date)
        return self._make_paginated_request(
            "GET",
            "v2/usercollection/daily_readiness",
            params={"start_date": start, "end_date": end},
        )

    def get_daily_sleep(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        start, end = self._format_dates(start_date, end_date)
        return self._make_paginated_request(
            "GET",
            "v2/usercollection/daily_sleep",
            params={"start_date": start, "end_date": end},
        )

    def get_heart_rate(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        start, end = self._format_dates(start_date, end_date)
        return self._make_paginated_request(
            "GET",
            "v2/usercollection/heartrate",
            params={"start_date": start, "end_date": end},
        )

    def get_sleep_periods(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        start, end = self._format_dates(start_date, end_date)
        return self._make_paginated_request(
            "GET",
            "v2/usercollection/sleep",
            params={"start_date": start, "end_date": end},
        )

    def get_sessions(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        start, end = self._format_dates(start_date, end_date)
        return self._make_paginated_request(
            "GET",
            "v2/usercollection/session",
            params={"start_date": start, "end_date": end},
        )

    def get_workouts(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        start, end = self._format_dates(start_date, end_date)
        return self._make_paginated_request(
            "GET",
            "v2/usercollection/workout",
            params={"start_date": start, "end_date": end},
        )

    def _make_paginated_request(
        self, method, url_slug, **kwargs
    ) -> list[dict[str, Any]]:
        params = kwargs.pop("params", {})
        response_data: list[dict[str, Any]] = []

        while True:
            response = self._make_request(method, url_slug, params=params, **kwargs)
            response_data.extend(response["data"])
            if next_token := response.get("next_token"):
                params["next_token"] = next_token
            else:
                break
        return response_data

    def _make_request(self, method, url_slug, **kwargs) -> dict[str, Any]:
        response = self.session.request(
            method=method, url=f"{API_URL}/{url_slug}", timeout=60, **kwargs
        )
        response.raise_for_status()
        return response.json()

    def _format_dates(
        self, start_date: str | None, end_date: str | None
    ) -> tuple[str, str]:
        end = date.fromisoformat(end_date) if end_date else date.today()
        start = (
            date.fromisoformat(start_date) if start_date else end - timedelta(days=1)
        )
        if start > end:
            raise ValueError(f"Start date greater than end date: {start} > {end}")
        return str(start), str(end)
