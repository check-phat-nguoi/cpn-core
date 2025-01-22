from re import compile as re_compile
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from cpn_core.models.notifications.base import BaseNotificationConfig

BOT_TOKEN_PATTERN = re_compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")
CHAT_ID_PATTERN = re_compile(r"^\d{18,19}$")


class DiscordConfig(BaseNotificationConfig):
    model_config = ConfigDict(
        title="Discord",
        frozen=True,
    )

    bot_token: str = Field(
        description="Bot token",
        examples=[
            "MTMzNzg4Ujq0NDI0NDYgNTcyMA.GpITQg.beoF9OxJScbKJwEz5Udy6bzrQJ8zI4BvndbaBA",
        ],
    )
    chat_id: int = Field(
        description="Chat ID",
        examples=[
            832930846182672436,
        ],
    )
    chat_type: Literal["user", "channel"]
    markdown: bool = Field(
        description="Gửi tin nhắn dạng markdown",
        default=True,
    )

    @field_validator("bot_token", mode="after")
    @classmethod
    def _validate_bot_token(cls, value: str) -> str:
        if not BOT_TOKEN_PATTERN.match(value):
            raise ValueError(f"Bot token {value} is not valid")
        return value

    @field_validator("chat_id", mode="after")
    @classmethod
    def _validate_chat_id(cls, value: int) -> int:
        if not CHAT_ID_PATTERN.match(str(value)):
            raise ValueError(f"User ID {value} is not valid")
        return value
