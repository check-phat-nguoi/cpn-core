import asyncio
from logging import getLogger
from typing import LiteralString, override

from httpx import AsyncClient

from cpn_core.models.notifications.telegram import TelegramConfig

from .base import BaseNotificationEngine

API_URL: LiteralString = "https://api.telegram.org/bot{bot_token}/sendMessage"


logger = getLogger(__name__)


class TelegramEngine(BaseNotificationEngine[TelegramConfig]):
    def __init__(self, *, timeout: float) -> None:
        self._timeout: float = timeout
        self._session: AsyncClient = AsyncClient(
            timeout=timeout,
        )

    async def _send_message(
        self,
        telegram: TelegramConfig,
        message: str,
    ) -> None:
        url: str = API_URL.format(bot_token=telegram.bot_token)
        payload: dict[str, str] = {
            "chat_id": telegram.chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        try:
            async with self._session.stream(
                "POST",
                url,
                json=payload,
            ) as response:
                response.raise_for_status()
            logger.info("Successfully sent to Telegram Chat ID: %s", telegram.chat_id)
        except TimeoutError as e:
            logger.error(
                "Timeout (%ds) sending to Telegram Chat ID: %s. %s",
                self._timeout,
                telegram.chat_id,
                e,
            )
            raise
        except Exception as e:
            logger.error(
                "Failed to sent to Telegram Chat ID (internally): %s. %s",
                telegram.chat_id,
                e,
            )
            raise

    @override
    async def send(
        self,
        config: TelegramConfig,
        messages: tuple[str, ...],
    ) -> None:
        await asyncio.gather(
            *(
                self._send_message(
                    telegram=config,
                    message=message,
                )
                for message in messages
            )
        )

    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await self._session.aclose()
