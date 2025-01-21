from logging import getLogger
from ssl import SSLContext
from ssl import create_default_context as ssl_create_context
from typing import Final, Self

from httpx import AsyncClient

logger = getLogger(__name__)
SSL_CONTEXT: Final[SSLContext] = ssl_create_context()
SSL_CONTEXT.set_ciphers("DEFAULT@SECLEVEL=1")


class RequestSessionHelper:
    def __init__(self, *, timeout: float) -> None:
        self._session_: AsyncClient | None = None
        self._timeout: float = timeout

    @property
    def _session(self) -> AsyncClient:
        if self._session_ is None:
            self._session_ = AsyncClient(timeout=self._timeout, verify=SSL_CONTEXT)
            logger.debug("Created a request session")
        return self._session_

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        if self._session_ is not None:
            await self._session_.aclose()
            logger.debug("Closed a request session")
