"""Telegram adapter boundary. A bot token is not required to run DormFlow."""

from collections.abc import Awaitable, Callable
from typing import Protocol


class NotificationAdapter(Protocol):
    async def send(self, recipient: str, message: str) -> None: ...


class TelegramAdapter:
    def __init__(self, sender: Callable[[str, str], Awaitable[None]] | None = None) -> None:
        self._sender = sender

    async def send(self, recipient: str, message: str) -> None:
        if self._sender is None:
            raise RuntimeError("Telegram integratsiyasi sozlanmagan.")
        await self._sender(recipient, message)
