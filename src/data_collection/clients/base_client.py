import asyncio
import httpx
import logging
import pandas as pd
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

class BaseClient(ABC):
    """Abstract base class for API clients."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        semaphore_limit: int = 10,
        request_timeout: float = 60.0,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ):
        self.base_url = base_url
        self.api_key = api_key
        self.semaphore = asyncio.Semaphore(semaphore_limit)
        self.request_timeout = request_timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.client: Optional[httpx.AsyncClient] = None # Initialize as None, created in __aenter__

    async def __aenter__(self):
        """Asynchronous context manager entry point. Initializes the httpx.AsyncClient."""
        self.client = httpx.AsyncClient()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit point. Closes the httpx.AsyncClient."""
        if self.client:
            await self.client.aclose()

    async def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None, json_data: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Makes an asynchronous HTTP request."""
        # Ensure client is initialized before making a request
        if not self.client:
            raise RuntimeError("httpx.AsyncClient not initialized. Use BaseClient within an 'async with' block.")

        async with self.semaphore:
            url = f"{self.base_url}/{endpoint}"
            for attempt in range(self.max_retries + 1):
                try:
                    response = await self.client.request(
                        method,
                        url,
                        params=params,
                        headers=headers,
                        json=json_data,
                        timeout=self.request_timeout,
                    )
                    response.raise_for_status()
                    if response.status_code == 204:
                        return None
                    try:
                        return response.json()
                    except ValueError:
                        log.warning("API response from %s was not valid JSON.", response.request.url)
                        return None
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    retry_after = e.response.headers.get("Retry-After")
                    should_retry = status == 429 or 500 <= status < 600
                    if should_retry and attempt < self.max_retries:
                        delay = self._retry_delay(attempt, retry_after)
                        log.warning(
                            "API request to %s failed with status %s. Retrying in %.1fs (%s/%s).",
                            e.request.url,
                            status,
                            delay,
                            attempt + 1,
                            self.max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue
                    log.warning("API request to %s failed with status %s: %s", e.request.url, status, e.response.text)
                    return None
                except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as e:
                    if attempt < self.max_retries:
                        delay = self._retry_delay(attempt)
                        log.warning(
                            "API request to %s failed due to transport error (%s). Retrying in %.1fs (%s/%s).",
                            url,
                            type(e).__name__,
                            delay,
                            attempt + 1,
                            self.max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue
                    log.error("API request to %s failed after retries: %s", url, e, exc_info=True)
                    return None
                except httpx.HTTPError as e:
                    log.error("API request to %s failed with HTTP client error: %s", url, e, exc_info=True)
                    return None
            return None

    def _retry_delay(self, attempt: int, retry_after_header: Optional[str] = None) -> float:
        """Compute retry delay with exponential backoff and optional Retry-After override."""
        if retry_after_header:
            try:
                parsed = float(retry_after_header)
                if parsed >= 0:
                    return parsed
            except ValueError:
                pass
        return self.retry_base_delay * (2 ** attempt)

    @abstractmethod
    async def fetch_data(self, **kwargs) -> pd.DataFrame:
        """Fetches data from the API and returns it as a DataFrame."""
        pass

    async def aclose(self):
        """Close the underlying HTTP client session."""
        if self.client:
            await self.client.aclose()
