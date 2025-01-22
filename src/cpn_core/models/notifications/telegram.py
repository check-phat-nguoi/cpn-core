from re import compile as re_compile

from pydantic import ConfigDict, Field, field_validator

from cpn_core.models.notifications.base import BaseNotificationConfig

BOT_TOKEN_PATTERN = re_compile(r"^[0-9]+:.+$")


class TelegramConfig(BaseNotificationConfig):
    model_config = ConfigDict(
        title="Telegram",
        frozen=True,
    )

    bot_token: str = Field(
        description="Bot token Telegram",
        examples=[
            "2780473231:weiruAShGUUx4oLOMoUhd0GiREXSZcCq-uB",
        ],
    )
    chat_id: str = Field(
        description="Chat ID Telegram",
        examples=[
            "-1001790012349",
        ],
    )
    markdown: bool = Field(
        description="Gửi tin nhắn dạng markdown",
        default=True,
    )

    @field_validator("bot_token", mode="after")
    @classmethod
    def validate_bot_token(cls, value: str) -> str:
        if not BOT_TOKEN_PATTERN.match(value):
            raise ValueError(f"Bot token {value} is not valid")
        return value

    @field_validator("chat_id", mode="after")
    @classmethod
    def validate_chat_id(cls, value: str) -> str:
        if not value.lstrip("-").isnumeric():
            raise ValueError(f"Chat ID {value} is not valid")
        return value
