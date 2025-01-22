from logging import getLogger
from typing import Self

from aiohttp import ClientSession, ClientTimeout

logger = getLogger(__name__)


class RequestSessionHelper:
    def __init__(self, *, timeout: float) -> None:
        self._session_: ClientSession | None = None
        self._timeout: float = timeout

    @property
    def _session(self) -> ClientSession:
        if self._session_ is None:
            self._session_ = ClientSession(
                timeout=ClientTimeout(self._timeout),
            )
            logger.debug("Created a request session")
        return self._session_

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        if self._session_ is not None:
            await self._session_.close()
            logger.debug("Closed a request session")
