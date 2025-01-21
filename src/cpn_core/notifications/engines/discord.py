from logging import getLogger
from typing import override

from discord import (
    Client,
    DMChannel,
    Forbidden,
    GroupChannel,
    HTTPException,
    Intents,
    TextChannel,
    User,
)

from cpn_core.notifications.models.discord import DiscordNotificationEngineConfig

from .base import BaseNotificationEngine

logger = getLogger(__name__)


# FIXME: @NTGNguyen: fetch channel, id bla bla bla. The command_prefix seem bruh? not relate
class _DiscordNotificationCoreEngine:
    def __init__(
        self,
        discord: DiscordNotificationEngineConfig,
        messages: tuple[str, ...],
    ) -> None:
        self.discord: DiscordNotificationEngineConfig = discord
        self._messages: tuple[str, ...] = messages
        self._client = Client(intents=Intents.default())

    async def _send_channel(self) -> None:
        try:
            channel = await self._client.fetch_channel(self.discord.chat_id)
            if channel is None:
                logger.error("Discord channel ID %d: Not found", self.discord.chat_id)
                return
            if (
                not isinstance(channel, TextChannel)
                or not isinstance(channel, GroupChannel)
                or not isinstance(channel, DMChannel)
            ):
                logger.error(
                    "Discord channel ID %d: Must be text channel", self.discord.chat_id
                )
                return
            for message in self._messages:
                await channel.send(message)
            logger.info(
                "Successfully sent to Discord channel: %d", self.discord.chat_id
            )
        except Exception as e:
            logger.error("Discord channel ID %d: %s", self.discord.chat_id, e)

    async def _send_user(self) -> None:
        try:
            user: User = await self._client.fetch_user(self.discord.chat_id)
            for message in self._messages:
                await user.send(message)
            logger.info("Successfully sent to Discord user: %d", self.discord.chat_id)
        except Forbidden as e:
            logger.error(
                "Discord bot doesn't have permission to send to user %d. %s",
                self.discord.chat_id,
                e,
            )
        except HTTPException as e:
            logger.error(
                "Failed to send message to %d. %s",
                self.discord.chat_id,
                e,
            )
        except Exception as e:
            logger.error(
                "Failed to send message to %d (internal). %s",
                self.discord.chat_id,
                e,
            )

    async def send(self) -> None:
        @self._client.event
        async def on_ready() -> None:  # pyright: ignore [reportUnusedFunction]
            match self.discord.chat_type:
                case "user":
                    await self._send_user()
                case "channel":
                    await self._send_channel()
            await self._client.close()

        await self._client.start(self.discord.bot_token)


class DiscordNotificationEngine(
    BaseNotificationEngine[DiscordNotificationEngineConfig]
):
    @override
    async def send(
        self,
        config: DiscordNotificationEngineConfig,
        messages: tuple[str, ...],
    ) -> None:
        discord_engine = _DiscordNotificationCoreEngine(config, messages)
        await discord_engine.send()
